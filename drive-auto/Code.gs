// ============================================================
//  Автозаливка бирок в Google Drive (Google Apps Script)
//  Принимает от сайта папку + бирку + количество и раскладывает
//  label1..labelN в подпапку внутри папки "labels" на твоём Drive.
// ============================================================

// 1) Вставь сюда ID папки "labels" на твоём Google Drive.
//    ID — это часть ссылки на папку между /folders/ и следующим / или ?
//    Пример ссылки: https://drive.google.com/drive/folders/1AbCdEf... -> ID = 1AbCdEf...
const PARENT_FOLDER_ID = 'ВСТАВЬ_ID_ПАПКИ_labels';

function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const folderName = String(data.folder || '').trim();
    const count = parseInt(data.count, 10) || 0;
    if (!folderName || !count) throw new Error('нет folder/count');
    const bytes = Utilities.base64Decode(data.b64);

    const parent = DriveApp.getFolderById(PARENT_FOLDER_ID);

    // найти подпапку по имени или создать
    let sub;
    const it = parent.getFoldersByName(folderName);
    if (it.hasNext()) {
      sub = it.next();
      const old = sub.getFiles();           // убрать старые бирки, чтобы не дублировались
      while (old.hasNext()) old.next().setTrashed(true);
    } else {
      sub = parent.createFolder(folderName);
    }

    for (let i = 1; i <= count; i++) {
      sub.createFile(Utilities.newBlob(bytes, 'application/octet-stream', 'label' + i + '.emf'));
    }
    return ContentService
      .createTextOutput(JSON.stringify({ ok: true, folder: folderName, count: count }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: String(err) }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
