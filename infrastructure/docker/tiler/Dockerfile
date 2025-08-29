# Use a stable base that always exists in Docker Hub
FROM python:3.11-slim-bookworm

# Allow passing a no-op ARG to easily bust cache if needed
ARG APT_BUSTER=0

# Faster, more reliable apt with retries; install GDAL runtime + Python bindings
# Notes:
# - python3-gdal pulls matching GDAL bindings for Python without compiling
# - libgdal-dev ensures headers/runtime pieces some tools expect
RUN set -eux; \
    apt-get -o Acquire::Retries=3 update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        gdal-bin libgdal-dev python3-gdal \
        ca-certificates curl \
    ; \
    pip3 install --no-cache-dir boto3; \
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*

# Optional envs (harmless on Debian, useful on some GDAL setups)
ENV GDAL_LIBRARY_PATH=/usr/lib/libgdal.so
ENV PROJ_LIB=/usr/share/proj
ENV CREATE_OPTS="TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2"

WORKDIR /app
COPY tiler.py /app/tiler.py

CMD ["python3", "/app/tiler.py"]
