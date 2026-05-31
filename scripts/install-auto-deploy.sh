#!/usr/bin/env bash
# ============================================
# install-auto-deploy.sh — engångs-installer för ApplyMind AI
#
# Installerar systemd-timer som pollar GitHub var 2:a minut.
# Idempotent: kan köras om utan biverkningar.
#
# Kör EN gång på servern:
#   bash /opt/applymind/scripts/install-auto-deploy.sh
# ============================================

set -euo pipefail

REPO="${REPO:-/opt/applymind}"
SYSTEMD_DIR="/etc/systemd/system"

[[ "$EUID" -eq 0 ]] || { echo "Kräver root (sudo)." >&2; exit 1; }
[[ -d "$REPO/.git" ]] || { echo "$REPO är inte en git-checkout" >&2; exit 1; }

echo "▶ Sätter rättigheter på deploy-skript"
chmod +x "$REPO/scripts/auto-deploy.sh"

echo "▶ Skapar loggfil"
touch /var/log/applymind-deploy.log
chmod 644 /var/log/applymind-deploy.log

echo "▶ Installerar systemd-units"
install -m 0644 "$REPO/deploy/systemd/auto-deploy-applymind.service" \
                "$SYSTEMD_DIR/auto-deploy-applymind.service"
install -m 0644 "$REPO/deploy/systemd/auto-deploy-applymind.timer" \
                "$SYSTEMD_DIR/auto-deploy-applymind.timer"

echo "▶ Reloadar systemd och startar timer"
systemctl daemon-reload
systemctl enable --now auto-deploy-applymind.timer

echo ""
echo "✅ Auto-deploy installerat!"
echo ""
echo "Status:         systemctl status auto-deploy-applymind.timer"
echo "Senaste deploy: systemctl status auto-deploy-applymind.service"
echo "Live-logg:      tail -f /var/log/applymind-deploy.log"
echo "Trigga nu:      systemctl start auto-deploy-applymind.service"
echo "Pausa:          systemctl stop auto-deploy-applymind.timer"
