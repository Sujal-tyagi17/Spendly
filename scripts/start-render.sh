#!/bin/sh
# Start the private API and the public dashboard in one container (used by the Dockerfile).
# If either process stops, stop the container so the host restarts it cleanly.
set -e

uvicorn api.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-access-log &
API_PID=$!

# Wait for the API before accepting traffic (up to 60 s).
i=0
until node -e "fetch('http://127.0.0.1:8000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"; do
  i=$((i + 1)); [ "$i" -ge 60 ] && { echo "API did not start"; exit 1; }
  sleep 1
done

cd web
node node_modules/next/dist/bin/next start -H 0.0.0.0 -p "${PORT:-10000}" &
WEB_PID=$!

# Exit as soon as either process exits.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do sleep 5; done
echo "A process stopped; exiting."
exit 1
