# build context: repo root  (docker build -f agents/kpi_agent/Dockerfile .)
FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir numpy==2.1.3 influxdb-client==1.47.0 requests==2.32.3

COPY agents/kpi_agent/*.py ./
# pre-trained weights for fast boot; dataset baked in as fallback (train on first boot)
COPY agents/kpi_agent/kpi_model.pt ./kpi_model.pt
COPY data/dataset.csv /data/dataset.csv

ENV MODEL_PATH=/app/kpi_model.pt POLL_INTERVAL_SEC=30 CONTROLLER_URL=http://controller:8080

CMD ["python", "kpi_agent.py"]
