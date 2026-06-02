"""
AutoEncoder anomaly detector using PyTorch.
Reconstruction error is used as the anomaly score.
"""

import hashlib
import pickle
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

MODEL_DIR = Path(__file__).parent / "registry"
MODEL_DIR.mkdir(exist_ok=True)

NUMERIC_FEATURES = [
    "DMBTR",
    "WRBTR",
    "days_to_pay",
    "hour_of_entry",
    "vendor_payment_count_30d",
    "amount_deviation_from_vendor_mean",
    "is_round_amount",
    "days_since_vendor_created",
    "po_invoice_ratio",
]


def _build_features(bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame) -> pd.DataFrame:
    from .isolation_forest import _build_features as _bf
    return _bf(bsak, bkpf, lfa1)


class _AENetwork(nn.Module):
    def __init__(self, input_dim: int, latent_dim: int = 4):
        super().__init__()
        hidden = max(latent_dim * 4, input_dim // 2)
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, hidden),
            nn.ReLU(),
            nn.BatchNorm1d(hidden),
            nn.Linear(hidden, latent_dim * 2),
            nn.ReLU(),
            nn.Linear(latent_dim * 2, latent_dim),
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, latent_dim * 2),
            nn.ReLU(),
            nn.Linear(latent_dim * 2, hidden),
            nn.ReLU(),
            nn.BatchNorm1d(hidden),
            nn.Linear(hidden, input_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)


class AutoEncoderDetector:
    def __init__(
        self,
        latent_dim: int = 4,
        epochs: int = 50,
        batch_size: int = 256,
        lr: float = 1e-3,
        threshold_percentile: float = 97.0,
        device: Optional[str] = None,
    ):
        self.latent_dim = latent_dim
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.threshold_percentile = threshold_percentile
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.network: Optional[_AENetwork] = None
        self.scaler: Optional[StandardScaler] = None
        self.threshold: float = 0.0
        self.feature_names: List[str] = NUMERIC_FEATURES
        self.model_hash: str = ""
        self.version: str = ""

    def fit(self, bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame) -> "AutoEncoderDetector":
        features_df = _build_features(bsak, bkpf, lfa1)
        X = features_df[self.feature_names].fillna(0).values.astype(np.float32)

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X).astype(np.float32)

        self.network = _AENetwork(input_dim=X_scaled.shape[1], latent_dim=self.latent_dim).to(self.device)
        optimizer = torch.optim.Adam(self.network.parameters(), lr=self.lr)
        criterion = nn.MSELoss()

        tensor = torch.tensor(X_scaled)
        loader = DataLoader(TensorDataset(tensor), batch_size=self.batch_size, shuffle=True)

        self.network.train()
        for epoch in range(self.epochs):
            epoch_loss = 0.0
            for (batch,) in loader:
                batch = batch.to(self.device)
                recon = self.network(batch)
                loss = criterion(recon, batch)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                epoch_loss += loss.item()
            if (epoch + 1) % 10 == 0:
                print(f"  AE Epoch {epoch+1}/{self.epochs} — loss: {epoch_loss/len(loader):.6f}")

        # Compute threshold on training data
        errors = self._reconstruction_errors(X_scaled)
        self.threshold = float(np.percentile(errors, self.threshold_percentile))
        return self

    def _reconstruction_errors(self, X_scaled: np.ndarray) -> np.ndarray:
        self.network.eval()
        tensor = torch.tensor(X_scaled.astype(np.float32)).to(self.device)
        with torch.no_grad():
            recon = self.network(tensor)
        errors = torch.mean((tensor - recon) ** 2, dim=1).cpu().numpy()
        return errors

    def predict(
        self, bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Returns (labels, scores). Label 1 = anomaly, 0 = normal."""
        features_df = _build_features(bsak, bkpf, lfa1)
        X = features_df[self.feature_names].fillna(0).values.astype(np.float32)
        X_scaled = self.scaler.transform(X).astype(np.float32)
        errors = self._reconstruction_errors(X_scaled)
        labels = (errors > self.threshold).astype(int)
        return labels, errors

    def predict_proba(
        self, bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame
    ) -> np.ndarray:
        _, errors = self.predict(bsak, bkpf, lfa1)
        e_min, e_max = errors.min(), errors.max()
        if e_max > e_min:
            return (errors - e_min) / (e_max - e_min)
        return np.zeros_like(errors)

    def get_latent(self, bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame) -> np.ndarray:
        features_df = _build_features(bsak, bkpf, lfa1)
        X = features_df[self.feature_names].fillna(0).values.astype(np.float32)
        X_scaled = self.scaler.transform(X).astype(np.float32)
        self.network.eval()
        tensor = torch.tensor(X_scaled).to(self.device)
        with torch.no_grad():
            latent = self.network.encode(tensor)
        return latent.cpu().numpy()

    def save(self, name: str = "autoencoder") -> Path:
        path = MODEL_DIR / f"{name}.pkl"
        state = {
            "network_state": self.network.state_dict(),
            "network_config": {
                "input_dim": list(self.network.encoder.parameters())[0].shape[1],
                "latent_dim": self.latent_dim,
            },
            "scaler": self.scaler,
            "threshold": self.threshold,
            "features": self.feature_names,
        }
        with open(path, "wb") as f:
            pickle.dump(state, f)
        self.model_hash = _file_hash(path)
        self.version = name
        return path

    @classmethod
    def load(cls, name: str = "autoencoder", device: Optional[str] = None) -> "AutoEncoderDetector":
        path = MODEL_DIR / f"{name}.pkl"
        with open(path, "rb") as f:
            state = pickle.load(f)
        obj = cls(latent_dim=state["network_config"]["latent_dim"], device=device)
        obj.scaler = state["scaler"]
        obj.threshold = state["threshold"]
        obj.feature_names = state["features"]
        input_dim = state["network_config"]["input_dim"]
        obj.network = _AENetwork(input_dim=input_dim, latent_dim=obj.latent_dim).to(obj.device)
        obj.network.load_state_dict(state["network_state"])
        obj.model_hash = _file_hash(path)
        obj.version = name
        return obj

    def get_feature_names(self) -> List[str]:
        return self.feature_names


def _file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()
