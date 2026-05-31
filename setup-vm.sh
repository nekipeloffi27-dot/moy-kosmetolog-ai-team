#!/usr/bin/env bash
#
# Bootstraps a fresh Ubuntu 24.04 VM for the AI team.
# Run as root or with sudo on a fresh Yandex Cloud VM.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/<your-user>/moy-kosmetolog-ai-team/main/setup-vm.sh | sudo bash
# or manually:
#   sudo bash setup-vm.sh

set -euo pipefail

echo "==> Updating apt"
apt-get update -y
apt-get upgrade -y

echo "==> Installing essentials"
apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    git \
    ufw \
    htop \
    vim

echo "==> Installing Docker"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable" \
    > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "==> Configuring firewall (allow SSH only — bot uses outbound long-polling)"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw --force enable

echo ""
echo "==> Done!"
echo ""
echo "Next steps:"
echo "  1. Clone the repo:"
echo "       git clone https://github.com/<owner>/moy-kosmetolog-ai-team.git"
echo "  2. cd moy-kosmetolog-ai-team"
echo "  3. cp .env.example .env  &&  vim .env   # fill in tokens"
echo "  4. docker compose up -d db redis"
echo "  5. docker compose run --rm bot alembic upgrade head"
echo "  6. docker compose up -d bot"
echo "  7. docker compose logs -f bot"
