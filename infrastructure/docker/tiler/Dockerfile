# Use Python image so pip is not "externally managed"
FROM python:3.11-slim

# Prevent interactive tzdata/etc.
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps (GDAL + tools). Keep the image lean.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      gdal-bin gdal-data gdal-plugins \
      curl jq ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Python deps (pip is OK on this image)
RUN pip install --no-cache-dir boto3

# Optional: create an unprivileged user
RUN useradd -m appuser
USER appuser
WORKDIR /app

# Copy your app code
# (adjust if your repo uses a different layout)
COPY tiler.py /app/tiler.py

# Default command; Step Functions/ECS can override with Command
CMD ["python", "/app/tiler.py"]
