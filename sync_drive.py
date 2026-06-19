#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Синхронизация бирок в Google Drive.

Что делает (запуск по расписанию, напр. GitHub Actions):
  1. читает XML-раскрои из исходной Drive-папки (BAZIS их туда складывает);
  2. для каждого XML: имя папки + число деталей (label1..labelN);
  3. данные детали (материал, МЕСТО, размеры, кромка) — из таблиц (как на сайте);
  4. кладёт N бирок в подпапку внутри Drive-папки `labels`;
  5. обновляет только то, что изменилось (поменяли «Место» в таблице -> бирки заменятся).

Авторизация: OAuth пользователя (refresh token) через переменные окружения:
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN
Папки (можно переопределить через окружение):
  XML_FOLDER_ID    — папка с XML (источник)
  LABELS_FOLDER_ID — папка labels (куда класть бирки)
"""

import os, io, re, sys, hashlib, datetime
import generate_labels as G

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials

XML_FOLDER_ID = os.environ.get("XML_FOLDER_ID", "1jdD9S-D80gBKzjGl-WcJ2G0XLwmKk3Mv")
LABELS_FOLDER_ID = os.environ.get("LABELS_FOLDER_ID", "1TO1PtrQA5TOvpSzS4TNRcglSIUjGbvbR")
FOLDER_MIME = "application/vnd.google-apps.folder"


def drive_service():
    creds = Credentials(
        None,
        refresh_token=os.environ["GOOGLE_REFRESH_TOKEN"],
        client_id=os.environ["GOOGLE_CLIENT_ID"],
        client_secret=os.environ["GOOGLE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_children(svc, parent, only_folders=False, fields="id,name,mimeType,md5Checksum", extra="", order_by=None):
    q = "'%s' in parents and trashed=false" % parent
    if only_folders:
        q += " and mimeType = '%s'" % FOLDER_MIME
    if extra:
        q += " " + extra
    out, token = [], None
    while True:
        r = svc.files().list(q=q, fields="nextPageToken, files(%s)" % fields,
                             pageToken=token, pageSize=1000, orderBy=order_by,
                             supportsAllDrives=True, includeItemsFromAllDrives=True).execute(num_retries=5)
        out += r.get("files", [])
        token = r.get("nextPageToken")
        if not token:
            break
    return out


def get_or_create_subfolder(svc, parent, name):
    for f in list_children(svc, parent, only_folders=True):
        if f["name"] == name:
            return f["id"]
    meta = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}
    return svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute(num_retries=5)["id"]


def download_bytes(svc, file_id):
    return svc.files().get_media(fileId=file_id, supportsAllDrives=True).execute(num_retries=5)


def upload_label(svc, parent, name, data):
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/octet-stream", resumable=False)
    meta = {"name": name, "parents": [parent]}
    svc.files().create(body=meta, media_body=media, fields="id", supportsAllDrives=True).execute(num_retries=5)


def parse_xml_bytes(b):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(b)
    material, groups = "", {}
    order = []
    for el in root.iter():
        if not material and el.get("material"):
            material = el.get("material").strip()
        code = (el.get("code") or "").strip()
        if "label" not in code.lower():
            continue
        comps = re.split(r"[\\/]", code)
        if len(comps) >= 2:
            folder = comps[-2]
            if folder not in groups:
                groups[folder] = set()
                order.append(folder)
        m = re.search(r"(label\d+)", comps[-1], re.I)
        if m and len(comps) >= 2:
            groups[folder].add(m.group(1).lower())
    return [{"folder": folder, "count": len(groups[folder]), "material": material}
            for folder in order if groups[folder]]


def emf_bytes(part):
    buf = io.BytesIO()
    G.draw_label(part).convert("1").save(buf, format="BMP")
    bmp = buf.getvalue()
    return bmp + bmp                                  # две копии — формат станка


def raspil_info(offline=False):
    """name -> {date, qty} из РАСПИЛ: дата задания и кол-во в партии (Д1, столбец E)."""
    m = {}
    try:
        for j in G.parse_job(date_filter="all", offline=offline):
            m[j["name"]] = {"date": j["date"], "qty": j["qty"]}   # берём последнюю запись
    except Exception as e:
        print("  (РАСПИЛ недоступен: %s)" % e)
    return m


def xml_modified_filter():
    days_raw = (os.environ.get("SYNC_DAYS") or "7").strip().lower()
    if days_raw in ("all", "все", "*"):
        return "все XML", ""
    days = int(days_raw)
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return "XML за последние %d дн." % days, "and modifiedTime > '%s'" % since


def main():
    if not all(os.environ.get(k) for k in
               ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")):
        print("Ключи Google не заданы (GitHub Secrets) — пропускаю. См. drive-auto/SYNC_SETUP.md")
        return
    svc = drive_service()
    base = G.fetch_base()                             # детали из Details List
    base_norm = G.build_part_lookup(base)
    info = raspil_info()                              # дата + кол-во в партии (Д1) по детали
    info_norm = {G.norm_part_name(k): v for k, v in info.items()}
    today = datetime.date.today().strftime("%d.%m.%Y")
    range_label, extra_filter = xml_modified_filter()  # по умолчанию свежие; SYNC_DAYS=all -> вся история
    xmls = [f for f in list_children(svc, XML_FOLDER_ID, extra=extra_filter,
                                     order_by="modifiedTime desc")   # свежие — первыми
            if f["name"].lower().endswith(".xml")]
    print("%s: %d" % (range_label, len(xmls)))

    made = skipped = missing = qty_from_xml = errors = 0
    total = len(xmls)
    for pos, x in enumerate(xmls, 1):
        prefix = "[%d/%d] " % (pos, total)
        try:
            label_jobs = parse_xml_bytes(download_bytes(svc, x["id"]))
        except Exception as e:
            print("  %s! %s — ошибка чтения XML: %s" % (prefix, x["name"], e)); continue
        if not label_jobs:
            print("  %s- %s — в XML не найдены label-коды" % (prefix, x["name"]))
            continue
        for job_pos, label_job in enumerate(label_jobs, 1):
            subprefix = prefix if len(label_jobs) == 1 else prefix + "[%d/%d] " % (job_pos, len(label_jobs))
            folder, n, material = label_job["folder"], label_job["count"], label_job["material"]
            pname = folder[:-(len(material) + 1)] if material and folder.endswith("-" + material) else folder
            part = base_norm.get(G.norm_part_name(pname))
            if part is None:
                print("  %s? деталь не найдена в базе: %r (папка %s)" % (subprefix, pname, folder)); missing += 1; continue

            ri = info.get(part["name"], {}) or info_norm.get(G.norm_part_name(part["name"]), {})
            date = ri.get("date") or today
            if ri and "qty" in ri:
                qty_label = ri["qty"]                     # кол-во НА БИРКЕ — из РАСПИЛ (Д1/Д2/Д3...)
                qty_source = "РАСПИЛ"
            else:
                qty_label = n                             # временный практичный fallback: число labelN из XML
                qty_source = "XML"
                qty_from_xml += 1
            data = emf_bytes(dict(part, date=date, qty=str(qty_label)))
            digest = hashlib.md5(data).hexdigest()
            # число ФАЙЛОВ остаётся n (из XML) — см. цикл ниже

            try:
                sub = get_or_create_subfolder(svc, LABELS_FOLDER_ID, folder)
                existing = list_children(svc, sub)
                if len(existing) == n and all(f.get("md5Checksum") == digest for f in existing):
                    print("  %s= %s: без изменений (%d файлов)" % (subprefix, folder, n))
                    skipped += 1; continue

                by_name = {}
                for f in existing:
                    by_name.setdefault(f["name"], []).append(f)

                def trash(fid):                            # чужие файлы удалить нельзя — пробуем мягко
                    try:
                        svc.files().update(fileId=fid, body={"trashed": True}, supportsAllDrives=True).execute(num_retries=5)
                    except Exception:
                        pass

                for i in range(1, n + 1):                  # обновляем на месте / создаём недостающие
                    nm = "label%d.emf" % i
                    fs = by_name.pop(nm, [])
                    if fs:
                        if fs[0].get("md5Checksum") != digest:
                            svc.files().update(fileId=fs[0]["id"], supportsAllDrives=True,
                                media_body=MediaIoBaseUpload(io.BytesIO(data),
                                                             mimetype="application/octet-stream")).execute(num_retries=5)
                        for dup in fs[1:]:
                            trash(dup["id"])
                    else:
                        upload_label(svc, sub, nm, data)
                for nm, fs in by_name.items():             # лишние labelN -> в корзину (мягко)
                    if re.match(r"label\d+\.emf$", nm):
                        for f in fs:
                            trash(f["id"])
                print("  %s✓ %s: %d файлов, кол-во на бирке %s из %s (Место %s, %s)"
                      % (subprefix, folder, n, qty_label, qty_source, part["cell"] or "—", date))
                made += 1
            except Exception as e:
                print("  %s! %s — ошибка записи: %s" % (subprefix, folder, str(e)[:160])); errors += 1

    print("Готово. Обновлено: %d, без изменений: %d, нет в базе: %d, кол-во взято из XML: %d, ошибок: %d"
          % (made, skipped, missing, qty_from_xml, errors))


if __name__ == "__main__":
    main()
