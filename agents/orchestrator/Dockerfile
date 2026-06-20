FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

ENV CONTROLLER_URL=http://controller:8080 \
    PLANNING_URL=http://planning-api:8081 \
    INFLUX_URL=http://influxdb:8086 \
    ANTHROPIC_MODEL_NAME=sonnet
EXPOSE 8082

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8082"]
