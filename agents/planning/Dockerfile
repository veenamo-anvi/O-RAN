FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
# CBC solver ships with pulp; coin-or-cbc not needed separately
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

ENV CONTROLLER_URL=http://controller:8080
EXPOSE 8081

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
