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
import json
import os
import re
import sys
import time
from pathlib import Path

import generate_labels as G
import sync_drive as D


HERE = Path(__file__).resolve().parent
XML_DIR = Path(os.environ.get("LOCAL_XML_DIR") or HERE / "Cutting для ФРЦ")
LABELS_DIR = Path(os.environ.get("LOCAL_LABELS_DIR") or XML_DIR / "labels")
STATE_PATH = Path(os.environ.get("LOCAL_STATE_FILE") or HERE / ".sync_state.json")
STATE_VERSION = 3
WATCH_INTERVAL = int(os.environ.get("LOCAL_WATCH_INTERVAL") or "5")
TABLE_INTERVAL = int(os.environ.get("LOCAL_TABLE_INTERVAL") or "60")


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


def load_state():
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if state.get("version") == STATE_VERSION:
            return state
    except Exception:
        pass
    return {"version": STATE_VERSION, "xml": {}}


def save_state(state):
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_PATH)


def xml_stat(path):
    st = path.stat()
    return {"size": st.st_size, "mtime_ns": st.st_mtime_ns}


def stable_hash(obj):
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def part_sig(part):
    keys = ("name", "material", "cell", "prisadka", "length", "width",
            "thick", "tolk", "dk", "shk")
    return {k: str(part.get(k, "") if part else "") for k in keys}


def row_sig(row):
    if not row:
        return None
    return {
        "date": row.get("date", ""),
        "name": row.get("name", ""),
        "refs": [{"name": ref.get("name", ""), "qty": ref.get("qty")}
                 for ref in row.get("refs", [])],
    }


def assignment_sig(label_job, assigned, job_row):
    return stable_hash({
        "xml": label_job,
        "row": row_sig(job_row),
        "assigned": [{
            "num": item["num"],
            "qty": item["qty"],
            "date": item["date"],
            "source": item["source"],
            "part": part_sig(item["part"]),
        } for item in assigned],
    })


def xml_dir_signature():
    if not XML_DIR.exists():
        return ()
    out = []
    for path in XML_DIR.glob("*.xml"):
        try:
            st = path.stat()
        except OSError:
            continue
        out.append((path.name, st.st_size, st.st_mtime_ns))
    return tuple(sorted(out))


def run_once(reason="manual"):
    if not XML_DIR.exists():
        XML_DIR.mkdir(parents=True, exist_ok=True)
        print("XML folder created: %s" % XML_DIR)
        print("Put XML files there and run sync again.")

    xmls = sorted(XML_DIR.glob("*.xml"), key=lambda p: p.stat().st_mtime, reverse=True)
    if reason:
        print("Причина запуска: %s" % reason)
    print("Локальные XML: %d" % len(xmls))
    print("XML: %s" % XML_DIR)
    print("labels: %s" % LABELS_DIR)

    base = G.fetch_base()
    base_norm = G.build_part_lookup(base)
    job_rows = G.parse_job_rows(date_filter="all")
    job_index = D.build_job_row_index(job_rows)
    today = datetime.date.today().strftime("%d.%m.%Y")
    state = load_state()
    state_xml = state.setdefault("xml", {})

    made = skipped = cached = missing = qty_from_xml = errors = 0
    total = len(xmls)
    for pos, xml_path in enumerate(xmls, 1):
        prefix = "[%d/%d] " % (pos, total)
        rel_key = str(xml_path.relative_to(XML_DIR))
        stat = xml_stat(xml_path)
        cached_xml = state_xml.get(rel_key, {})
        xml_changed = cached_xml.get("stat") != stat
        try:
            if not xml_changed and cached_xml.get("label_jobs"):
                label_jobs = cached_xml["label_jobs"]
            else:
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

            job_row = D.row_for_xml_folder_indexed(job_index, pname)
            assigned = D.assign_labels(label_job, part, job_row, base_norm, today)
            if any(item["source"] == "XML" for item in assigned):
                qty_from_xml += 1

            sig = assignment_sig(label_job, assigned, job_row)
            job_key = folder_name
            prev_jobs = cached_xml.get("jobs", {}) if isinstance(cached_xml.get("jobs"), dict) else {}
            if not xml_changed and prev_jobs.get(job_key) == sig:
                cached += 1
                continue

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

            cached_xml.setdefault("jobs", {})[job_key] = sig

        cached_xml["stat"] = stat
        cached_xml["label_jobs"] = label_jobs
        state_xml[rel_key] = cached_xml

    known = set(str(p.relative_to(XML_DIR)) for p in xmls)
    for key in list(state_xml):
        if key not in known:
            state_xml.pop(key, None)
    save_state(state)

    print("Готово. Обновлено: %d, без изменений: %d, пропущено по кэшу: %d, нет в базе: %d, кол-во взято из XML: %d, ошибок: %d"
          % (made, skipped, cached, missing, qty_from_xml, errors))


def watch_loop():
    print("Watch mode: XML folder is checked every %d sec; tables every %d sec."
          % (WATCH_INTERVAL, TABLE_INTERVAL))
    last_sig = None
    last_table_run = 0
    while True:
        now = time.time()
        sig = xml_dir_signature()
        should_run = False
        reason = ""
        if sig != last_sig:
            should_run = True
            reason = "XML folder changed"
            last_sig = sig
        elif now - last_table_run >= TABLE_INTERVAL:
            should_run = True
            reason = "scheduled table check"

        if should_run:
            print("-" * 60)
            print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            run_once(reason)
            last_table_run = time.time()
            last_sig = xml_dir_signature()

        time.sleep(WATCH_INTERVAL)


def main():
    if "--watch" in sys.argv:
        watch_loop()
    else:
        run_once()


if __name__ == "__main__":
    main()
