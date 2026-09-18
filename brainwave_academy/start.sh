#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  Brainwave Academy - Starting up"
echo "============================================"

if ! command -v python3 &> /dev/null; then
    echo ""
    echo "Python 3 was not found on this computer."
    echo "Please install Python 3.11 or later from https://www.python.org/downloads/"
    echo "Then run this script again (./start.sh)."
    echo ""
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo ""
    echo "First-time setup - this only happens once and may take a few minutes..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
else
    source .venv/bin/activate
fi

if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "Created a .env settings file with default values."
    echo "Edit it in a text editor to set a real SECRET_KEY and admin password before real use."
    echo ""
fi

echo ""
echo "Starting the server... your browser should open automatically."
echo "Keep this window open while you use the app. Press Ctrl+C to stop the server."
echo ""

( sleep 2 && (open http://localhost:5000 2>/dev/null || xdg-open http://localhost:5000 2>/dev/null || true) ) &

python run.py
