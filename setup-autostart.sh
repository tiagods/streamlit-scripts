#!/bin/bash
set -e

APP_DIR="$HOME/streamlit-scripts"
SERVICE_NAME="streamlit-scripts"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
COMPOSE_BIN="$(which docker-compose)"

echo "Configurando autostart para: $APP_DIR"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Streamlit Scripts - Docker Compose
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=${COMPOSE_BIN} up -d --build
ExecStop=${COMPOSE_BIN} down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl start "$SERVICE_NAME"

echo "Serviço '$SERVICE_NAME' configurado com sucesso."
echo ""
echo "  sudo systemctl status $SERVICE_NAME"
echo "  sudo systemctl stop $SERVICE_NAME"
echo "  sudo systemctl restart $SERVICE_NAME"
echo "  sudo journalctl -u $SERVICE_NAME -f"
