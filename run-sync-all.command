#!/bin/zsh
cd "$(dirname "$0")" || exit 1

echo ""
echo "--- full sync $(date) ---" | tee -a sync-all.log
echo "Log: $(pwd)/sync-all.log"
echo ""

PYTHONUNBUFFERED=1 SYNC_DAYS=all python3 sync_drive.py 2>&1 | tee -a sync-all.log

echo ""
echo "Done. Press any key to close."
read -k 1
