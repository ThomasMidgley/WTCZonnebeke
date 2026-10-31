#!/bin/sh
# Start van de container: database bijwerken, startinhoud aanmaken, nachtelijke back-up plannen, webserver starten.
set -e

mkdir -p "$DATA_DIR/media" "$DATA_DIR/backups"
python manage.py migrate --noinput
python manage.py seed_site

# Elke nacht om BACKUP_TIME (standaard 02:30) een back-up naar $DATA_DIR/backups.
(
  while true; do
    now=$(date +%s)
    next=$(date -d "$(date +%F) ${BACKUP_TIME:-02:30}" +%s)
    [ "$next" -le "$now" ] && next=$((next + 86400))
    sleep $((next - now))
    python manage.py backup_db || echo "Back-up mislukt"
  done
) &

# Planner voor de nachtelijke Cyql-sync (uur instelbaar bij Instellingen > Integraties).
python manage.py run_scheduler &

exec gunicorn config.wsgi \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-2}" \
  --threads 2 \
  --timeout 60 \
  --access-logfile - \
  --forwarded-allow-ips "*"
