#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 python3 curl
systemctl enable --now docker
install -d -m 700 /opt/biographer
cd /opt/biographer
umask 077
python3 - <<'PYSETUP'
import urllib.request,json,base64,subprocess
headers={'Metadata-Flavor':'Google'}
r=urllib.request.Request('http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token',headers=headers)
token=json.load(urllib.request.urlopen(r))['access_token']
r=urllib.request.Request('https://secretmanager.googleapis.com/v1/projects/gen-lang-client-0362286623/secrets/biographer-runtime-env/versions/latest:access',headers={'Authorization':'Bearer '+token})
from pathlib import Path
Path('runtime.env').write_bytes(base64.b64decode(json.load(urllib.request.urlopen(r))['payload']['data']))
subprocess.run(['docker','login','-u','oauth2accesstoken','--password-stdin','https://us-east1-docker.pkg.dev'],input=token,text=True,check=True,stdout=subprocess.DEVNULL)
PYSETUP
cat > compose.yaml <<'COMPOSE'
name: biographer-cloud
x-api: &api
  image: us-east1-docker.pkg.dev/gen-lang-client-0362286623/biographer/api:interview-templates-20261028
  env_file: runtime.env
  restart: unless-stopped
services:
  sqlproxy:
    image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:2.14.1
    command: ["--address=0.0.0.0", "--port=5432", "gen-lang-client-0362286623:us-east1:biographer-db"]
    restart: unless-stopped
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes: [redis_data:/data]
    restart: unless-stopped
  clamav:
    image: clamav/clamav:stable
    volumes: [clamav_data:/var/lib/clamav]
    restart: unless-stopped
  temporal:
    image: temporalio/auto-setup:1.29.7
    environment:
      DB: postgres12
      DB_PORT: 5432
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PWD: ${POSTGRES_PWD}
      POSTGRES_SEEDS: sqlproxy
      DBNAME: temporal
      VISIBILITY_DBNAME: temporal_visibility
      SKIP_DB_CREATE: 'true'
      DEFAULT_NAMESPACE: default
    depends_on: [sqlproxy]
    restart: unless-stopped
  migrate:
    <<: *api
    command: sh -c 'alembic upgrade head && python -m app.bootstrap_interviews'
    restart: 'no'
    depends_on: [sqlproxy]
  api:
    <<: *api
    ports: ['10.42.0.10:8000:8000']
    depends_on:
      migrate: {condition: service_completed_successfully}
      redis: {condition: service_started}
      clamav: {condition: service_started}
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 20s
      timeout: 5s
      retries: 6
  worker:
    <<: *api
    command: python -m app.worker
    depends_on:
      migrate: {condition: service_completed_successfully}
      temporal: {condition: service_started}
      clamav: {condition: service_started}
volumes:
  redis_data:
  clamav_data:
COMPOSE
for attempt in $(seq 1 30); do
 if docker compose --env-file runtime.env pull; then break; fi
 sleep 20
done
docker compose --env-file runtime.env up -d sqlproxy redis clamav temporal
for attempt in $(seq 1 30); do
 if docker compose --env-file runtime.env run --rm migrate; then
  docker compose --env-file runtime.env up -d api worker
  exit 0
 fi
 sleep 10
done
exit 1
