FROM python:3.12-slim

WORKDIR /app

# Install system dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

EXPOSE 8000

ENV APP_ENV=local
ENV DATABASE_PATH=/app/data/go-live.db

CMD ["python", "run_demo.py", "--host", "0.0.0.0", "--port", "8000"]
