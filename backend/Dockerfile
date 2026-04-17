FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini main.py ./
COPY alembic ./alembic

RUN python -m pip install --upgrade pip \
    && python -m pip wheel --wheel-dir /tmp/wheels .

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/opt/venv/bin:$PATH"
ENV PORT=8000
ENV UVICORN_WORKERS=1

WORKDIR /app/backend

RUN python -m venv /opt/venv \
    && adduser --disabled-password --gecos "" --home /nonexistent --shell /usr/sbin/nologin appuser

COPY --from=builder /tmp/wheels /tmp/wheels
COPY --from=builder /app/backend /app/backend

RUN /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir --no-index --find-links=/tmp/wheels task-platform-backend \
    && rm -rf /tmp/wheels \
    && mkdir -p /var/lib/task-platform/uploads \
    && chown -R appuser:appuser /app/backend /var/lib/task-platform

USER appuser

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS}"]
