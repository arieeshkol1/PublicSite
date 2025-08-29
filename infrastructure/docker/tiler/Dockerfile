# Base: Debian slim; install GDAL CLI + Python bindings
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive PIP_ROOT_USER_ACTION=ignore

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      gdal-bin python3 python3-pip python3-setuptools ca-certificates curl jq && \
    pip3 install --no-cache-dir boto3 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# App code
WORKDIR /app
COPY tiler.py /app/tiler.py

# Default command (ECS also overrides with the same command)
CMD ["python3", "/app/tiler.py"]
