#!/bin/bash
# Daily backup of the SQLite database. On your own server, backups are your
# responsibility (unlike a managed cloud database) - this script keeps the
# last 30 days of copies. Add it to cron:
#
#   crontab -e
#   # then add this line to run it every night at 11pm:
#   0 23 * * * /home/brainwave/fdp2021/brainwave_academy/deploy/backup.sh

set -e

APP_DIR="/home/brainwave/fdp2021/brainwave_academy"
DB_FILE="$APP_DIR/brainwave.db"
BACKUP_DIR="/home/brainwave/backups"
DATE=$(date +%Y-%m-%d_%H%M)

mkdir -p "$BACKUP_DIR"
cp "$DB_FILE" "$BACKUP_DIR/brainwave_$DATE.db"

# Keep only the last 30 days of backups
find "$BACKUP_DIR" -name "brainwave_*.db" -mtime +30 -delete
