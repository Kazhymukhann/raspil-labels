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


def list_children(svc, parent, only_folders=False, fields="id,name,mimeType,md5Checksum"):
    q = "'%s' in parents and trashed=false" % parent
    if only_folders:
        q += " and mimeType = '%s'" % FOLDER_MIME
    out, token = [], None
    while True:
        r = svc.files().list(q=q, fields="nextPageToken, files(%s)" % fields,
                             pageToken=token, pageSize=1000,
                             supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
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
    return svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute()["id"]


def download_bytes(svc, file_id):
    return svc.files().get_media(fileId=file_id, supportsAllDrives=True).execute()


def upload_label(svc, parent, name, data):
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/octet-stream", resumable=False)
    meta = {"name": name, "parents": [parent]}
    svc.files().create(body=meta, media_body=media, fields="id", supportsAllDrives=True).execute()


def parse_xml_bytes(b):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(b)
    folder, material, labels = None, "", set()
    for el in root.iter():
        if not material and el.get("material"):
            material = el.get("material").strip()
        code = (el.get("code") or "").strip()
        if "label" not in code.lower():
            continue
        comps = re.split(r"[\\/]", code)
        if len(comps) >= 2:
            folder = comps[-2]
        m = re.search(r"(label\d+)", comps[-1], re.I)
        if m:
            labels.add(m.group(1).lower())
    return folder, len(labels), material


def emf_bytes(part):
    buf = io.BytesIO()
    G.draw_label(part).convert("1").save(buf, format="BMP")
    bmp = buf.getvalue()
    return bmp + bmp                                  # две копии — формат станка


def raspil_dates(offline=False):
    """name -> последняя дата задания (для поля «Дата» на бирке)."""
    m = {}
    try:
        for j in G.parse_job(date_filter="all", offline=offline):
            prev = m.get(j["name"])
            m[j["name"]] = j["date"]                  # parse_job идёт по порядку; берём последнюю
    except Exception as e:
        print("  (РАСПИЛ недоступен: %s)" % e)
    return m


def main():
    if not all(os.environ.get(k) for k in
               ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")):
        print("Ключи Google не заданы (GitHub Secrets) — пропускаю. См. drive-auto/SYNC_SETUP.md")
        return
    svc = drive_service()
    base = G.fetch_base()                             # детали из Details List
    base_norm = {k.replace("/", "-"): v for k, v in base.items()}
    dates = raspil_dates()
    today = datetime.date.today().strftime("%d.%m.%Y")

    xmls = [f for f in list_children(svc, XML_FOLDER_ID)
            if f["name"].lower().endswith(".xml")]
    print("XML в источнике: %d" % len(xmls))

    made = skipped = missing = 0
    for x in xmls:
        try:
            folder, n, material = parse_xml_bytes(download_bytes(svc, x["id"]))
        except Exception as e:
            print("  ! %s — ошибка чтения XML: %s" % (x["name"], e)); continue
        if not folder or not n:
            continue
        pname = folder[:-(len(material) + 1)] if material and folder.endswith("-" + material) else folder
        part = base_norm.get(pname)
        if part is None:
            print("  ? деталь не найдена в базе: %r (папка %s)" % (pname, folder)); missing += 1; continue

        date = dates.get(part["name"]) or today
        data = emf_bytes(dict(part, date=date, qty=str(n)))
        digest = hashlib.md5(data).hexdigest()

        sub = get_or_create_subfolder(svc, LABELS_FOLDER_ID, folder)
        existing = list_children(svc, sub)
        same = (len(existing) == n and all(f.get("md5Checksum") == digest for f in existing))
        if same:
            skipped += 1; continue

        for f in existing:                            # очистить и переписать
            svc.files().delete(fileId=f["id"], supportsAllDrives=True).execute()
        for i in range(1, n + 1):
            upload_label(svc, sub, "label%d.emf" % i, data)
        print("  ✓ %s: %d бирок (Место %s, %s)" % (folder, n, part["cell"] or "—", date))
        made += 1

    print("Готово. Обновлено: %d, без изменений: %d, нет в базе: %d" % (made, skipped, missing))


if __name__ == "__main__":
    main()
