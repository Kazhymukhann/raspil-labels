// ===================== PDF и печать из браузера (раскладка на A4) =====================
const LBL_ASPECT = 884 / 1419;
const PAGE_W = 210, PAGE_H = 297, MARGIN = 10, GAP = 6;   // A4, мм

function labelMM() {
  const w = (window.RASPIL_CONFIG && window.RASPIL_CONFIG.labelWidthMm) || 100;
  return { w, h: +(w * LBL_ASPECT).toFixed(2) };
}

// ---- PDF: бирки сеткой на листах A4 ----
function pdfDoc(list) {
  const { jsPDF } = window.jspdf;
  const { w, h } = labelMM();
  const doc = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4", compress: true });
  const cols = Math.max(1, Math.floor((PAGE_W - 2 * MARGIN + GAP) / (w + GAP)));
  const rows = Math.max(1, Math.floor((PAGE_H - 2 * MARGIN + GAP) / (h + GAP)));
  const per = cols * rows;
  const offX = (PAGE_W - (cols * w + (cols - 1) * GAP)) / 2;   // центрируем сетку
  list.forEach((g, i) => {
    const idx = i % per;
    if (i && idx === 0) doc.addPage("a4", "portrait");
    const r = Math.floor(idx / cols), c = idx % cols;
    doc.addImage(g.png, "PNG", offX + c * (w + GAP), MARGIN + r * (h + GAP), w, h);
  });
  return doc;
}
function downloadPdf(g) {
  pdfDoc([g]).save(g.filename.replace(/\.emf$/, ".pdf"));
}
function downloadAllPdf(name) {
  const list = visibleGenerated();
  if (!list.length) return;
  pdfDoc(list).save(name || "labels.pdf");
}

// ---- печать из браузера: бирки сеткой на A4 (по центру) ----
function printLabels(list) {
  if (!list.length) return;
  const { w, h } = labelMM();
  const ifr = document.createElement("iframe");
  ifr.setAttribute("aria-hidden", "true");
  ifr.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(ifr);
  const d = ifr.contentWindow.document;
  d.open();
  d.write(
    '<!DOCTYPE html><html><head><meta charset="utf-8"><style>' +
    "@page{size:A4;margin:" + MARGIN + "mm}" +
    "html,body{margin:0;padding:0}" +
    ".sheet{text-align:center;font-size:0}" +
    ".sheet img{width:" + w + "mm;height:" + h + "mm;display:inline-block;vertical-align:top;" +
    "margin:" + (GAP / 2) + "mm;break-inside:avoid;page-break-inside:avoid}" +
    "</style></head><body><div class=\"sheet\">" +
    list.map((g) => '<img src="' + g.png + '">').join("") +
    "</div></body></html>"
  );
  d.close();
  let fired = false;
  const go = () => {
    if (fired) return; fired = true;
    try { ifr.contentWindow.focus(); ifr.contentWindow.print(); } catch (e) {}
    setTimeout(() => ifr.remove(), 60000);
  };
  ifr.onload = () => setTimeout(go, 400);
  setTimeout(go, 1000);          // запасной запуск
}
