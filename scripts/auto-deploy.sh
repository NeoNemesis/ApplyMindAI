#!/usr/bin/env bash
# ============================================
# ApplyMind AI — Auto-deploy med automatisk rollback
#
# Triggas av systemd-timern auto-deploy-applymind.timer var 2:a minut.
# Kollar om origin/master har nya commits — deploar om ja, annars exit 0.
#
# Säkerhet: om ny kod inte svarar på hälsokontroll inom 30s rullas
# den automatiskt tillbaka till föregående fungerande version.
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

log()     { printf '[%s] %s\n' "$(date -Iseconds)" "$*" | tee -a "$LOG"; }
fail()    { log "❌ $*"; exit 1; }
success() { log "✅ $*"; }

trap 'log "❌ Fel på rad $LINENO — kommando: $BASH_COMMAND"' ERR

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
  exit 0
fi

log "🚀 Ny commit hittad: ${LOCAL:0:7} → ${REMOTE:0:7}"

# Spara föregående SHA för eventuell rollback
PREV_SHA="$LOCAL"

log "▶ Drar senaste koden från GitHub (hard reset)"
git checkout -- .
git clean -fd --quiet
git reset --hard "origin/$BRANCH"

# ── Om deploy-scriptet självt ändrades → exec om med ny version ─────────
SCRIPT_SHA_AFTER=$(sha256sum "$SCRIPT_PATH" | cut -d' ' -f1)
if [[ "$SCRIPT_SHA_BEFORE" != "$SCRIPT_SHA_AFTER" ]]; then
  log "🔄 Deploy-skriptet uppdaterades — startar om med ny version"
  exec env FORCE=1 bash "$SCRIPT_PATH"
fi

# ── Hälsokontroll-funktion ───────────────────────────────────────────────
# VIKTIGT: containern publicerar INGEN port till hosten (expose, inte ports),
# så `curl localhost:5000` från hosten misslyckas ALLTID. Det orsakade en
# oändlig deploy→rollback-loop 2026-06-10 där containern återskapades varannan
# minut och taskit-edge tappade upstream-IP:n → 502 för alla användare.
# Fråga i stället Dockers egen healthcheck (curl INUTI containern, definierad
# i docker-compose.yml). Samma fix som föreslogs i PR #56.
wait_healthy() {
  local label="$1"
  log "▶ Väntar på hälsokontroll ($label)..."
  for i in $(seq 1 30); do
    status=$(docker inspect --format '{{.State.Health.Status}}' applymind-web 2>/dev/null || echo "absent")
    if [[ "$status" == "healthy" ]]; then
      return 0
    fi
    sleep 3
  done
  log "   Sista status: ${status:-okänd}"
  return 1
}

# ── Nginx-reload — taskit-edge cachear upstream-IP:n vid config-laddning ──
# Varje container-recreate ger applymind-web en ny IP på taskit-net; utan
# reload pekar nginx på den gamla → 502. Reload efter varje recreate.
reload_edge_nginx() {
  if docker exec taskit-edge nginx -s reload 2>/dev/null; then
    log "✅ taskit-edge nginx omladdad (ny upstream-IP)"
  else
    log "⚠️  Kunde inte ladda om taskit-edge nginx — kontrollera manuellt vid 502"
  fi
}

# ── Rollback-funktion ────────────────────────────────────────────────────
rollback() {
  log "🔄 RULLAR TILLBAKA till ${PREV_SHA:0:7}..."
  git checkout -- .
  git clean -fd --quiet
  git reset --hard "$PREV_SHA"
  docker compose --env-file "$ENV_FILE" up -d --force-recreate
  if wait_healthy "rollback"; then
    reload_edge_nginx
    log "✅ Rollback lyckades — appen är uppe med föregående version (${PREV_SHA:0:7})"
    log "⚠️  Ny kod (${REMOTE:0:7}) var trasig — undersök och fixa innan nästa deploy"
  else
    log "💥 KRITISKT: Rollback misslyckades också — manuell åtgärd krävs"
    log "   Kör: docker compose logs applymind-web --tail=100"
  fi
  exit 1
}

# ── Bygg bara om beroenden ändrats sedan föregående deploy ──────────────
# Jämför mot PREV_SHA (inte HEAD~1) för att fånga alla commits i pushen
DEPS_CHANGED=0
COMPOSE_CHANGED=0
git diff "${PREV_SHA}..HEAD" -- requirements.production.txt Dockerfile 2>/dev/null \
  | grep -q '^+' && DEPS_CHANGED=1 || true
git diff "${PREV_SHA}..HEAD" -- docker-compose.yml 2>/dev/null \
  | grep -q '^+' && COMPOSE_CHANGED=1 || true

if [[ "$DEPS_CHANGED" -gt 0 ]]; then
  log "📦 Beroenden ändrade — full rebuild"
  docker compose --env-file "$ENV_FILE" build
  docker compose --env-file "$ENV_FILE" up -d --wait || true
elif [[ "$COMPOSE_CHANGED" -gt 0 ]]; then
  log "🔄 docker-compose.yml ändrad — återskapar container"
  docker compose --env-file "$ENV_FILE" up -d --force-recreate
else
  log "⚡ Kod-ändring — återskapar container (binder om fil-mounts)"
  docker compose --env-file "$ENV_FILE" up -d --force-recreate
fi

# ── Hälsokontroll — rulla tillbaka om ny kod är trasig ───────────────────
if ! wait_healthy "ny version"; then
  log "❌ Ny kod (${REMOTE:0:7}) svarar inte — startar rollback"
  rollback
fi

# Containern är frisk men har ny IP efter recreate — ladda om edge-nginx
reload_edge_nginx

# ── DB-migrationer ───────────────────────────────────────────────────────
if docker compose exec -T applymind-web python -c "import flask_migrate" 2>/dev/null; then
  log "▶ Kör DB-migrationer"
  docker compose exec -T applymind-web flask db upgrade 2>/dev/null \
    || log "⚠️  Inga migrationer att köra (eller flask db ej konfigurerat)"
else
  docker compose exec -T applymind-web python -c "
from web_app import app
from models import db
with app.app_context():
    db.create_all()
print('DB schema verifierat')
" 2>/dev/null && log "✅ DB schema verifierat" || true
fi

success "Deploy klar — ApplyMind AI kör ${REMOTE:0:7}"
