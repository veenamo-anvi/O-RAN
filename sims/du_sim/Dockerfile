# build context: repo root  (docker build -f sims/du_sim/Dockerfile .)
FROM python:3.11-slim

WORKDIR /app
COPY sims/du_sim/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY simlib ./simlib
COPY sims/du_sim/du_sim.py .

CMD ["python", "du_sim.py"]
