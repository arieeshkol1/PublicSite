# ---- Base image ----
# Use a valid GDAL tag (3.8.4 is available, 3.8.5 is not)
# You can bump to ubuntu-small-latest if you want rolling updates
FROM osgeo/gdal:ubuntu-small-3.8.4

# ---- System tools ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# ---- Python deps ----
RUN pip3 install --no-cache-dir boto3 awscli

# ---- Workdir ----
WORKDIR /app

# ---- Copy tiler code ----
COPY tiler.py /app/tiler.py

# ---- Default command ----
# Step Functions / ECS overrides this, so just keep python
CMD ["python3"]
