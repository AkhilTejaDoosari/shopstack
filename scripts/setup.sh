#!/bin/bash
set -euo pipefail

# ShopStack — Docker setup for Ubuntu (AWS EC2)
# Run once on a fresh instance: bash setup.sh

echo ""
echo "================================================"
echo "  ShopStack — Docker Setup"
echo "================================================"
echo ""

# 1. Remove any old Docker installs
echo "[1/6] Removing old Docker versions if any..."
sudo apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

# 2. Update apt
echo "[2/6] Updating apt..."
sudo apt-get update -y

# 3. Install dependencies
echo "[3/6] Installing dependencies..."
sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release

# 4. Add Docker's official GPG key and repo
echo "[4/6] Adding Docker GPG key and repository..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# 5. Install Docker Engine + Compose plugin
echo "[5/6] Installing Docker Engine and Compose plugin..."
sudo apt-get update -y
sudo apt-get install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin

# 6. Add current user to docker group
echo "[6/6] Adding $USER to docker group..."
sudo usermod -aG docker "$USER"

echo ""
echo "================================================"
echo "  Setup complete."
echo ""
echo "  IMPORTANT: Group permissions need a new shell."
echo "  Run this now:"
echo ""
echo "    newgrp docker"
echo ""
echo "  Then start ShopStack:"
echo ""
echo "    docker compose up --build -d"
echo ""
echo "  This is normal Linux group behaviour."
echo "  Not a Docker bug. Not a setup error."
echo "================================================"
echo ""
