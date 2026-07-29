FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN groupadd --gid 10001 dnd-manager \
    && useradd --uid 10001 --gid dnd-manager --no-create-home dnd-manager

COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

COPY --chown=dnd-manager:dnd-manager . .
RUN mkdir -p /data/portraits \
    && chown -R dnd-manager:dnd-manager /data \
    && chmod +x /app/deploy/docker-entrypoint.sh

USER dnd-manager

ENV DATABASE_PATH=/data/dnd_manager.sqlite3 \
    PORTRAIT_PATH=/data/portraits \
    PORT=8000

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=3)"]

ENTRYPOINT ["/app/deploy/docker-entrypoint.sh"]
