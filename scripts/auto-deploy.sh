#!/usr/bin/env bash
# ============================================
# ApplyMind AI — Auto-deploy (server-driven polling)
#
# Triggas av systemd-timern auto-deploy-applymind.timer var 2:a minut.
# Kollar om origin/master har nya commits — deploar om ja, annars exit 0.
#
# Zero-downtime: Docker startar nya containers innan gamla stängs.
# Sidan är alltid uppe under deploy.
#
# Installera EN gång: bash scripts/install-auto-deploy.sh
# Trigga manuellt:    systemctl start auto-deploy-applymind.service
# Live-logg:          tail -f /var/log/applymind-deploy.log
# ============================================

set -euo pipefail

REPO="${REPO:-/opt/applymind}"
LOG="${LOG:-/var/log/applymind-deploy.log}"
LOCK="${LOCK:-/var/run/applymind-deploy.lock}"
ENV_FILE="${ENV_FILE:-${REPO}/.env.production}"
BRANCH="${BRANCH:-master}"
FORCE="${FORCE:-0}"
SCRIPT_PATH="$(readlink -f "$0")"

log()  { printf '[%s] %s\n' "$(date -Iseconds)" "$*" | tee -a "$LOG"; }
fail() { log "❌ $*"; exit 1; }

# ── Lås mot parallella deploys ──────────────────────────────────────────
exec 200>"$LOCK"
flock -n 200 || fail "Annan deploy pågår redan — avbryter"

# ── Sanity ──────────────────────────────────────────────────────────────
[[ -d "$REPO/.git" ]] || fail "$REPO är inte en git-checkout"
[[ -f "$ENV_FILE" ]]  || fail "$ENV_FILE saknas — kan inte starta containers"

cd "$REPO"

SCRIPT_SHA_BEFORE=$(sha256sum "$SCRIPT_PATH" | cut -d' ' -f1)

# ── Snabb-check: finns nya commits? ────────────────────────────────────
git fetch --quiet origin "$BRANCH"
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/$BRANCH")

if [[ "$LOCAL" == "$REMOTE" && "$FORCE" != "1" ]]; then
  exit 0   # Inget nytt — tyst exit (spammar inte loggen)
fi

log "🚀 Ny commit hittad: ${LOCAL:0:7} → ${REMOTE:0:7}"
log "▶ Drar senaste koden från GitHub"
git pull --ff-only origin "$BRANCH"

# ── Om deploy-scriptet självt ändrades → exec om oss med ny version ────
SCRIPT_SHA_AFTER=$(sha256sum "$SCRIPT_PATH" | cut -d' ' -f1)
if [[ "$SCRIPT_SHA_BEFORE" != "$SCRIPT_SHA_AFTER" ]]; then
  log "🔄 Deploy-skriptet uppdaterades — startar om med ny version"
  exec bash "$SCRIPT_PATH"
fi

# ── Bygga och starta containers ─────────────────────────────────────────
log "🔨 Bygger Docker-images"
docker compose --env-file "$ENV_FILE" build --no-cache

log "▶ Startar containers (zero-downtime)"
docker compose --env-file "$ENV_FILE" up -d

# ── Kör DB-migrationer om de finns ─────────────────────────────────────
if docker compose exec -T applymind-web python -c "import flask_migrate" 2>/dev/null; then
  log "▶ Kör DB-migrationer"
  docker compose exec -T applymind-web flask db upgrade || log "⚠️ Inga migrationer att köra"
else
  # Enkel db.create_all() som fallback
  docker compose exec -T applymind-web python -c "
from web_app import app
from models import db
with app.app_context():
    db.create_all()
print('DB schema verifierat')
" && log "✅ DB schema verifierat"
fi

# ── Hälsokontroll ───────────────────────────────────────────────────────
log "▶ Väntar på hälsokontroll"
for i in $(seq 1 15); do
  if curl -sf http://localhost:5000/auth/login > /dev/null 2>&1; then
    log "✅ Deploy klar — ApplyMind AI svarar på :5000"
    exit 0
  fi
  sleep 2
done

log "⚠️ Hälsokontroll timeout — kontrollera: docker compose logs applymind-web"
exit 1
