FROM python:3.12-slim

WORKDIR /app

# system deps kept minimal; pandas/numpy ship wheels
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# app code (analysis engine + pipeline + service). Raw data / .env are NOT copied;
# the seed CSV is mounted or provided via env in deployment.
COPY analysis/ ./analysis/
COPY pipeline/ ./pipeline/
COPY service/ ./service/

# persistent data (track library, jobs, uploads, results) lives on a mounted volume
ENV DATA_DIR=/data \
    TRACK_DB_PATH=/data/track_library.db \
    PORT=8000
EXPOSE 8000

# the worker runs in-process; a single uvicorn worker keeps the SQLite job store simple
CMD ["sh", "-c", "uvicorn app:app --app-dir service --host 0.0.0.0 --port ${PORT}"]
