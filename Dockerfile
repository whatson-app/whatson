FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app

COPY pyproject.toml README.md ./
COPY whatson ./whatson
RUN pip install --no-cache-dir ".[anthropic,openai]"

VOLUME /data
EXPOSE 8430
CMD ["uvicorn", "whatson.app:app", "--host", "0.0.0.0", "--port", "8430"]
