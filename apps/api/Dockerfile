FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libmagic1 && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.lock.txt .
RUN pip install --no-cache-dir -r requirements.lock.txt
RUN useradd --create-home biographer
COPY --chown=biographer:biographer . .
USER biographer
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
