from __future__ import annotations

import torch
import torch.nn as nn


class SentimentLSTM(nn.Module):
    """Dual-head LSTM: direction classification (3-class) + magnitude regression.

    Architecture (V1 ~217K params):
        LSTM(35→128) → LSTM(128→128) → Dropout
        ├── direction head: Linear(128→3) + Softmax
        └── magnitude head: Linear(128→1)
    """

    def __init__(
        self,
        input_dim: int = 35,
        hidden_dim: int = 128,
        num_layers: int = 2,
        dropout: float = 0.2,
        num_direction_classes: int = 3,
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.dropout = nn.Dropout(dropout)
        self.direction_head = nn.Linear(hidden_dim, num_direction_classes)
        self.magnitude_head = nn.Linear(hidden_dim, 1)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        # x: (batch, seq_len, input_dim)
        _, (h_n, _) = self.lstm(x)
        features = self.dropout(h_n[-1])  # last layer, last timestep
        direction_logits = self.direction_head(features)
        magnitude = self.magnitude_head(features).squeeze(-1)
        return direction_logits, magnitude


class CombinedLoss(nn.Module):
    """α × CrossEntropy(direction) + (1 - α) × Huber(magnitude)."""

    def __init__(self, alpha: float = 0.5) -> None:
        super().__init__()
        self.alpha = alpha
        self.ce = nn.CrossEntropyLoss()
        self.huber = nn.HuberLoss()

    def forward(
        self,
        direction_logits: torch.Tensor,
        direction_labels: torch.Tensor,
        magnitude_pred: torch.Tensor,
        magnitude_true: torch.Tensor,
    ) -> torch.Tensor:
        loss_cls = self.ce(direction_logits, direction_labels)
        loss_reg = self.huber(magnitude_pred, magnitude_true)
        return self.alpha * loss_cls + (1.0 - self.alpha) * loss_reg


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
