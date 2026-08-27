FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHON=python3

WORKDIR /app

RUN groupadd --system apocalypt && useradd --system --gid apocalypt --home-dir /app apocalypt

COPY pyproject.toml requirements.txt README.md ./
COPY apocalyptbot ./apocalyptbot
COPY beast.py ./
RUN pip install --no-cache-dir .

COPY deploy ./deploy
RUN chmod +x deploy/*.sh \
    && mkdir -p state logs data \
    && chown -R apocalypt:apocalypt /app

USER apocalypt

HEALTHCHECK --interval=5m --timeout=10s --start-period=3m --retries=3 \
    CMD python3 -m apocalyptbot health --heartbeat state/heartbeat --max-age 900 || exit 1

ENTRYPOINT ["./deploy/run.sh"]
