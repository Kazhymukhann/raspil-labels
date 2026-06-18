// ===================== PDF и печать из браузера =====================
const LBL_ASPECT = 884 / 1419;

function labelMM() {
  const w = (window.RASPIL_CONFIG && window.RASPIL_CONFIG.labelWidthMm) || 100;
  return { w, h: +(w * LBL_ASPECT).toFixed(2) };
}

// ---- PDF ----
function pdfDoc(list) {
  const { jsPDF } = window.jspdf;
  const { w, h } = labelMM();
  const orient = w >= h ? "landscape" : "portrait";
  const doc = new jsPDF({ orientation: orient, unit: "mm", format: [w, h], compress: true });
  list.forEach((g, i) => {
    if (i) doc.addPage([w, h], orient);
    doc.addImage(g.png, "PNG", 0, 0, w, h);
  });
  return doc;
}
function downloadPdf(g) {
  pdfDoc([g]).save(g.filename.replace(/\.emf$/, ".pdf"));
}
function downloadAllPdf(name) {
  if (!GENERATED.length) return;
  pdfDoc(GENERATED).save(name || "labels.pdf");
}

// ---- печать прямо из браузера (без скачивания) ----
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
    "@page{size:" + w + "mm " + h + "mm;margin:0}" +
    "html,body{margin:0;padding:0}" +
    "img{width:" + w + "mm;height:" + h + "mm;display:block}" +
    "img+img{page-break-before:always}" +
    "</style></head><body>" +
    list.map((g) => '<img src="' + g.png + '">').join("") +
    "</body></html>"
  );
  d.close();
  let fired = false;
  const go = () => {
    if (fired) return; fired = true;
    try { ifr.contentWindow.focus(); ifr.contentWindow.print(); } catch (e) {}
    setTimeout(() => ifr.remove(), 60000);
  };
  ifr.onload = () => setTimeout(go, 350);
  setTimeout(go, 900);          // запасной запуск, если onload уже прошёл
}
