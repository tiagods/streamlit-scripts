FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Instala o rar para o patoolib conseguir criar/ler os arquivos
RUN echo "deb http://deb.debian.org/debian trixie main contrib non-free non-free-firmware" > /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian-security trixie-security main contrib non-free non-free-firmware" >> /etc/apt/sources.list && \
    apt-get update && apt-get install -y \
    rar \
    unrar \
    && rm -rf /var/lib/apt/lists/*

COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 8501

CMD ["streamlit", "run", "pages/Home.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true", "--browser.gatherUsageStats=false"]
