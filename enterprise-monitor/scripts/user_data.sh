#!/usr/bin/env bash
# ── NetWatch Enterprise — EC2 Bootstrap Script ────────────────────────────────
set -euo pipefail
exec > >(tee /var/log/netwatch-init.log | logger -t netwatch-init) 2>&1

echo "═══════════════════════════════════════════"
echo " NetWatch Enterprise — Server Bootstrap"
echo " $(date)"
echo "═══════════════════════════════════════════"

PROJECT_NAME="${project_name}"
APP_DIR="/opt/netwatch"

# ── 1. System update ──────────────────────────────────────────────────────────
apt-get update -y
apt-get upgrade -y
apt-get install -y curl git unzip jq htop

# ── 2. Install Docker ─────────────────────────────────────────────────────────
curl -fsSL https://get.docker.com | bash
usermod -aG docker ubuntu
systemctl enable docker
systemctl start docker

# ── 3. Install Docker Compose ─────────────────────────────────────────────────
COMPOSE_VERSION="2.27.0"
curl -fsSL \
  "https://github.com/docker/compose/releases/download/v${COMPOSE_VERSION}/docker-compose-linux-x86_64" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# ── 4. Clone project ──────────────────────────────────────────────────────────
mkdir -p "$APP_DIR"
# In production, replace with your real GitHub repo:
# git clone https://github.com/YOUR_USERNAME/enterprise-monitor.git "$APP_DIR"
chown -R ubuntu:ubuntu "$APP_DIR"

# ── 5. Create .env ────────────────────────────────────────────────────────────
cat > "$APP_DIR/.env" <<EOF
SECRET_KEY=$(openssl rand -hex 32)
GRAFANA_USER=admin
GRAFANA_PASSWORD=$(openssl rand -hex 16)
EOF

# ── 6. Firewall (UFW) ─────────────────────────────────────────────────────────
ufw --force enable
ufw allow OpenSSH
ufw allow 80/tcp
# Admin ports — restrict further if needed
ufw allow 3000/tcp
ufw allow 9090/tcp
ufw allow 9093/tcp

# ── 7. Systemd service ────────────────────────────────────────────────────────
cat > /etc/systemd/system/netwatch.service <<UNIT
[Unit]
Description=NetWatch Enterprise Monitoring Stack
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/local/bin/docker-compose up -d --build
ExecStop=/usr/local/bin/docker-compose down
TimeoutStartSec=300
User=ubuntu

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable netwatch.service

# ── 8. Launch (once app directory is populated via git/scp) ───────────────────
# Uncomment after deploying code:
# cd "$APP_DIR" && docker-compose up -d --build

echo "✓ Bootstrap complete — $(date)"
echo "Grafana password stored in $APP_DIR/.env"
