# ---- Base (configurable) ----
# Use a rolling tag that exists; you can pin via build-arg from CDK if needed.
ARG GDAL_TAG=ubuntu-small-latest
FROM osgeo/gdal:${GDAL_TAG}

# ---- System tools ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# ---- Python deps ----
RUN pip3 install --no-cache-dir boto3 awscli

# ---- Workdir ----
WORKDIR /app

# ---- App code ----
COPY tiler.py /app/tiler.py

# ECS/StepFunctions will override command; keep python default
CMD ["python3"]
