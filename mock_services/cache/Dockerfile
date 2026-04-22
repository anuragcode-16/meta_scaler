FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn

COPY main.py .

EXPOSE 6379

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "6379"]
