#!/usr/bin/env bash
# One-time setup for a fresh Ubuntu 24.04 Lightsail instance. Run as the
# default `ubuntu` user:
#
#   curl -fsSL https://raw.githubusercontent.com/Nithusikan01/Medical-Student-Assistant/main/deploy/lightsail/bootstrap.sh | bash
#
# or copy it over with scp and run `bash bootstrap.sh`. Safe to re-run.
set -euo pipefail

DEPLOY_USER="${SUDO_USER:-$USER}"
APP_DIR=/opt/msa

echo "==> Docker Engine + compose plugin"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$DEPLOY_USER"
sudo systemctl enable --now docker

echo "==> 2 GB swap file"
# Headroom for memory spikes (a large PDF ingest, a BM25 rebuild) so the
# kernel swaps instead of killing Postgres or the API.
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf >/dev/null
sudo sysctl --system >/dev/null

echo "==> Automatic security updates"
sudo apt-get update -y
sudo apt-get install -y unattended-upgrades
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> App directory $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown "$DEPLOY_USER:$DEPLOY_USER" "$APP_DIR"

cat <<EOF

Done. Next:
  1. Log out and back in, so the docker group membership applies.
  2. Create $APP_DIR/.env from deploy/lightsail/.env.example, then: chmod 600 $APP_DIR/.env
  3. Run the "Deploy backend" workflow from GitHub Actions.
EOF
