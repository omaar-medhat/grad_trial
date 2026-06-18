# PulseGuard AI - Backend Dockerfile
# ----------------------------------
# Slim Python image with just the Flask + Firebase deps (no torch).
# Heavy AI deps are intentionally out-of-image; the backend gracefully
# falls back to rule-based replies when transformers isn't available.

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=5000

WORKDIR /app

# System deps (curl for healthcheck).
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps first (better layer caching).
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt

# App code.
COPY backend /app/backend

# Non-root user.
RUN useradd --create-home --shell /bin/bash pulse \
    && chown -R pulse:pulse /app
USER pulse

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "60", "backend.app:app"]
