#!/bin/bash
set -e

APP_DIR="$HOME/streamlit-scripts"
SERVICE_NAME="streamlit-scripts"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Detecta o caminho real do docker
DOCKER_BIN="$(which docker)"
if [ -z "$DOCKER_BIN" ]; then
    echo "Erro: docker não encontrado no PATH."
    exit 1
fi

echo "Docker encontrado em: $DOCKER_BIN"
echo "Configurando autostart para: $APP_DIR"

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
Environment="PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=${DOCKER_BIN} compose up -d --build
ExecStop=${DOCKER_BIN} compose down
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
