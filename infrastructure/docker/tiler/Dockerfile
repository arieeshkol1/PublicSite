# Dockerfile
FROM debian:bookworm-slim

# System deps (GDAL + Python + venv + handy tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      gdal-bin python3 python3-venv python3-setuptools ca-certificates curl jq && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Create and activate a dedicated venv for Python packages
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Install Python deps into the venv (PEP 668-safe)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir boto3

# App files
WORKDIR /app
# COPY requirements.txt .       # if you have more deps, add them here
# RUN pip install -r requirements.txt
COPY tiler.py /app/tiler.py

# Run
ENTRYPOINT ["bash", "-lc", "python3 /app/tiler.py"]
