FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

COPY apps ./apps
COPY packages ./packages
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./

RUN groupadd --gid 10001 enkip \
    && useradd --uid 10001 --gid enkip --home-dir /app enkip \
    && mkdir -p /var/lib/enkip/source /app/.cache/huggingface \
    && chown -R enkip:enkip /var/lib/enkip /app/.cache/huggingface

ENV STORAGE_ROOT=/var/lib/enkip/source \
    HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/huggingface

USER enkip

EXPOSE 8000

CMD [".venv/bin/python", "-m", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
