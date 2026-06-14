FROM python:3.11-slim

WORKDIR /app

# Install ffmpeg (required by pydub for audio processing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure Python output is sent straight to the logs (no buffering)
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn","app:app","-b","0.0.0.0:8080","--workers=1","--threads=1","--timeout=300"]
