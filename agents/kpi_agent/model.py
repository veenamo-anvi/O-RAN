"""BiLSTM cell-health classifier.

2-layer bidirectional LSTM (hidden=64, dropout=0.25) over a 6-step, 9-feature window:
  LSTM(9 -> 64, 2 layers, bidirectional) -> last step (128) ->
  Linear(128->64) -> ReLU -> Dropout(0.25) -> Linear(64->5)
"""
from __future__ import annotations

import torch
import torch.nn as nn

SEQ_LEN = 6
N_FEATURES = 9
N_CLASSES = 5
CLASSES = ["NORMAL", "OVERLOAD", "UNDERLOAD", "SINR_LOW", "POWER_WASTE"]

# 9 features in fixed order (must match kpi_agent.extract_features + cell_kpi fields)
FEATURES = [
    "prb_dl_pct", "sinr_db", "connected_ues", "power_w", "packet_loss_pct",
    "dl_throughput_mbps", "cqi", "bler_pct", "latency_ms",
]

# fallback per-feature (min, range) covering 4G+5G hardware ranges; train.py overwrites
# these with values learned from the dataset and saves them alongside the weights.
FEATURE_NORM = {
    "prb_dl_pct": (0.0, 100.0), "sinr_db": (-5.0, 35.0), "connected_ues": (0.0, 900.0),
    "power_w": (50.0, 1000.0), "packet_loss_pct": (0.0, 8.0), "dl_throughput_mbps": (0.0, 3800.0),
    "cqi": (1.0, 15.0), "bler_pct": (0.0, 20.0), "latency_ms": (0.0, 150.0),
}


class KPIClassifier(nn.Module):
    def __init__(self, n_features: int = N_FEATURES, hidden: int = 64,
                 n_classes: int = N_CLASSES, dropout: float = 0.25) -> None:
        super().__init__()
        self.lstm = nn.LSTM(n_features, hidden, num_layers=2, batch_first=True,
                            bidirectional=True, dropout=dropout)
        self.head = nn.Sequential(
            nn.Linear(hidden * 2, 64), nn.ReLU(), nn.Dropout(dropout), nn.Linear(64, n_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)          # (B, T, 2*hidden)
        return self.head(out[:, -1, :])  # classify last timestep


def normalize(feats: list[float], norm: dict[str, tuple[float, float]]) -> list[float]:
    out = []
    for name, val in zip(FEATURES, feats):
        lo, rng = norm.get(name, (0.0, 1.0))
        rng = rng if rng else 1.0
        out.append((val - lo) / rng)
    return out
