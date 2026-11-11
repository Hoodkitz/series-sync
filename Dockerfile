FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# ML-Modelle (Whisper/Torch) separat: docker build --build-arg ML=1
ARG ML=0
COPY requirements-ml.txt .
RUN if [ "$ML" = "1" ]; then pip install --no-cache-dir -r requirements-ml.txt; fi
COPY apps ./apps
COPY db_migrations ./db_migrations
COPY alembic.ini .
RUN useradd -r -u 10001 app && chown -R app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
