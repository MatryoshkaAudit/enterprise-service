FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY enterprise-service/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY protos /app/protos
RUN pip install --no-cache-dir -e /app/protos

COPY database /app/database
RUN pip install --no-cache-dir -e /app/database

COPY enterprise-service /app/enterprise-service
WORKDIR /app/enterprise-service

EXPOSE 8001 50051

CMD ["python", "-m", "app.main"]
