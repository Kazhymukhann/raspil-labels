#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Генератор бирок для пильного центра.

Что делает:
  - тянет данные детали из базы (Google Sheet, вкладка BASE) по названию;
  - берёт ДИНАМИЧЕСКУЮ ячейку из колонки «Место» (A3, B6, E3, X ...);
  - рисует бирку 1:1 с оригиналом (QR + название + №ячейки + материал + размеры + CNC);
  - сохраняет в формате labelN.emf (две копии монохромного BMP 1419x884, как у станка).

Меняешь «Место» в таблице -> перегенерировал -> на бирке новая ячейка.

Использование:
  # ПОЛНАЯ ДИНАМИКА ИЗ ТАБЛИЦЫ (вкладка РАСПИЛ): сам соберёт все бирки задания
  python3 generate_labels.py --job 08.12.2025      # все детали за дату
  python3 generate_labels.py --job all             # всё задание целиком

  # Ручной режим
  python3 generate_labels.py "ANT-Bok L/R;27"               # деталь;кол-во
  python3 generate_labels.py --date 08.12.2025 "ANT-Bok L/R;27" "V-Bok L/R;36"
  python3 generate_labels.py --offline --job 08.12.2025     # без интернета (из кэша)

Данные: РАСПИЛ -> какие детали, сколько штук, дата;  BASE -> материал, МЕСТО, размеры, CNC.
"""

import sys, os, csv, io, json, urllib.request, urllib.parse

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------- настройки
HERE = os.path.dirname(os.path.abspath(__file__))

def load_sheet_id():
    """ID Google-таблицы. Берётся из env RASPIL_SHEET_ID или из config.json
    (config.json не хранится в репозитории — впиши свой ID, см. config.example.json)."""
    sid = os.environ.get("RASPIL_SHEET_ID")
    if sid:
        return sid.strip()
    cfg = os.path.join(HERE, "config.json")
    if os.path.exists(cfg):
        try:
            return (json.load(open(cfg, encoding="utf-8")).get("sheet_id") or "").strip()
        except Exception:
            pass
    return ""

SHEET_ID = load_sheet_id()           # таблица с заданием (вкладка РАСПИЛ)
RASPIL_SHEET = "РАСПИЛ"
# Детали (материал/место/размеры/кромка) — таблица Details List, вкладка Main
BASE_SHEET_ID = "1pWEjfyh_MOm1U0zPpNIyp9DkqTk6ICcxS4W-8YqzKuI"
BASE_GID = "1918355371"
CACHE = os.path.join(HERE, "base_cache.csv")
OUT_DIR = os.path.join(HERE, "labels")
ICON_PRISADKA = os.path.join(HERE, "assets", "cnc_prisadka.png")

# Канва бирки (как в оригинале со станка)
W, H = 1419, 884

# Короткие названия материалов для бирки (DB -> бирка). Дополняй по мере надобности.
MATERIAL_DISPLAY = {
    "ЛДСП Белый Молет": "ЛДСП «Белый»",
    "ЛДСП Бежевый":     "ЛДСП «Бежевый»",
    "ЛДСП Серый":       "ЛДСП «Серый»",
    "ЛДСП Белый":       "ЛДСП «Белый»",
}

FONTS = "/System/Library/Fonts/Supplemental/"
def font(name, size):
    return ImageFont.truetype(FONTS + name, size)

# ---------------------------------------------------------------- база (DB)
def fetch_base(offline=False):
    """Возвращает dict: имя детали -> словарь полей из BASE."""
    if offline and os.path.exists(CACHE):
        text = open(CACHE, encoding="utf-8").read()
    else:
        url = ("https://docs.google.com/spreadsheets/d/%s/gviz/tq"
               "?tqx=out:csv&gid=%s" % (BASE_SHEET_ID, BASE_GID))
        text = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
        open(CACHE, "w", encoding="utf-8").write(text)  # кэш на случай оффлайна

    rows = list(csv.reader(io.StringIO(text)))
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    def col(r, name):
        i = idx.get(name)
        return r[i].strip() if i is not None and i < len(r) else ""
    def coln(r, name):                       # None, если колонки нет
        i = idx.get(name)
        if i is None:
            return None
        return r[i].strip() if i < len(r) else ""

    base = {}
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        name = r[0].strip()
        base[name] = {
            "name":     name,
            "material": col(r, "Материал"),
            "cell":     col(r, "Место"),       # <-- ДИНАМИЧЕСКАЯ ЯЧЕЙКА
            "prisadka": col(r, "Присадка"),
            "length":   col(r, "Длина"),
            "width":    col(r, "Ширина"),
            "thick":    col(r, "Толщина"),
            "tolk":     coln(r, "ТолК"),       # толщина кромки (0.8 жирная / 0.4 тонкая)
            "dk":       coln(r, "ДК"),         # длина-кромка: кол-во линий
            "shk":      coln(r, "ШК"),         # ширина-кромка: кол-во линий
            "date":     "",                    # уровень задания (вход)
            "qty":      "",                    # уровень задания (вход)
        }
    return base


def fetch_csv(sheet, cache_name):
    """Скачать вкладку как CSV (живьём по имени) + кэш."""
    cache = os.path.join(HERE, cache_name)
    try:
        url = ("https://docs.google.com/spreadsheets/d/%s/gviz/tq"
               "?tqx=out:csv&sheet=%s" % (SHEET_ID, urllib.parse.quote(sheet)))
        text = urllib.request.urlopen(url, timeout=30).read().decode("utf-8")
        open(cache, "w", encoding="utf-8").write(text)
    except Exception:
        text = open(cache, encoding="utf-8").read()
    return list(csv.reader(io.StringIO(text)))


def parse_job(date_filter=None, offline=False):
    """Читает вкладку РАСПИЛ: Наименование (B) + кол-во (C) + Дата (A).

    Возвращает список {name, qty, date}; количество суммируется по детали за день.
    """
    import re
    if offline:
        rows = list(csv.reader(io.StringIO(open(os.path.join(HERE, "raspil_cache.csv"),
                                                encoding="utf-8").read())))
    else:
        rows = fetch_csv(RASPIL_SHEET, "raspil_cache.csv")

    def norm_date(s):                       # "08.12.2025"/"8.12.2025" -> "8.12.2025"
        s = (s or "").strip()
        p = re.split(r"[.\-/]", s)
        return ".".join(str(int(x)) for x in p) if len(p) == 3 and all(
            x.strip().isdigit() for x in p) else s

    header = rows[0]
    date_i = header.index("Дата") if "Дата" in header else 0           # A
    name_i = header.index("Наименование") if "Наименование" in header else 1  # B
    qty_i = header.index("кол-во") if "кол-во" in header else 2         # C
    want = norm_date(date_filter) if date_filter and date_filter != "all" else None

    order, acc = [], {}
    for r in rows[1:]:
        if not r or len(r) <= name_i:
            continue
        rdate = r[date_i].strip() if date_i < len(r) else ""
        if not rdate:
            continue
        if want and norm_date(rdate) != want:
            continue
        name = r[name_i].strip()
        if not name:
            continue
        digits = re.sub(r"[^\d]", "", r[qty_i]) if qty_i < len(r) else ""
        qty = int(digits) if digits else 0
        key = (name, rdate)
        if key not in acc:
            acc[key] = {"name": name, "qty": 0, "date": rdate}
            order.append(key)
        acc[key]["qty"] += qty
    return [acc[k] for k in order]

# ---------------------------------------------------------------- QR
def qr_text(part, disp_name):
    """Текст для QR: все поля бирки (читается телефоном построчно)."""
    mat = MATERIAL_DISPLAY.get(part["material"], part["material"] or "—")
    dk, shk = _num(part.get("dk")), _num(part.get("shk"))
    t = str(part.get("tolk") if part.get("tolk") is not None else "").strip()
    if not dk and not shk and not t:
        krom = "Кромка: нет"
    else:
        krom = "Кромка: Д%d/Ш%d" % (dk, shk) + (", %s" % t if t else "")
    return "\n".join([
        disp_name,
        "%s · %sшт" % (part.get("date") or "—", part.get("qty") or "—"),
        mat,
        "Место: %s" % (part["cell"] or "—"),
        "%sx%s" % (part["length"] or "—", part["width"] or "—"),
        krom,
        "CNC: %s" % ("да" if part["prisadka"] else "нет"),
    ])


def make_qr(text, box):
    """Чёткий сканируемый монохромный QR ~box пикселей (кратно модулю, без ресайза)."""
    import segno
    qr = segno.make(text, error="m")
    modules = qr.symbol_size(border=2)[0]          # модулей вместе с тихой зоной
    scale = max(1, round(box / modules))           # целочисленный масштаб
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=2)
    buf.seek(0)
    return Image.open(buf).convert("1")            # размер = modules*scale (≈ box)

# ---------------------------------------------------------------- отрисовка
def _num(v):
    import re
    s = re.sub(r"[^\d]", "", str(v if v is not None else ""))
    return int(s) if s else 0

def _thick(v):
    try:
        return float(str(v if v is not None else "").replace(",", ".")) >= 0.6
    except ValueError:
        return False

def _edge(d, x1, x2, y_top, count, lw):
    if not count or count < 1:
        return
    gap = lw + 8
    for i in range(count):
        d.line([(x1, y_top + i * gap), (x2, y_top + i * gap)], fill=0, width=lw)

def fit_font(draw, text, name, size, max_w):
    """Подбираем размер шрифта, чтобы текст влез в max_w пикселей."""
    f = font(name, size)
    while size > 24 and draw.textlength(text, font=f) > max_w:
        size -= 4
        f = font(name, size)
    return f

def draw_label(part):
    img = Image.new("1", (W, H), 1)            # 1-bit, белый фон
    d = ImageDraw.Draw(img)
    BLACK = 0

    # --- внешняя рамка (скруглённый прямоугольник)
    d.rounded_rectangle([6, 6, W - 7, H - 7], radius=26, outline=BLACK, width=4)

    # --- вертикальный разделитель
    DIV = 626
    d.line([(DIV, 40), (DIV, H - 40)], fill=BLACK, width=4)

    # ============================ ЛЕВАЯ ЧАСТЬ ============================
    # QR (кодируем отображаемое имя: "/" -> "-")
    disp_name = part["name"].replace("/", "-")
    qr_box = 540
    qr = make_qr(qr_text(part, disp_name), qr_box)   # в QR — все поля бирки
    qx = 44 + (qr_box - qr.width) // 2          # центрируем в области QR
    qy = 40 + (qr_box - qr.height) // 2
    img.paste(qr, (qx, qy))

    # линия под QR
    d.line([(44, 612), (590, 612)], fill=BLACK, width=3)

    # размеры "Длина x Ширина" + обозначение кромки под числами
    len_str = str(part["length"] or "—"); wid_str = str(part["width"] or "—")
    dims = "%s  x  %s" % (len_str, wid_str)
    fdim = fit_font(d, dims, "Arial Black.ttf", 96, 540)
    d.text((48, 648), dims, font=fdim, fill=BLACK)
    x1b = 48 + d.textlength(len_str, font=fdim)
    x2a = 48 + d.textlength("%s  x  " % len_str, font=fdim)
    x2b = x2a + d.textlength(wid_str, font=fdim)
    if part.get("dk") is None and part.get("shk") is None:   # колонок кромки нет — как раньше
        d.line([(48, 800), (x1b, 800)], fill=BLACK, width=3)
        d.line([(x2a, 800), (x2b, 800)], fill=BLACK, width=3)
    else:
        lw = 8 if _thick(part.get("tolk")) else 3
        _edge(d, 48, x1b, 800, _num(part.get("dk")), lw)       # Длина → ДК
        _edge(d, x2a, x2b, 800, _num(part.get("shk")), lw)     # Ширина → ШК

    # ============================ ПРАВАЯ ЧАСТЬ ===========================
    RX = 660                                    # левый край правой колонки
    RXE = W - 44                                # правый край
    RW = RXE - RX

    # 1) Наименование по системе
    ftitle = fit_font(d, disp_name, "Arial Bold.ttf", 76, RW)
    d.text((RX, 48), disp_name, font=ftitle, fill=BLACK)

    # 2) Дата  |  Кол-во в партии
    flab = font("Arial Bold.ttf", 44)
    dt = part.get("date") or ""
    p = dt.split(".")
    if len(p) == 3 and all(x.isdigit() for x in p):     # дополняем до dd.mm.yyyy
        dt = "%02d.%02d.%s" % (int(p[0]), int(p[1]), p[2])
    d.text((RX, 188), "Дата: %s" % (dt or "—"), font=flab, fill=BLACK)
    d.text((RX, 252), "Кол-во в партии: %s шт" % (part.get("qty") or "—"),
           font=flab, fill=BLACK)

    # 3) Материал
    mat = MATERIAL_DISPLAY.get(part["material"], part["material"] or "—")
    fmat = fit_font(d, "Материал: " + mat, "Arial Bold.ttf", 46, RW)
    d.text((RX, 326), "Материал: " + mat, font=fmat, fill=BLACK)

    # разделительная линия
    d.line([(RX, 420), (RXE, 420)], fill=BLACK, width=3)

    # 4) МЕСТО (ячейка) — ключевое динамическое поле, крупно
    flab2 = font("Arial Bold.ttf", 60)
    d.text((RX, 470), "Место:", font=flab2, fill=BLACK)
    fcell = font("Arial Black.ttf", 104)
    lab_w = d.textlength("Место:", font=flab2)
    d.text((RX + lab_w + 28, 438), part["cell"] or "—", font=fcell, fill=BLACK)

    # 5) CNC: + иконка операции (присадка) — снизу справа
    fcnc = font("Arial Bold.ttf", 60)
    d.text((RX, 690), "CNC:", font=fcnc, fill=BLACK)
    if part["prisadka"] and os.path.exists(ICON_PRISADKA):
        icon = Image.open(ICON_PRISADKA).convert("1")
        img.paste(icon, (RX + 200, 640))

    return img

# ------------------------------------------------------- сохранение в .emf
def save_emf(img, path):
    """Сохраняем как 1-bit BMP, продублированный дважды (формат файлов станка)."""
    buf = io.BytesIO()
    img.convert("1").save(buf, format="BMP")
    bmp = buf.getvalue()
    with open(path, "wb") as f:
        f.write(bmp)
        f.write(bmp)            # вторая копия — как в оригинальных файлах

# ---------------------------------------------------------------- main
def main():
    import datetime
    args = sys.argv[1:]
    offline = "--offline" in args

    def opt(flag):
        return args[args.index(flag) + 1] if flag in args else None

    if not SHEET_ID and not offline:
        print("  ! Не задан ID таблицы. Создай config.json (см. config.example.json)\n"
              "    или задай: export RASPIL_SHEET_ID=<id>")
        sys.exit(1)

    base = fetch_base(offline=offline)
    os.makedirs(OUT_DIR, exist_ok=True)

    # ---- собираем список заданий: (name, qty, date) ----
    jobs = []
    if "--job" in args:
        # ПОЛНАЯ ДИНАМИКА: тянем задание прямо из вкладки РАСПИЛ
        for j in parse_job(date_filter=opt("--job"), offline=offline):
            jobs.append((j["name"], str(j["qty"]), j["date"]))
        if not jobs:
            print("  ! За '%s' в РАСПИЛ ничего не найдено" % opt("--job"))
            sys.exit(1)
    else:
        # ручной режим: "Имя" или "Имя;кол-во", дата через --date
        job_date = opt("--date") or datetime.date.today().strftime("%d.%m.%Y")
        skip = {args.index("--date") + 1} if "--date" in args else set()
        items = [a for k, a in enumerate(args)
                 if not a.startswith("--") and k not in skip]
        if not items:
            print(__doc__)
            sys.exit(1)
        for it in items:
            name, qty = (it.rsplit(";", 1) + [""])[:2] if ";" in it else (it, "")
            jobs.append((name.strip(), qty.strip(), job_date))

    # ---- генерим бирки ----
    n = 0
    for name, qty, date in jobs:
        part = base.get(name)
        if part is None:
            print("  ! НЕ найдено в BASE: %r — пропуск" % name)
            continue
        n += 1
        part = dict(part, date=date, qty=qty)
        img = draw_label(part)
        out = os.path.join(OUT_DIR, "label%d.emf" % n)
        save_emf(img, out)
        print("  label%d.emf  <-  %s | Место: %s | %s шт | %s | %s | %sx%s"
              % (n, part["name"], part["cell"] or "—", part["qty"] or "—",
                 part["date"], part["material"], part["length"], part["width"]))
    print("  ИТОГО бирок: %d  ->  %s" % (n, OUT_DIR))

if __name__ == "__main__":
    main()
