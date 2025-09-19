# Small-ish Ubuntu GDAL image; includes gdal_translate, Python
FROM osgeo/gdal:ubuntu-small-3.8.5

# Tools: awscli + boto3 for S3 upload; pip kept minimal
RUN apt-get update && \
    apt-get install -y --no-install-recommends python3-pip curl ca-certificates && \
    pip3 install --no-cache-dir boto3 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# App files
WORKDIR /app
COPY tiler.py /app/tiler.py

# Env for GDAL
ENV GDAL_LIBRARY_PATH=/usr/lib/libgdal.so
ENV PROJ_LIB=/usr/share/proj
ENV CREATE_OPTS="TILED=YES,BIGTIFF=IF_SAFER,COMPRESS=LZW,PREDICTOR=2"

# Default command (Step Functions can still override)
CMD ["python3", "/app/tiler.py"]