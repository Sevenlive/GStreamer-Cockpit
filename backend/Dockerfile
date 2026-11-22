FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    COCKPIT_DATA_DIR=/app/data \
    COCKPIT_RECORDINGS_DIR=/app/recordings

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-gi \
    python3-gst-1.0 \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gstreamer1.0-x \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Allow system PyGObject (gi) inside Python environment
ENV PYTHONPATH=/usr/lib/python3/dist-packages:/app

COPY app ./app

RUN mkdir -p /app/data /app/recordings

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
