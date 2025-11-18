FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# We'll treat /app as the project root
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install backend dependencies (from backend/requirements.txt)
COPY backend/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# 👇 Copy the entire project so modules like market_structure_analyzer.py are available
COPY . /app

# Make sure Python can import from both /app and /app/backend
ENV PYTHONPATH=/app:/app/backend

EXPOSE 8000

# Entry point: backend/app/api/main.py  -> backend.app.api.main:app
CMD ["uvicorn", "backend.app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
