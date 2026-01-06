FROM python:3.11-slim

WORKDIR /app

# Adicionei libopus-dev aqui, essencial para voz
RUN apt-get update && \
    apt-get install -y ffmpeg git gcc libffi-dev libnacl-dev python3-dev libopus-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]