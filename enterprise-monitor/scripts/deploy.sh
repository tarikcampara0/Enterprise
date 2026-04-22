#!/usr/bin/env bash
# ── NetWatch Enterprise — Deployment Script ───────────────────────────────────
# Usage:
#   ./scripts/deploy.sh local       # local Docker Compose
#   ./scripts/deploy.sh aws         # push to AWS via SSH
#   ./scripts/deploy.sh aws-setup   # provision AWS with Terraform

set -euo pipefail
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
die()  { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

MODE="${1:-local}"

# ── Check prereqs ─────────────────────────────────────────────────────────────
check_prereqs() {
  for cmd in docker docker-compose; do
    command -v "$cmd" &>/dev/null || die "$cmd not found. Install it first."
  done
  log "Prerequisites OK"
}

# ── Local deployment ──────────────────────────────────────────────────────────
deploy_local() {
  log "Deploying NetWatch locally..."

  # Create .env if missing
  if [[ ! -f .env ]]; then
    warn ".env not found, creating from .env.example"
    cp .env.example .env
  fi

  log "Building images..."
  docker-compose build --no-cache

  log "Starting services..."
  docker-compose up -d

  log "Waiting for services to be healthy..."
  sleep 10

  # Health check
  for svc in "http://localhost:5000/health" "http://localhost:9090/-/ready"; do
    if curl -sf "$svc" &>/dev/null; then
      log "$svc — OK"
    else
      warn "$svc — not responding yet (may still be starting)"
    fi
  done

  echo ""
  echo -e "${GREEN}═══════════════════════════════════════════${NC}"
  echo -e "${GREEN} NetWatch Enterprise is running!${NC}"
  echo -e "${GREEN}═══════════════════════════════════════════${NC}"
  echo "  Dashboard:    http://localhost:5000"
  echo "  Prometheus:   http://localhost:9090"
  echo "  Grafana:      http://localhost:3000"
  echo "  Alertmanager: http://localhost:9093"
  echo ""
  echo "  View logs:  docker-compose logs -f"
  echo "  Stop:       docker-compose down"
}

# ── AWS deployment via SSH ────────────────────────────────────────────────────
deploy_aws() {
  [[ -f terraform/terraform.tfstate ]] || \
    die "No Terraform state found. Run: ./scripts/deploy.sh aws-setup first."

  EC2_IP=$(cd terraform && terraform output -raw public_ip)
  KEY=$(cd terraform && terraform output -raw ssh_command | awk '{print $3}' | sed 's/~\///')
  KEY_PATH="$HOME/$KEY"

  log "Syncing code to EC2 at $EC2_IP..."
  rsync -avz --exclude='.git' --exclude='terraform' \
    -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
    ./ "ubuntu@${EC2_IP}:/opt/netwatch/"

  log "Running docker-compose on EC2..."
  ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no "ubuntu@${EC2_IP}" \
    "cd /opt/netwatch && docker-compose pull && docker-compose up -d --build"

  echo ""
  echo -e "${GREEN}Deployed to AWS!${NC}"
  echo "  Dashboard:    http://$EC2_IP"
  echo "  Prometheus:   http://$EC2_IP:9090"
  echo "  Grafana:      http://$EC2_IP:3000"
}

# ── Terraform provision ───────────────────────────────────────────────────────
aws_setup() {
  command -v terraform &>/dev/null || die "Terraform not found."
  cd terraform
  log "Initialising Terraform..."
  terraform init
  log "Planning..."
  terraform plan -out=tfplan
  warn "Review the plan above, then press Enter to apply (Ctrl+C to cancel)"
  read -r
  terraform apply tfplan
}

# ── Main ──────────────────────────────────────────────────────────────────────
check_prereqs
case "$MODE" in
  local)     deploy_local ;;
  aws)       deploy_aws ;;
  aws-setup) aws_setup ;;
  *)         die "Unknown mode: $MODE. Use: local | aws | aws-setup" ;;
esac
