FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose ports
# 5000-5003: FastAPI
# 50051-50053: gRPC
EXPOSE 5000 50051

# Run the FastAPI server
CMD ["uvicorn", "cache_node.app.main:app", "--host", "0.0.0.0", "--port", "5000"]
