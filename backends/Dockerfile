FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn[standard]==0.34.0
COPY service ./service
EXPOSE 8001 8002
