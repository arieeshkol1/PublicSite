# infrastructure/lambda/docker/tiler/Dockerfile
# Stable base that doesn't disappear: Debian Bookworm Slim
FROM debian:bookworm-slim

# System deps + GDAL (CLI + Python bindings) + Python toolchain
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      gdal-bin python3-gdal python3-pip python3-venv ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Python libs used by the worker
RUN pip3 install --no-cache-dir boto3 awscli

# Workdir & app code
WORKDIR /app
COPY tiler.py /app/tiler.py

# ECS / Step Functions will override this via container command
CMD ["python3"]
