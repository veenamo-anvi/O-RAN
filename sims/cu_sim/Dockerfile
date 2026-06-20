# build context: repo root  (docker build -f sims/cu_sim/Dockerfile .)
FROM python:3.11-slim

WORKDIR /app
COPY sims/cu_sim/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simlib ./simlib
COPY sims/cu_sim/cu_sim.py .

CMD ["python", "cu_sim.py"]
