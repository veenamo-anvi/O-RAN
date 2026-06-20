"""Train the BiLSTM from the synthetic dataset.

Builds 6-step sliding windows per cell (time-ordered), labels each window by its last row,
normalises features from the data, and trains with a WeightedRandomSampler so the
70/15/8/5/2 class imbalance does not dominate. Saves weights + norm to kpi_model.pt.
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
from collections import Counter, defaultdict

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset, WeightedRandomSampler

from model import CLASSES, FEATURES, SEQ_LEN, KPIClassifier

log = logging.getLogger("kpi.train")

CLASS_IDX = {c: i for i, c in enumerate(CLASSES)}


def _default_dataset() -> str:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "data", "dataset.csv")


def build_windows(dataset_path: str, limit_rows: int | None = None):
    by_cell: dict[str, list[tuple[list[float], str]]] = defaultdict(list)
    with open(dataset_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit_rows and i >= limit_rows:
                break
            feats = [float(row[name]) for name in FEATURES]
            by_cell[row["cell_id"]].append((feats, row["label"]))

    X, y = [], []
    for seq in by_cell.values():
        for i in range(len(seq) - SEQ_LEN + 1):
            window = seq[i:i + SEQ_LEN]
            X.append([w[0] for w in window])
            y.append(CLASS_IDX[window[-1][1]])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.int64)


def compute_norm(X: np.ndarray) -> dict[str, tuple[float, float]]:
    flat = X.reshape(-1, X.shape[-1])
    mins = flat.min(axis=0)
    maxs = flat.max(axis=0)
    return {name: (float(mins[i]), float(max(maxs[i] - mins[i], 1e-6))) for i, name in enumerate(FEATURES)}


def apply_norm(X: np.ndarray, norm: dict[str, tuple[float, float]]) -> np.ndarray:
    lo = np.array([norm[n][0] for n in FEATURES], dtype=np.float32)
    rng = np.array([norm[n][1] for n in FEATURES], dtype=np.float32)
    return (X - lo) / rng


def train(dataset_path: str, out_path: str, epochs: int = 8, batch_size: int = 256,
          limit_rows: int | None = None) -> dict:
    X, y = build_windows(dataset_path, limit_rows)
    if len(X) == 0:
        raise SystemExit("no training windows built — is the dataset present?")
    norm = compute_norm(X)
    Xn = apply_norm(X, norm)

    counts = Counter(y.tolist())
    log.info("windows=%d class_counts=%s", len(X), {CLASSES[k]: v for k, v in counts.items()})
    class_w = {c: 1.0 / counts.get(c, 1) for c in range(len(CLASSES))}
    sample_w = np.array([class_w[int(t)] for t in y], dtype=np.float64)
    sampler = WeightedRandomSampler(weights=sample_w, num_samples=len(sample_w), replacement=True)

    ds = TensorDataset(torch.from_numpy(Xn), torch.from_numpy(y))
    loader = DataLoader(ds, batch_size=batch_size, sampler=sampler)

    model = KPIClassifier()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    lossf = torch.nn.CrossEntropyLoss()
    model.train()
    for ep in range(epochs):
        total = 0.0
        for xb, yb in loader:
            opt.zero_grad()
            loss = lossf(model(xb), yb)
            loss.backward()
            opt.step()
            total += loss.item() * len(xb)
        log.info("epoch %d/%d loss=%.4f", ep + 1, epochs, total / len(ds))

    torch.save({"state_dict": model.state_dict(), "norm": norm, "classes": CLASSES}, out_path)
    log.info("saved model -> %s", out_path)
    return {"windows": len(X), "epochs": epochs, "out": out_path}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=_default_dataset())
    ap.add_argument("--out", default=os.environ.get("MODEL_PATH", "kpi_model.pt"))
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--limit-rows", type=int, default=None)
    args = ap.parse_args()
    train(args.dataset, args.out, args.epochs, limit_rows=args.limit_rows)


if __name__ == "__main__":
    main()
