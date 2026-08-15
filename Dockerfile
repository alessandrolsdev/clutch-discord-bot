FROM python:3.11-slim

# Não gera .pyc e não bufferiza stdout (logs aparecem na hora em docker logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Runtime: ffmpeg (áudio) e libopus (voz do Discord).
# gcc/headers ficam só durante o build e saem na mesma camada.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libopus0 \
        libffi8 \
        ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev python3-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc libffi-dev python3-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY . .

# Usuário sem privilégios: o bot não precisa de root.
# /app/data e /app/temp são escritos em runtime.
RUN useradd --create-home --uid 1000 clutch && \
    mkdir -p /app/data /app/temp /app/logs /app/assets/sfx && \
    chown -R clutch:clutch /app

USER clutch

CMD ["python", "main.py"]
