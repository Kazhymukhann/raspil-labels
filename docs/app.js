// ============================ Логика приложения ============================
const CFG = window.RASPIL_CONFIG || {};
const $ = (id) => document.getElementById(id);

let BASE = {};          // имя детали -> поля
let JOB = [];           // текущее задание [{name, qty, date}]
let GENERATED = [];     // [{filename, bytes, part, canvas}]

// ----- утилиты -----
function normDate(s) {
  s = String(s || "").trim();
  const p = s.split(/[.\-/]/);
  if (p.length === 3 && p.every((x) => /^\d+$/.test(x.trim())))
    return p.map((x) => String(parseInt(x, 10))).join(".");
  return s;
}
function dateKey(d) {                       // для сортировки
  const p = normDate(d).split(".");
  return p.length === 3 ? +p[2] * 10000 + +p[1] * 100 + +p[0] : 0;
}

// ----- CSV парсер (учитывает кавычки и запятые внутри) -----
function parseCSV(text) {
  const rows = [];
  let row = [], cell = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; }
      else cell += c;
    } else {
      if (c === '"') q = true;
      else if (c === ",") { row.push(cell); cell = ""; }
      else if (c === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
      else if (c === "\r") { /* skip */ }
      else cell += c;
    }
  }
  if (cell.length || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

// ----- получение данных: опубликованный CSV или gviz JSONP -----
async function fetchSheet(kind) {  // kind: 'base' | 'raspil'
  const url = kind === "base" ? CFG.baseCsvUrl : CFG.raspilCsvUrl;
  if (url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error("Не удалось загрузить CSV (" + r.status + ")");
    return parseCSV(await r.text());
  }
  if (CFG.sheetId) {
    const sheet = kind === "base" ? CFG.baseSheet : CFG.raspilSheet;
    return await gvizJSONP(CFG.sheetId, sheet);
  }
  throw new Error("Источник данных не настроен (config.js)");
}

function gvizJSONP(sheetId, sheet) {
  return new Promise((resolve, reject) => {
    const cb = "gviz_cb_" + Math.floor(performance.now()) + "_" +
               Math.random().toString(36).slice(2);
    const s = document.createElement("script");
    const cleanup = () => { delete window[cb]; s.remove(); };
    window[cb] = (resp) => { cleanup(); resolve(gvizToRows(resp)); };
    s.onerror = () => { cleanup(); reject(new Error("Нет доступа к таблице (JSONP)")); };
    s.src = `https://docs.google.com/spreadsheets/d/${sheetId}/gviz/tq` +
            `?sheet=${encodeURIComponent(sheet)}&tqx=responseHandler:${cb}`;
    document.head.appendChild(s);
  });
}
function gvizToRows(resp) {
  const t = resp.table;
  const header = t.cols.map((c) => (c.label || "").trim());
  const rows = [header];
  for (const r of t.rows)
    rows.push(r.c.map((c) => (c ? (c.f != null ? String(c.f) : (c.v != null ? String(c.v) : "")) : "")));
  return rows;
}

// ----- разбор -----
function buildBase(rows) {
  const h = rows[0], idx = {}; h.forEach((n, i) => idx[(n || "").trim()] = i);
  const col = (r, n) => { const i = idx[n]; return i != null && i < r.length ? (r[i] || "").trim() : ""; };
  const map = {};
  for (let k = 1; k < rows.length; k++) {
    const r = rows[k]; if (!r || !(r[0] || "").trim()) continue;
    const name = r[0].trim();
    map[name] = {
      name, material: col(r, "Материал"), cell: col(r, "Место"),
      prisadka: col(r, "Присадка"), length: col(r, "Длина"), width: col(r, "Ширина"),
    };
  }
  return map;
}

function parseJob(rows, dateFilter) {
  const h = rows[0], idx = {}; h.forEach((n, i) => idx[(n || "").trim()] = i);
  const dateI = idx["Дата"] != null ? idx["Дата"] : 0;
  const dCols = ["Д1", "Д2", "Д3"].filter((c) => idx[c] != null).map((c) => idx[c]);
  const want = dateFilter && dateFilter !== "all" ? normDate(dateFilter) : null;
  const pat = /^(.+?)-(\d+)\s*шт\s*\|/;
  const order = [], acc = {};
  for (let k = 1; k < rows.length; k++) {
    const r = rows[k]; if (!r || r.length <= dateI) continue;
    const rdate = (r[dateI] || "").trim(); if (!rdate) continue;
    if (want && normDate(rdate) !== want) continue;
    for (const ci of dCols) {
      const v = (r[ci] || "").trim();
      if (!v || v === "X" || v === "#N/A") continue;
      const m = v.match(pat); if (!m) continue;
      const name = m[1].trim(), qty = parseInt(m[2], 10);
      if (!qty) continue;
      const key = name + "|" + rdate;
      if (!(key in acc)) { acc[key] = { name, qty: 0, date: rdate }; order.push(key); }
      acc[key].qty += qty;
    }
  }
  return order.map((k) => acc[k]);
}

function allDates(rows) {
  const h = rows[0], idx = {}; h.forEach((n, i) => idx[(n || "").trim()] = i);
  const dateI = idx["Дата"] != null ? idx["Дата"] : 0;
  const set = new Set();
  for (let k = 1; k < rows.length; k++) {
    const r = rows[k]; if (!r || r.length <= dateI) continue;
    const d = (r[dateI] || "").trim(); if (d) set.add(normDate(d));
  }
  return [...set].sort((a, b) => dateKey(b) - dateKey(a));
}

function padDate2(s) {
  const p = normDate(s).split(".");
  return p.length === 3 ? p[0].padStart(2, "0") + "." + p[1].padStart(2, "0") + "." + p[2] : s;
}

// ----- поток: загрузка -----
let RASPIL_ROWS = null;
async function init() {
  await preloadIcon();
  setStatus("Загружаю данные из таблицы…");
  try {
    const [baseRows, raspilRows] = await Promise.all([fetchSheet("base"), fetchSheet("raspil")]);
    BASE = buildBase(baseRows);
    RASPIL_ROWS = raspilRows;
    const dates = allDates(raspilRows);
    const sel = $("dateSelect");
    sel.innerHTML = "";
    for (const d of dates) {
      const o = document.createElement("option");
      o.value = d; o.textContent = padDate2(d); sel.appendChild(o);
    }
    setStatus(`Готово. Деталей в базе: ${Object.keys(BASE).length}. Выбери дату и нажми «Сформировать».`, "ok");
    $("genBtn").disabled = false;
  } catch (e) {
    setStatus("Ошибка: " + e.message + ". Проверь config.js (источник данных).", "err");
  }
}

// ----- поток: генерация -----
async function generate() {
  const date = $("dateSelect").value;
  JOB = parseJob(RASPIL_ROWS, date);
  if (!JOB.length) { setStatus("За эту дату в РАСПИЛ ничего не найдено.", "err"); return; }
  setStatus(`Формирую бирки (${JOB.length})…`);
  const grid = $("grid"); grid.innerHTML = ""; GENERATED = [];
  let n = 0, skipped = [];
  for (const j of JOB) {
    const b = BASE[j.name];
    if (!b) { skipped.push(j.name); continue; }
    n++;
    const part = Object.assign({}, b, { date: j.date, qty: j.qty });
    const canvas = document.createElement("canvas");
    drawLabel(canvas, part);
    const bytes = makeEMF(canvas);
    const filename = `label${n}.emf`;
    GENERATED.push({ filename, bytes, part });
    grid.appendChild(makeCard(canvas, part, filename, bytes));
    if (n % 5 === 0) await new Promise((r) => setTimeout(r)); // не вешать UI
  }
  $("zipBtn").disabled = GENERATED.length === 0;
  let msg = `Готово: ${GENERATED.length} бирок.`;
  if (skipped.length) msg += ` Нет в базе BASE (пропущены): ${skipped.join(", ")}.`;
  setStatus(msg, GENERATED.length ? "ok" : "err");
}

function makeCard(canvas, part, filename, bytes) {
  const card = document.createElement("div"); card.className = "card";
  const thumb = document.createElement("canvas");
  thumb.width = 355; thumb.height = 221;
  thumb.getContext("2d").drawImage(canvas, 0, 0, 355, 221);
  card.appendChild(thumb);
  const info = document.createElement("div"); info.className = "info";
  info.innerHTML = `<b>${esc(part.name)}</b>` +
    `<span>Место: <b>${esc(part.cell || "—")}</b> · ${esc(part.qty || "—")} шт</span>` +
    `<span>${esc(part.material || "")}</span>`;
  card.appendChild(info);
  const a = document.createElement("a");
  a.className = "dl"; a.textContent = "скачать " + filename;
  a.href = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  a.download = filename;
  card.appendChild(a);
  return card;
}

async function downloadZip() {
  setStatus("Упаковываю в ZIP…");
  const zip = new JSZip();
  for (const g of GENERATED) zip.file(g.filename, g.bytes);
  const blob = await zip.generateAsync({ type: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "labels_" + padDate2($("dateSelect").value).replace(/\./g, "-") + ".zip";
  a.click();
  setStatus(`Скачано ${GENERATED.length} бирок (ZIP).`, "ok");
}

function esc(s) { return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function setStatus(t, cls) { const e = $("status"); e.textContent = t; e.className = "status " + (cls || ""); }

window.addEventListener("DOMContentLoaded", () => {
  $("genBtn").addEventListener("click", generate);
  $("zipBtn").addEventListener("click", downloadZip);
  init();
});
