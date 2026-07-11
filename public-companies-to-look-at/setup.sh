#!/bin/bash
# One-time setup: install dependencies and schedule daily cron job
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(which python3)"

echo "==> Installing Python dependencies..."
"$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "==> Copy .env.example to .env and fill in your credentials:"
echo "    cp $SCRIPT_DIR/.env.example $SCRIPT_DIR/.env"
echo "    nano $SCRIPT_DIR/.env"
echo ""

# Ask before installing cron
read -rp "Install daily cron job (runs at 6:30 PM ET / after market close)? [y/N] " yn
if [[ "$yn" =~ ^[Yy]$ ]]; then
    CRON_LINE="30 18 * * 1-5 cd $SCRIPT_DIR && $PYTHON $SCRIPT_DIR/sec_form4_checker.py >> $SCRIPT_DIR/form4.log 2>&1"
    # Append only if not already present
    ( crontab -l 2>/dev/null | grep -qF "sec_form4_checker" ) \
        && echo "Cron job already installed." \
        || ( (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab - && echo "Cron job installed." )
    echo "Runs Mon–Fri at 6:30 PM (your local time). Adjust time in crontab if needed."
    echo "View with: crontab -l"
fi

echo ""
echo "==> Test run (requires .env to be configured):"
echo "    python3 $SCRIPT_DIR/sec_form4_checker.py"
echo "    python3 $SCRIPT_DIR/sec_form4_checker.py 2024-11-15   # specific date"
