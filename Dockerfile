FROM python:3.11-slim

WORKDIR /app

# Install Docker CLI (for subprocess commands)
RUN apt-get update && apt-get install -y \
    docker.io curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.runtime.txt .
RUN pip install --no-cache-dir -r requirements.runtime.txt

COPY . .

EXPOSE 7860

ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "uvicorn", "server.app:app", \
     "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
