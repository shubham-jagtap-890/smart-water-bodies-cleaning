# ---- stage 1: build the React frontend ----
FROM node:20-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- stage 2: Flask API + built frontend ----
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 STATIC_DIR=/app/frontend/dist
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist /app/frontend/dist
# 1 worker + threads keeps RAM under the 512 MB free-tier limit
CMD gunicorn app:app --bind 0.0.0.0:${PORT:-10000} --workers 1 --threads 4 --timeout 60
