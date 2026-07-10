# Stage 1: Build Frontend
FROM node:20-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Backend Runtime
FROM python:3.11-slim

ARG INCLUDE_LOCAL_MODELS=false
ARG LOCAL_MODELS_CONTEXT=docker/icu-models

WORKDIR /app

# Install system dependencies (curl for healthcheck, ffmpeg for audio preprocessing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements*.txt ./
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY backend/ ./
# Copy frontend build to backend static directory
COPY --from=frontend-build /frontend/dist ./static

# Optional offline model bundle. Put Chronos weights at:
#   docker/icu-models/chronos/{config.json,model.safetensors,...}
# Then build with:
#   docker build -f backend/Dockerfile --build-arg INCLUDE_LOCAL_MODELS=true -t icu-alert:chronos .
COPY ${LOCAL_MODELS_CONTEXT}/ /opt/icu-models/
RUN if [ "${INCLUDE_LOCAL_MODELS}" != "true" ]; then rm -rf /opt/icu-models; fi && \
    mkdir -p /opt/icu-models

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV APP_CONFIG_FILE=/app/config.yaml
ENV ICU_MODELS_DIR=/opt/icu-models

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
