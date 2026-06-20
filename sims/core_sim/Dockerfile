# build context: repo root  (docker build -f sims/core_sim/Dockerfile .)
FROM python:3.11-slim

WORKDIR /app
COPY sims/core_sim/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simlib ./simlib
COPY sims/core_sim/core_sim.py .

CMD ["python", "core_sim.py"]
