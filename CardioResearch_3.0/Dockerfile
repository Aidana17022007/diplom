FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements-tested.txt ./
RUN pip install --no-cache-dir -r requirements-tested.txt
COPY cardio/ ./cardio/
COPY assets/ ./assets/
COPY models/ ./models/
COPY reports/ ./reports/
COPY --from=frontend /app/frontend/dist ./frontend/dist
EXPOSE 8000
CMD ["python","-m","uvicorn","cardio.api:app","--host","0.0.0.0","--port","8000","--no-access-log"]
