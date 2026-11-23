# Containerizes ctf-platform itself. No Docker-socket access needed at
# all -- this process only ever talks to the orchestrator over plain
# HTTP (PLATFORM_ORCHESTRATOR_URL), never touches Docker directly.
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Mount a volume at /app/data in compose and point
# PLATFORM_DATABASE_URL at sqlite:////app/data/platform.db so the DB
# survives `docker compose down`/up.
RUN mkdir -p /app/data /app/app/static/uploads

EXPOSE 9200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9200"]
