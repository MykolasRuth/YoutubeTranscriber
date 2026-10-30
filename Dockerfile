FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/data/huggingface \
    XDG_CACHE_HOME=/app/data/cache \
    VIDEOS_DB_PATH=/app/data/videos.db

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        ffmpeg \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && grep -vi '^rumps' requirements.txt > /tmp/requirements-docker.txt \
    && pip install -r /tmp/requirements-docker.txt

COPY . .
RUN mkdir -p /app/data

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
