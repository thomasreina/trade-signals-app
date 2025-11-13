
# Minimal Python image
FROM python:3.11-slim

# Set TZ (optional)
ENV TZ=Europe/Madrid
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

# Workdir
WORKDIR /app

# Copy files
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY market_structure_analyzer.py .
COPY .env .

# Default command runs once; for cron scheduling, see README.md
CMD ["python", "market_structure_analyzer.py"]
