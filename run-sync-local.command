#!/bin/zsh
cd "$(dirname "$0")" || exit 1

echo ""
echo "--- local sync $(date) ---" | tee -a sync-local.log
echo "XML: $(pwd)/Cutting для ФРЦ"
echo "Labels: $(pwd)/Cutting для ФРЦ/labels"
echo "Log: $(pwd)/sync-local.log"
echo ""

PYTHONUNBUFFERED=1 python3 sync_local.py 2>&1 | tee -a sync-local.log

echo ""
echo "Done. Press any key to close."
read -k 1
