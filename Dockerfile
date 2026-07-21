FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md BACKLOG.md ./
COPY src ./src

RUN pip install --no-cache-dir .

EXPOSE 8020

CMD ["uvicorn", "reachpath.api:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8020"]
