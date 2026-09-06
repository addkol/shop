FROM python:3.14.7-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --require-hashes -r requirements.txt


FROM python:3.14.7-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8000

RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --create-home --shell /usr/sbin/nologin appuser

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appgroup . .

RUN mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appgroup /app/staticfiles /app/media

USER appuser

RUN ENVIRONMENT=build SECRET_KEY=container-build-only DEBUG=False ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health/live/', timeout=3)"

CMD ["sh", "-c", "python manage.py check --deploy --database default && exec gunicorn -c gunicorn.conf.py project.wsgi:application"]
