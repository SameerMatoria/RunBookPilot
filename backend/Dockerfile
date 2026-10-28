# API and worker image (the same image runs both; the command decides which).
# Build from the repo root:  docker build -f backend/Dockerfile .
FROM python:3.12-slim

# Docker CLI, so the worker can start sandbox containers through the host's Docker engine.
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
COPY sandbox/ /app/sandbox/

ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
