# One image for both the API and the worker (different commands).
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# FFmpeg (ffmpeg + ffprobe) from Debian; no build tools left in the image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

RUN useradd --system --uid 10001 --home /nonexistent mediagate \
 && mkdir -p /data && chown mediagate /data
USER mediagate

ENV TEMP_DIR=/data
EXPOSE 8000 8081
ENTRYPOINT ["/usr/bin/tini", "--"]

# API (default). Worker: `python -m app.worker.main`
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*", "--no-server-header"]
