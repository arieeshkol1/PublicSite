# Make the GDAL base tag configurable (fallback to a known-good version)
ARG GDAL_TAG=ubuntu-small-3.8.4
FROM osgeo/gdal:${GDAL_TAG}

# Tools: boto3 for S3; keep image lean
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip curl ca-certificates && \
    pip3 install --no-cache-dir boto3 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# App files
WORKDIR /app
COPY tiler.py /app/tiler.py

# GDAL env
ENV GDAL_LIBRARY_PATH=/usr/lib/libgdal.so
ENV PROJ_LIB=/usr/share/proj
ENV CREATE_OPTS="TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2"

CMD ["python3", "/app/tiler.py"]
