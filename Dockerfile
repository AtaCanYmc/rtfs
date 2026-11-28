FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RTFS_CACHE_URL=redis://redis:6379/0

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir ".[api,redis]"

EXPOSE 8000

CMD ["rtfs", "serve", "--host", "0.0.0.0", "--port", "8000"]
