// ===================== НАСТРОЙКА ИСТОЧНИКОВ ДАННЫХ =====================
// Два источника:
//   • Задание (что и сколько пилим, дата) — вкладка РАСПИЛ;
//   • Детали (материал, место, размеры, кромка ТолК/ДК/ШК) — таблица Details List.
window.RASPIL_CONFIG = {
  // Задание
  raspilSheetId: "10nsX_nmzfPB7IyHM7oSqlj8wrdBn-zfoaKiMDZSccKI",
  raspilSheet:   "РАСПИЛ",

  // Детали (Details List, вкладка Main)
  baseSheetId:   "1pWEjfyh_MOm1U0zPpNIyp9DkqTk6ICcxS4W-8YqzKuI",
  baseGid:       "1918355371",

  // (необязательно) опубликованные CSV — если решите закрыть таблицы «по ссылке».
  // Если заполнить — будут использоваться вместо ID выше.
  raspilCsvUrl: "",
  baseCsvUrl:   "",

  // Автозаливка бирок в Google Drive (Apps Script web app). Вставь сюда URL после
  // развёртывания скрипта (см. drive-auto/SETUP.md). Пусто — кнопки заливки нет.
  driveUploadUrl: "",
};
