// ============================ Логика приложения ============================
const CFG = window.RASPIL_CONFIG || {};
const $ = (id) => document.getElementById(id);

let BASE = {};          // имя детали -> поля
let BASE_LOOKUP = {};   // нормализованное имя детали -> поля
let JOB = [];           // текущее задание [{name, qty, date}]
let GENERATED = [];     // [{filename, bytes, part, png, card, search}]
let QUERY = "";         // строка поиска (фильтр карточек)
let ACTIVE_DATE = "";   // дата, по которой реально сформированы бирки

function todayStr() {
  const d = new Date();
  return d.getDate() + "." + (d.getMonth() + 1) + "." + d.getFullYear();
}

// ----- утилиты -----
function normDate(s) {
  s = String(s || "").trim();
  const p = s.split(/[.\-/]/);
  if (p.length === 3 && p.every((x) => /^\d+$/.test(x.trim())))
    return p.map((x) => String(parseInt(x, 10))).join(".");
  return s;
}
function normPartName(s) {
  return String(s || "")
    .trim()
    .replace(/\u00a0/g, " ")
    .replace(/\//g, "-")
    .replace(/[Хх]/g, "x")
    .replace(/\s+/g, " ")
    .toLocaleLowerCase("ru-RU");
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
async function fetchSheet(kind) {  // kind: 'base' (детали) | 'raspil' (задание)
  const url = kind === "base" ? CFG.baseCsvUrl : CFG.raspilCsvUrl;
  if (url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error("Не удалось загрузить CSV (" + r.status + ")");
    return parseCSV(await r.text());
  }
  if (kind === "base") {
    return await gvizJSONP(CFG.baseSheetId, CFG.baseGid
      ? { gid: CFG.baseGid } : { sheet: CFG.baseSheet || "Main" });
  }
  return await gvizJSONP(CFG.raspilSheetId, { sheet: CFG.raspilSheet || "РАСПИЛ" });
}

function gvizJSONP(sheetId, opts) {
  return new Promise((resolve, reject) => {
    if (!sheetId) { reject(new Error("Не задан ID таблицы (config.js)")); return; }
    const cb = "gviz_cb_" + Math.floor(performance.now()) + "_" +
               Math.random().toString(36).slice(2);
    const s = document.createElement("script");
    const cleanup = () => { delete window[cb]; s.remove(); };
    window[cb] = (resp) => { cleanup(); resolve(gvizToRows(resp)); };
    s.onerror = () => { cleanup(); reject(new Error("Нет доступа к таблице (JSONP)")); };
    const sel = opts.gid ? "gid=" + encodeURIComponent(opts.gid)
                         : "sheet=" + encodeURIComponent(opts.sheet);
    s.src = `https://docs.google.com/spreadsheets/d/${sheetId}/gviz/tq` +
            `?${sel}&tqx=responseHandler:${cb}`;
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
  const colN = (r, n) => idx[n] == null ? null : (idx[n] < r.length ? (r[idx[n]] || "").trim() : "");
  const map = {};
  const lookup = {};
  for (let k = 1; k < rows.length; k++) {
    const r = rows[k]; if (!r || !(r[0] || "").trim()) continue;
    const name = r[0].trim();
    map[name] = {
      name, material: col(r, "Материал"), cell: col(r, "Место"),
      prisadka: col(r, "Присадка"), length: col(r, "Длина"), width: col(r, "Ширина"),
      tolk: colN(r, "ТолК"), dk: colN(r, "ДК"), shk: colN(r, "ШК"),  // кромка (null = колонки нет)
    };
    lookup[normPartName(name)] = map[name];
  }
  BASE_LOOKUP = lookup;
  return map;
}

function parseJob(rows, dateFilter) {
  const h = rows[0];
  const dateI = Math.max(0, h.indexOf("Дата"));            // колонка A
  const nameI = h.indexOf("Наименование") >= 0 ? h.indexOf("Наименование") : 1; // B
  const qtyI = h.indexOf("кол-во") >= 0 ? h.indexOf("кол-во") : 2;              // C (запас)
  const d1I = h.indexOf("Д1");                             // E: «Имя-Nшт | ячейки»
  const reSht = /-\s*(\d+)\s*шт/;
  const want = dateFilter && dateFilter !== "all" ? normDate(dateFilter) : null;
  const order = [], acc = {};
  for (let k = 1; k < rows.length; k++) {
    const r = rows[k]; if (!r) continue;
    const rdate = (r[dateI] || "").trim(); if (!rdate) continue;
    if (want && normDate(rdate) !== want) continue;
    const name = (r[nameI] || "").trim(); if (!name) continue;
    // кол-во в партии — число Nшт из Д1 (столбец E); запасной вариант — «кол-во» (C)
    const m = d1I >= 0 && r[d1I] ? String(r[d1I]).match(reSht) : null;
    const qty = m ? parseInt(m[1], 10)
                  : (parseInt(String(r[qtyI] || "").replace(/[^\d]/g, ""), 10) || 0);
    const key = name + "|" + rdate;
    if (!(key in acc)) { acc[key] = { name, qty: 0, date: rdate }; order.push(key); }
    acc[key].qty += qty;                                   // суммируем, если деталь в нескольких строках за день
  }
  return order.map((k) => acc[k]);
}

function allDates(rows) {
  const h = rows[0];
  const dateI = Math.max(0, h.indexOf("Дата"));            // колонка A
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
    $("genBtn").disabled = false;
    await generate();                      // сразу формируем задание на сегодня
  } catch (e) {
    setStatus("Ошибка: " + e.message + ". Проверь config.js (источник данных).", "err");
  }
}

async function refresh() {                 // «Обновить»: перечитать таблицу и пересобрать
  setStatus("Обновляю данные из таблицы…");
  try {
    const [b, r] = await Promise.all([fetchSheet("base"), fetchSheet("raspil")]);
    BASE = buildBase(b); RASPIL_ROWS = r;
  } catch (e) { setStatus("Ошибка обновления: " + e.message, "err"); return; }
  await generate();
}

// ----- поток: генерация -----
async function generate() {
  const today = todayStr();
  let date = today, fellBack = false;
  JOB = parseJob(RASPIL_ROWS, date);
  if (!JOB.length) {                       // на сегодня нет — берём последнюю дату
    const dates = allDates(RASPIL_ROWS);
    if (dates.length) { date = dates[0]; JOB = parseJob(RASPIL_ROWS, date); fellBack = true; }
  }
  ACTIVE_DATE = date;
  $("hint").textContent = fellBack
    ? `На сегодня (${padDate2(today)}) задания нет. Показано последнее: ${padDate2(date)}.`
    : `Задание на сегодня: ${padDate2(date)}`;
  if (!JOB.length) { setStatus("Заданий в таблице не найдено.", "err"); $("searchbar").hidden = true; return; }
  setStatus(`Формирую бирки (${JOB.length})…`);
  const grid = $("grid"); grid.innerHTML = ""; GENERATED = [];
  let n = 0, skipped = [];
  for (const j of JOB) {
    const b = BASE[j.name] || BASE_LOOKUP[normPartName(j.name)];
    if (!b) { skipped.push(j.name); continue; }
    n++;
    const part = Object.assign({}, b, { date: j.date, qty: j.qty });
    const canvas = document.createElement("canvas");
    drawLabel(canvas, part);
    const g = {
      filename: `label${n}.emf`,
      bytes: makeEMF(canvas),
      png: canvas.toDataURL("image/png"),   // для превью, PDF и печати
      part,
    };
    GENERATED.push(g);
    grid.appendChild(makeCard(g));
    if (n % 5 === 0) await new Promise((r) => setTimeout(r)); // не вешать UI
  }
  enableExport(GENERATED.length > 0);
  const sb = $("searchbar");
  sb.hidden = GENERATED.length === 0;
  $("search").value = ""; QUERY = ""; applyFilter();
  let msg = `Готово: ${GENERATED.length} бирок. Можно распечатать или скачать (PDF / EMF / ZIP).`;
  if (skipped.length) msg += ` Нет в базе BASE (пропущены): ${skipped.join(", ")}.`;
  setStatus(msg, GENERATED.length ? "ok" : "err");
}

function makeCard(g) {
  const { part, filename, bytes, png } = g;
  const card = document.createElement("div"); card.className = "card";
  g.card = card;
  g.search = [part.name, part.cell, part.material].join(" ").toLowerCase();

  const img = document.createElement("img"); img.className = "thumb"; img.src = png;
  card.appendChild(img);

  const info = document.createElement("div"); info.className = "info";
  info.innerHTML = `<b>${esc(part.name)}</b>` +
    `<span>Место: <b>${esc(part.cell || "—")}</b> · ${esc(part.qty || "—")} шт</span>` +
    `<span>${esc(part.material || "")}</span>`;
  card.appendChild(info);

  const actions = document.createElement("div"); actions.className = "actions";
  // печать
  const aPr = btn("🖨 печать", () => printLabels([g]));
  // PDF
  const aPdf = btn("PDF", () => downloadPdf(g));
  // EMF (для станка)
  const aEmf = document.createElement("a");
  aEmf.className = "dl"; aEmf.textContent = "EMF";
  aEmf.href = URL.createObjectURL(new Blob([bytes], { type: "application/octet-stream" }));
  aEmf.download = filename;
  actions.append(aPr, aPdf, aEmf);
  card.appendChild(actions);
  return card;
}

function btn(text, onClick) {
  const a = document.createElement("a");
  a.className = "dl"; a.textContent = text; a.href = "#";
  a.addEventListener("click", (e) => { e.preventDefault(); onClick(); });
  return a;
}

async function downloadZip() {
  const list = visibleGenerated();
  if (!list.length) return;
  setStatus("Упаковываю в ZIP…");
  const zip = new JSZip();
  for (const g of list) zip.file(g.filename, g.bytes);
  const blob = await zip.generateAsync({ type: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "labels_" + padDate2(ACTIVE_DATE).replace(/\./g, "-") + ".zip";
  a.click();
  setStatus(`Скачано ${list.length} бирок (ZIP).`, "ok");
}

// ----- режим XML (раскрой BAZIS) -----
function parseXmlText(text) {
  const doc = new DOMParser().parseFromString(text, "application/xml");
  let folder = null, material = "", labels = new Set();
  doc.querySelectorAll("*").forEach((el) => {
    if (!material && el.getAttribute("material")) material = el.getAttribute("material").trim();
    const code = (el.getAttribute("code") || "").trim();
    if (!/label/i.test(code)) return;
    const comps = code.split(/[\\/]/);
    if (comps.length >= 2) folder = comps[comps.length - 2];
    const m = comps[comps.length - 1].match(/label\d+/i);
    if (m) labels.add(m[0].toLowerCase());
  });
  return { folder, count: labels.size, material };
}

let XML_FOLDER = "", XML_BYTES = null, XML_COUNT = 0;
async function handleXml(file) {
  const xr = $("xmlResult");
  try {
    const { folder, count, material } = parseXmlText(await file.text());
    if (!folder || !count) { xr.innerHTML = '<span class="err">В XML не найдены бирки (label-коды).</span>'; return; }
    const pname = (material && folder.endsWith("-" + material)) ? folder.slice(0, -(material.length + 1)) : folder;
    const part = BASE_LOOKUP[normPartName(pname)];
    if (!part) { xr.innerHTML = '<span class="err">Деталь не найдена в базе: ' + esc(pname) + '</span>'; return; }
    // кол-во НА БИРКЕ — из РАСПИЛ (Д1, столбец E) по имени; число файлов = count (из XML)
    const ri = (RASPIL_ROWS ? parseJob(RASPIL_ROWS, "all").find((j) => normPartName(j.name) === normPartName(part.name)) : null) || {};
    const p = Object.assign({}, part, { date: ri.date || todayStr(), qty: String(ri.qty == null ? count : ri.qty) });
    const canvas = document.createElement("canvas"); drawLabel(canvas, p);
    XML_FOLDER = folder; XML_BYTES = makeEMF(canvas); XML_COUNT = count;
    const img = document.createElement("img"); img.className = "thumb"; img.src = canvas.toDataURL("image/png");
    img.style.maxWidth = "320px";
    xr.innerHTML = "";
    xr.appendChild(img);
    const info = document.createElement("div"); info.className = "info";
    info.innerHTML = "<b>" + esc(part.name) + "</b><span>Папка: " + esc(folder) +
      "</span><span>Будет создано <b>" + count + "</b> бирок (label1…label" + count + ")</span>";
    xr.appendChild(info);
    const acts = document.createElement("div"); acts.className = "row buttons";
    if (CFG.driveUploadUrl) {
      const dbtn = document.createElement("button"); dbtn.className = "primary";
      dbtn.textContent = "☁ Залить в Drive (" + count + ")";
      const dstatus = document.createElement("div"); dstatus.className = "status";
      dbtn.onclick = () => uploadToDrive(dstatus);
      acts.appendChild(dbtn);
      const zbtn = document.createElement("button");
      zbtn.textContent = "⬇ Скачать папку (ZIP)"; zbtn.onclick = downloadXmlZip;
      acts.appendChild(zbtn);
      xr.appendChild(acts); xr.appendChild(dstatus);
    } else {
      const zbtn = document.createElement("button"); zbtn.className = "primary";
      zbtn.textContent = "⬇ Скачать папку (" + count + " бирок, ZIP)";
      zbtn.onclick = downloadXmlZip;
      xr.appendChild(zbtn);
    }
  } catch (e) { xr.innerHTML = '<span class="err">Ошибка XML: ' + esc(e.message) + '</span>'; }
}
async function downloadXmlZip() {
  if (!XML_BYTES) return;
  const zip = new JSZip();
  for (let i = 1; i <= XML_COUNT; i++) zip.file(XML_FOLDER + "/label" + i + ".emf", XML_BYTES);
  const blob = await zip.generateAsync({ type: "blob" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = XML_FOLDER + ".zip"; a.click();
}

function base64FromBytes(u8) {
  let s = ""; const chunk = 0x8000;
  for (let i = 0; i < u8.length; i += chunk) s += String.fromCharCode.apply(null, u8.subarray(i, i + chunk));
  return btoa(s);
}
async function uploadToDrive(statusEl) {
  if (!XML_BYTES || !CFG.driveUploadUrl) return;
  statusEl.textContent = "Заливаю в Drive…"; statusEl.className = "status";
  try {
    const payload = JSON.stringify({ folder: XML_FOLDER, count: XML_COUNT, b64: base64FromBytes(XML_BYTES) });
    // text/plain -> простой запрос без CORS-preflight; ответ непрозрачный (no-cors)
    await fetch(CFG.driveUploadUrl, { method: "POST", mode: "no-cors", credentials: "include",
      headers: { "Content-Type": "text/plain;charset=utf-8" }, body: payload });
    statusEl.textContent = "Отправлено в Drive: " + XML_COUNT + " бирок в папку «" + XML_FOLDER + "». Проверьте Drive.";
    statusEl.className = "status ok";
  } catch (e) {
    statusEl.textContent = "Ошибка заливки: " + e.message; statusEl.className = "status err";
  }
}

function visibleGenerated() {
  return QUERY ? GENERATED.filter((g) => g.search.includes(QUERY)) : GENERATED;
}
function applyFilter() {
  QUERY = $("search").value.trim().toLowerCase();
  let shown = 0;
  for (const g of GENERATED) {
    const ok = !QUERY || g.search.includes(QUERY);
    g.card.style.display = ok ? "" : "none";
    if (ok) shown++;
  }
  const c = $("count");
  c.textContent = QUERY ? `показано ${shown} из ${GENERATED.length}` : `всего ${GENERATED.length}`;
}

function esc(s) { return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function setStatus(t, cls) { const e = $("status"); e.textContent = t; e.className = "status " + (cls || ""); }

function enableExport(on) {
  $("zipBtn").disabled = !on;
  $("pdfBtn").disabled = !on;
  $("printBtn").disabled = !on;
}

window.addEventListener("DOMContentLoaded", () => {
  $("genBtn").addEventListener("click", refresh);
  $("zipBtn").addEventListener("click", downloadZip);
  $("pdfBtn").addEventListener("click", () =>
    downloadAllPdf("labels_" + padDate2(ACTIVE_DATE).replace(/\./g, "-") + ".pdf"));
  $("printBtn").addEventListener("click", () => printLabels(visibleGenerated()));
  $("search").addEventListener("input", applyFilter);
  $("xmlFile").addEventListener("change", (e) => { if (e.target.files[0]) handleXml(e.target.files[0]); });
  init();
});
