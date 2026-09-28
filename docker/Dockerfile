FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    cron \
    curl \
    fonts-roboto \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp

RUN pip install --no-cache-dir requests faster-whisper

WORKDIR /app

COPY sync_videos.py /app/sync_videos.py
COPY subtitles.py /app/subtitles.py
COPY glossary.json /app/glossary.json

RUN mkdir -p /app/videos /app/data /app/models

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
