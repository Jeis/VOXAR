FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set environment variables for development
ENV JWT_SECRET=spatial_development_jwt_secret_please_change_in_production
ENV ENVIRONMENT=development
ENV LOG_LEVEL=INFO

EXPOSE 8080

CMD ["python", "-m", "uvicorn", "websocket_server:app", "--host", "0.0.0.0", "--port", "8080", "--reload"]