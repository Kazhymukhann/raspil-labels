#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Локальная синхронизация бирок.

Читает XML из локальной папки (по умолчанию `Cutting для ФРЦ`) и пишет готовые
папки `labels/<деталь>/labelN.emf` туда же. Данные деталей и количества берёт
из тех же Google-таблиц, что и Drive-синхронизация.
"""

import datetime
import hashlib
import os
import re
from pathlib import Path

import generate_labels as G
import sync_drive as D


HERE = Path(__file__).resolve().parent
XML_DIR = Path(os.environ.get("LOCAL_XML_DIR") or HERE / "Cutting для ФРЦ")
LABELS_DIR = Path(os.environ.get("LOCAL_LABELS_DIR") or XML_DIR / "labels")


def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_label(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and file_md5(path) == hashlib.md5(data).hexdigest():
        return False
    path.write_bytes(data)
    return True


def trash_extra_labels(folder, keep_count):
    for p in folder.glob("label*.emf"):
        m = re.fullmatch(r"label(\d+)\.emf", p.name, re.I)
        if m and int(m.group(1)) > keep_count:
            p.unlink()


def main():
    if not XML_DIR.exists():
        XML_DIR.mkdir(parents=True, exist_ok=True)
        print("XML folder created: %s" % XML_DIR)
        print("Put XML files there and run sync again.")

    xmls = sorted(XML_DIR.glob("*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
    print("Локальные XML: %d" % len(xmls))
    print("XML: %s" % XML_DIR)
    print("labels: %s" % LABELS_DIR)

    base = G.fetch_base()
    base_norm = G.build_part_lookup(base)
    job_rows = G.parse_job_rows(date_filter="all")
    today = datetime.date.today().strftime("%d.%m.%Y")

    made = skipped = missing = qty_from_xml = errors = 0
    total = len(xmls)
    for pos, xml_path in enumerate(xmls, 1):
        prefix = "[%d/%d] " % (pos, total)
        try:
            label_jobs = D.parse_xml_bytes(xml_path.read_bytes())
        except Exception as e:
            print("  %s! %s — ошибка чтения XML: %s" % (prefix, xml_path.name, e))
            errors += 1
            continue
        if not label_jobs:
            print("  %s- %s — в XML не найдены label-коды" % (prefix, xml_path.name))
            continue

        for job_pos, label_job in enumerate(label_jobs, 1):
            subprefix = prefix if len(label_jobs) == 1 else prefix + "[%d/%d] " % (job_pos, len(label_jobs))
            folder_name, n, material = label_job["folder"], label_job["count"], label_job["material"]
            pname = folder_name[:-(len(material) + 1)] if material and folder_name.endswith("-" + material) else folder_name
            part = G.find_part(base_norm, pname, material)
            if part is None:
                print("  %s? деталь не найдена в базе: %r (папка %s)" % (subprefix, pname, folder_name))
                missing += 1
                continue

            job_row = D.row_for_xml_folder(job_rows, pname)
            assigned = D.assign_labels(label_job, part, job_row, base_norm, today)
            if any(item["source"] == "XML" for item in assigned):
                qty_from_xml += 1

            out_dir = LABELS_DIR / folder_name
            changed = 0
            for item in assigned:
                data = D.emf_bytes(dict(item["part"], date=item["date"], qty=str(item["qty"])))
                if write_label(out_dir / ("label%d.emf" % item["num"]), data):
                    changed += 1
            trash_extra_labels(out_dir, n)

            if changed:
                print("  %s✓ %s: %d файлов, изменено %d (%s)"
                      % (subprefix, folder_name, n, changed, D.describe_assignment(assigned)))
                made += 1
            else:
                print("  %s= %s: без изменений (%d файлов)" % (subprefix, folder_name, n))
                skipped += 1

    print("Готово. Обновлено: %d, без изменений: %d, нет в базе: %d, кол-во взято из XML: %d, ошибок: %d"
          % (made, skipped, missing, qty_from_xml, errors))


if __name__ == "__main__":
    main()
