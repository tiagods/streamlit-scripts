#!/bin/bash
set -e

APP_DIR="$HOME/streamlit-scripts"
SERVICE_NAME="streamlit-scripts"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
WRAPPER="/usr/local/bin/${SERVICE_NAME}-start.sh"

# ─── Detecta o docker ────────────────────────────────────────────────────────

DOCKER_BIN="$(which docker)"
if [ -z "$DOCKER_BIN" ]; then
    echo "Erro: docker não encontrado no PATH."
    exit 1
fi
echo "Docker encontrado em: $DOCKER_BIN"

# ─── Instala o compose plugin se não existir ─────────────────────────────────

if ! "$DOCKER_BIN" compose version &> /dev/null; then
    echo "Docker Compose plugin não encontrado. Instalando..."
    if command -v dnf &> /dev/null; then
        sudo dnf install -y docker-compose-plugin
    elif command -v apt-get &> /dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y docker-compose-plugin
    else
        echo "Erro: gerenciador de pacotes não suportado."
        exit 1
    fi
fi

# Verifica se o compose funciona como root
if ! sudo "$DOCKER_BIN" compose version &> /dev/null; then
    echo "Erro: 'sudo docker compose' não funciona. Verifique a instalação do plugin."
    sudo "$DOCKER_BIN" compose version
    exit 1
fi

echo "Docker Compose: $(sudo $DOCKER_BIN compose version)"
echo "Configurando autostart para: $APP_DIR"

# ─── Cria o script wrapper ───────────────────────────────────────────────────

sudo tee "$WRAPPER" > /dev/null <<EOF
#!/bin/bash
cd ${APP_DIR}
${DOCKER_BIN} compose \$@
EOF

sudo chmod +x "$WRAPPER"

# ─── Cria o serviço systemd ───────────────────────────────────────────────────

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Streamlit Scripts - Docker Compose
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=/bin/bash -c '${DOCKER_BIN} compose up -d --build'
ExecStop=/bin/bash -c '${DOCKER_BIN} compose down'
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

# ─── Ativa e inicia o serviço ─────────────────────────────────────────────────

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo ""
echo "Serviço '$SERVICE_NAME' configurado com sucesso."
echo ""
echo "Comandos úteis:"
echo "  sudo systemctl status $SERVICE_NAME"
echo "  sudo systemctl stop $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo journalctl -u $SERVICE_NAME -f"
