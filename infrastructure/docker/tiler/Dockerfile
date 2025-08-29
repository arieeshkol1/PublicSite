# Stable base that’s always available in Docker Hub
FROM debian:bookworm-slim

# Install GDAL CLI + Python bindings + minimal tools
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      gdal-bin python3-gdal python3-pip ca-certificates curl && \
    pip3 install --no-cache-dir boto3 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# App
WORKDIR /app
COPY tiler.py /app/tiler.py

# Helpful envs (GDAL on Debian already finds libs/proj; these are harmless)
ENV GDAL_LIBRARY_PATH=/usr/lib/libgdal.so
ENV PROJ_LIB=/usr/share/proj
ENV CREATE_OPTS="TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2"

CMD ["python3", "/app/tiler.py"]
