# Works on Render, Railway, Fly.io, Google Cloud Run, Hugging Face Spaces (Docker) and similar hosts.
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend backend
COPY frontend frontend
WORKDIR /app/backend
EXPOSE 8000
# Hosts set $PORT; fall back to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
