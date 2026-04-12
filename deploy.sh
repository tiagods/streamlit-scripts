#!/bin/bash
set -e

REPO_URL="git@github.com:tiagods/streamlit-scripts.git"
APP_DIR="streamlit-scripts"

# ─── Detecta o gerenciador de pacotes ────────────────────────────────────────

if command -v dnf &> /dev/null; then
    PKG="sudo dnf install -y"
    PKG_UPDATE="sudo dnf update -y"
elif command -v apt-get &> /dev/null; then
    PKG="sudo apt-get install -y"
    PKG_UPDATE="sudo apt-get update -qq"
else
    echo "Gerenciador de pacotes não suportado (esperado dnf ou apt-get)."
    exit 1
fi

# ─── Funções de instalação ────────────────────────────────────────────────────

install_git() {
    echo "Instalando git..."
    $PKG_UPDATE
    $PKG git
}

install_docker() {
    echo "Instalando Docker..."
    if command -v dnf &> /dev/null; then
        sudo dnf install -y docker
        sudo systemctl enable docker
        sudo systemctl start docker
    else
        $PKG_UPDATE
        $PKG ca-certificates curl gnupg lsb-release

        sudo install -m 0755 -d /etc/apt/keyrings
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
            | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
        sudo chmod a+r /etc/apt/keyrings/docker.gpg

        echo \
            "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
            https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
            | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

        $PKG_UPDATE
        $PKG docker-ce docker-ce-cli containerd.io

        sudo systemctl enable docker
        sudo systemctl start docker
    fi

    sudo usermod -aG docker "$USER"
    echo "Docker instalado. Pode ser necessário fazer logout/login para usar sem sudo."
}

install_docker_compose() {
    echo "Instalando Docker Compose plugin..."
    if command -v dnf &> /dev/null; then
        sudo dnf install -y docker-compose-plugin
    else
        $PKG_UPDATE
        $PKG docker-compose-plugin
    fi
}

# ─── Verificações e instalações ───────────────────────────────────────────────

if ! command -v git &> /dev/null; then
    install_git
else
    echo "git: $(git --version)"
fi

if ! command -v docker &> /dev/null; then
    install_docker
else
    echo "docker: $(docker --version)"
fi

if ! docker compose version &> /dev/null; then
    install_docker_compose
else
    echo "docker compose: $(docker compose version)"
fi

# ─── Clone ou atualização do repositório ─────────────────────────────────────

if [ -d "$APP_DIR" ]; then
    echo "Repositório já existe. Atualizando..."
    cd "$APP_DIR"
    git pull
else
    echo "Clonando repositório..."
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ─── Deploy ───────────────────────────────────────────────────────────────────

echo "Subindo com docker compose..."
docker compose up -d --build

echo "Aplicação disponível em http://localhost:8501"
