# Draft UI: Your intelligence, vaulted. index browser. Build from repo root: docker build -t draft-ui .
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8058

CMD ["python", "-m", "uvicorn", "ui.app:app", "--host", "0.0.0.0", "--port", "8058"]
