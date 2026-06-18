// ============ Отрисовка бирки на canvas + кодирование в .emf ============
// Канва как у станка
const LBL_W = 1419, LBL_H = 884;

// Короткие названия материалов (как в питон-версии)
const MATERIAL_DISPLAY = {
  "ЛДСП Белый Молет": "ЛДСП «Белый»",
  "ЛДСП Бежевый":     "ЛДСП «Бежевый»",
  "ЛДСП Серый":       "ЛДСП «Серый»",
  "ЛДСП Белый":       "ЛДСП «Белый»",
};

let _cncIcon = null;            // предзагруженная иконка CNC
function preloadIcon() {
  return new Promise((res) => {
    const img = new Image();
    img.onload = () => { _cncIcon = img; res(); };
    img.onerror = () => res();
    img.src = window.CNC_ICON_PNG;
  });
}

function utf8(s) { return unescape(encodeURIComponent(s)); }

function padDate(s) {
  const p = String(s || "").split(".");
  if (p.length === 3 && p.every((x) => /^\d+$/.test(x)))
    return p[0].padStart(2, "0") + "." + p[1].padStart(2, "0") + "." + p[2];
  return s || "—";
}

// Подбор размера шрифта, чтобы влезло в maxW
function fitFont(ctx, text, weight, size, family, maxW) {
  do {
    ctx.font = `${weight} ${size}px ${family}`;
    if (ctx.measureText(text).width <= maxW) break;
    size -= 4;
  } while (size > 24);
  return size;
}

// Рисуем QR в квадрат box, центрируя в (x0,y0,boxArea)
// Текст для QR: всё, что есть на бирке (читается телефоном построчно)
function qrText(part, dispName) {
  const mat = MATERIAL_DISPLAY[part.material] || part.material || "—";
  const dk = numOr0(part.dk), shk = numOr0(part.shk);
  const t = String(part.tolk == null ? "" : part.tolk).trim();
  const krom = (!dk && !shk && !t) ? "Кромка: нет"
    : "Кромка: Д" + dk + "/Ш" + shk + (t ? ", " + t : "");
  return [
    dispName,
    padDate(part.date) + " · " + (part.qty || "—") + "шт",
    mat,
    "Место: " + (part.cell || "—"),
    (part.length || "—") + "x" + (part.width || "—"),
    krom,
    "CNC: " + (part.prisadka ? "да" : "нет"),
  ].join("\n");
}

function drawQR(ctx, text, x0, y0, boxArea) {
  const qr = qrcode(0, "M");          // данных больше -> средняя коррекция (баланс плотность/надёжность)
  qr.addData(utf8(text), "Byte");
  qr.make();
  const n = qr.getModuleCount();
  const border = 2;
  const total = n + border * 2;
  const scale = Math.max(1, Math.floor(boxArea / total));
  const px = total * scale;
  const ox = x0 + Math.floor((boxArea - px) / 2);
  const oy = y0 + Math.floor((boxArea - px) / 2);
  ctx.fillStyle = "#000";
  for (let r = 0; r < n; r++)
    for (let c = 0; c < n; c++)
      if (qr.isDark(r, c))
        ctx.fillRect(ox + (c + border) * scale, oy + (r + border) * scale, scale, scale);
}

