FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .
COPY static ./static

ENV CONTROLLER_URL=http://controller:8080 ORCHESTRATOR_URL=http://orchestrator:8082
EXPOSE 8083

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8083"]
