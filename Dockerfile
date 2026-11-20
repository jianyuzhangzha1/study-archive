FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock && useradd -u 10001 -m app && mkdir -p /data/uploads && chown -R app:app /data
COPY app ./app
COPY web ./web
USER app
ENV UPLOAD_DIR=/data/uploads
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
