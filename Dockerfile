FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md BACKLOG.md alembic.ini ./
COPY src ./src
COPY migrations ./migrations

RUN pip install --no-cache-dir .

EXPOSE 8020

CMD ["sh", "-c", "alembic upgrade head && uvicorn reachpath.api:app --app-dir src --host 0.0.0.0 --port 8020"]
