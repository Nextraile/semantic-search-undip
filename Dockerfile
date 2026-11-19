FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/model-cache

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install -r requirements.txt

# New: Copying the API files
COPY backend.py search_routes.py search_schemas.py ./

RUN mkdir -p /app/eprints_vector_db /model-cache \
    && useradd --create-home --uid 10001 app \
    && chown -R app:app /app /model-cache

USER app

EXPOSE 8000

# New: Adding a container health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)" || exit 1

# Change: Running backend.py
CMD ["uvicorn", "backend:app", "--host", "0.0.0.0", "--port", "8000"]
