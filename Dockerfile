FROM python:3.11-slim

# HF Spaces runs as user 1000 — set up correctly
RUN useradd -m -u 1000 user
WORKDIR /app

# Install Docker CLI (needed for subprocess docker commands)
RUN apt-get update && apt-get install -y \
    docker.io curl && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.runtime.txt .
RUN pip install --no-cache-dir -r requirements.runtime.txt

# Copy project files
COPY --chown=user . .

# Switch to non-root user
USER user

# HF Spaces MUST use port 7860
EXPOSE 7860

ENV PYTHONUNBUFFERED=1
ENV HOME=/home/user

CMD ["python3", "-m", "uvicorn", "server.app:app", \
     "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]
