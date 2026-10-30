# Website WTC Zonnebeke: één container met Django/Wagtail en SQLite.
# Gebouwd voor linux/arm64 (Raspberry Pi) en linux/amd64.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data \
    TZ=Europe/Brussels

RUN apt-get update \
    && apt-get install -y --no-install-recommends libjpeg62-turbo zlib1g libwebp7 tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 wtc

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=wtc:wtc . .
RUN SECRET_KEY=build DEBUG=0 python manage.py collectstatic --noinput \
    && mkdir -p /data && chown wtc:wtc /data

USER wtc
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/gezond/')"

ENTRYPOINT ["./docker-entrypoint.sh"]