// Главная функция: рисует бирку детали на canvas
function drawLabel(canvas, part) {
  canvas.width = LBL_W; canvas.height = LBL_H;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, LBL_W, LBL_H);
  ctx.fillStyle = "#000"; ctx.strokeStyle = "#000";
  ctx.textBaseline = "top";
  const FAM = "Arial, 'Helvetica Neue', sans-serif";

  // рамка
  roundRect(ctx, 6, 6, LBL_W - 13, LBL_H - 13, 26); ctx.lineWidth = 4; ctx.stroke();

  // вертикальный разделитель
  const DIV = 626;
  line(ctx, DIV, 40, DIV, LBL_H - 40, 4);

  // -------- левая часть --------
  const dispName = String(part.name || "").replace(/\//g, "-");
  drawQR(ctx, qrText(part, dispName), 44, 40, 540);   // в QR — все поля бирки
  line(ctx, 44, 612, 590, 612, 3);

  const lenStr = String(part.length || "—"), widStr = String(part.width || "—");
  const dims = `${lenStr}  x  ${widStr}`;
  let s = fitFont(ctx, dims, "900", 96, FAM, 540);
  ctx.font = `900 ${s}px ${FAM}`; ctx.fillText(dims, 48, 648);
  // обозначение кромки под числами (Длина→ДК, Ширина→ШК), толщина по ТолК
  const x1b = 48 + ctx.measureText(lenStr).width;
  const x2a = 48 + ctx.measureText(`${lenStr}  x  `).width;
  const x2b = x2a + ctx.measureText(widStr).width;
  if (part.dk == null && part.shk == null) {        // колонок кромки нет — как раньше
    line(ctx, 48, 800, x1b, 800, 3); line(ctx, x2a, 800, x2b, 800, 3);
  } else {
    const lw = isThick(part.tolk) ? 8 : 3;
    edgeLines(ctx, 48, x1b, 800, numOr0(part.dk), lw);
    edgeLines(ctx, x2a, x2b, 800, numOr0(part.shk), lw);
  }

  // -------- правая часть --------
  const RX = 660, RXE = LBL_W - 44, RW = RXE - RX;

  s = fitFont(ctx, dispName, "bold", 76, FAM, RW);
  ctx.font = `bold ${s}px ${FAM}`; ctx.fillText(dispName, RX, 48);

  ctx.font = `bold 44px ${FAM}`;
  ctx.fillText("Дата: " + padDate(part.date), RX, 188);
  ctx.fillText("Кол-во в партии: " + (part.qty || "—") + " шт", RX, 252);

  const mat = MATERIAL_DISPLAY[part.material] || part.material || "—";
  s = fitFont(ctx, "Материал: " + mat, "bold", 46, FAM, RW);
  ctx.font = `bold ${s}px ${FAM}`; ctx.fillText("Материал: " + mat, RX, 326);

  line(ctx, RX, 420, RXE, 420, 3);

  ctx.font = `bold 60px ${FAM}`; ctx.fillText("Место:", RX, 470);
  const labW = ctx.measureText("Место:").width;
  ctx.font = `900 104px ${FAM}`; ctx.fillText(part.cell || "—", RX + labW + 28, 438);

  ctx.font = `bold 60px ${FAM}`; ctx.fillText("CNC:", RX, 690);
  if (part.prisadka && _cncIcon)
    ctx.drawImage(_cncIcon, RX + 200, 640, 181, 181);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function line(ctx, x1, y1, x2, y2, w) {
  ctx.lineWidth = w; ctx.beginPath();
  ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
}

// Обозначение кромки: count параллельных линий, толщина по ТолК
function edgeLines(ctx, x1, x2, yTop, count, lw) {
  if (!count || count < 1) return;
  const gap = lw + 8;
  for (let i = 0; i < count; i++) line(ctx, x1, yTop + i * gap, x2, yTop + i * gap, lw);
}
function numOr0(v) { return parseInt(String(v == null ? "" : v).replace(/[^\d]/g, ""), 10) || 0; }
function isThick(v) { return parseFloat(String(v == null ? "" : v).replace(",", ".")) >= 0.6; }

// -------- кодирование canvas -> 1-bit BMP (формат станка) --------
function encodeBMP1bit(canvas) {
  const W = canvas.width, H = canvas.height;
  const data = canvas.getContext("2d").getImageData(0, 0, W, H).data;
  const rowBytes = Math.floor((W + 31) / 32) * 4;   // паддинг до 4 байт
  const imgSize = rowBytes * H;
  const fileSize = 62 + imgSize;                     // 14+40+8 заголовки
  const buf = new ArrayBuffer(fileSize);
  const dv = new DataView(buf);
  const u8 = new Uint8Array(buf);
  // BITMAPFILEHEADER
  u8[0] = 0x42; u8[1] = 0x4d;            // 'BM'
  dv.setUint32(2, fileSize, true);
  dv.setUint32(10, 62, true);            // offset to pixels
  // BITMAPINFOHEADER
  dv.setUint32(14, 40, true);
  dv.setInt32(18, W, true);
  dv.setInt32(22, H, true);
  dv.setUint16(26, 1, true);             // planes
  dv.setUint16(28, 1, true);             // bpp = 1
  dv.setUint32(30, 0, true);             // compression
  dv.setUint32(34, imgSize, true);
  dv.setInt32(38, 3780, true);           // x ppm
  dv.setInt32(42, 3780, true);           // y ppm
  dv.setUint32(46, 2, true);             // clrUsed
  dv.setUint32(50, 2, true);             // clrImportant
  // palette: index0 = чёрный, index1 = белый (BGRA)
  u8[54] = 0; u8[55] = 0; u8[56] = 0; u8[57] = 0;
  u8[58] = 255; u8[59] = 255; u8[60] = 255; u8[61] = 0;
  // пиксели (снизу вверх), бит=1 -> белый
  for (let y = 0; y < H; y++) {
    const srcY = H - 1 - y;
    let rowOff = 62 + y * rowBytes;
    for (let x = 0; x < W; x++) {
      const i = (srcY * W + x) * 4;
      const lum = (data[i] * 299 + data[i + 1] * 587 + data[i + 2] * 114) / 1000;
      if (lum >= 128) u8[rowOff + (x >> 3)] |= (0x80 >> (x & 7)); // белый -> 1
    }
  }
  return u8;
}

// .emf = две одинаковые копии BMP подряд (как у станка)
function makeEMF(canvas) {
  const bmp = encodeBMP1bit(canvas);
  const out = new Uint8Array(bmp.length * 2);
  out.set(bmp, 0); out.set(bmp, bmp.length);
  return out;
}
