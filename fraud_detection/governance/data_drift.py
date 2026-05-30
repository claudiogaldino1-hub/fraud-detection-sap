"""
Data drift detection using Population Stability Index (PSI) and KS test.
Compares current inference data distributions against training baseline.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

DRIFT_REPORTS_DIR = Path("governance/drift_reports")
DRIFT_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_FILE = Path("governance/baseline_stats.json")


def _psi(expected: np.ndarray, actual: np.ndarray, buckets: int = 10) -> float:
    """Population Stability Index — PSI > 0.2 signals significant drift."""
    expected = expected[~np.isnan(expected)]
    actual = actual[~np.isnan(actual)]
    if len(expected) == 0 or len(actual) == 0:
        return 0.0

    breakpoints = np.percentile(expected, np.linspace(0, 100, buckets + 1))
    breakpoints = np.unique(breakpoints)
    if len(breakpoints) < 2:
        return 0.0

    exp_counts, _ = np.histogram(expected, bins=breakpoints)
    act_counts, _ = np.histogram(actual, bins=breakpoints)

    exp_pct = (exp_counts + 1e-8) / len(expected)
    act_pct = (act_counts + 1e-8) / len(actual)

    psi = np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct))
    return float(psi)


MONITORED_FEATURES = [
    "DMBTR", "WRBTR", "days_to_pay", "hour_of_entry",
    "vendor_payment_count_30d", "amount_deviation_from_vendor_mean",
    "is_round_amount", "days_since_vendor_created", "po_invoice_ratio",
]


class DataDriftDetector:
    def __init__(self):
        self._baseline: Optional[Dict[str, dict]] = None
        if BASELINE_FILE.exists():
            self._baseline = json.loads(BASELINE_FILE.read_text())

    def save_baseline(self, df: pd.DataFrame):
        """Persist descriptive statistics of training features as baseline."""
        stats_dict = {}
        for col in MONITORED_FEATURES:
            if col in df.columns:
                arr = df[col].dropna().values
                stats_dict[col] = {
                    "mean": float(np.mean(arr)),
                    "std": float(np.std(arr)),
                    "min": float(np.min(arr)),
                    "max": float(np.max(arr)),
                    "p25": float(np.percentile(arr, 25)),
                    "p50": float(np.percentile(arr, 50)),
                    "p75": float(np.percentile(arr, 75)),
                    "values": arr.tolist()[:2000],  # Store sample for PSI
                }
        BASELINE_FILE.write_text(json.dumps(stats_dict, indent=2), encoding="utf-8")
        self._baseline = stats_dict

    def detect(self, current_df: pd.DataFrame) -> dict:
        if self._baseline is None:
            raise RuntimeError("Baseline not set — call save_baseline() first.")

        results = {}
        alerts = []
        for col in MONITORED_FEATURES:
            if col not in current_df.columns or col not in self._baseline:
                continue

            current = current_df[col].dropna().values
            baseline_vals = np.array(self._baseline[col]["values"])

            psi_val = _psi(baseline_vals, current)
            ks_stat, ks_p = stats.ks_2samp(baseline_vals, current)

            drift_level = (
                "HIGH" if psi_val > 0.2 else
                "MEDIUM" if psi_val > 0.1 else
                "LOW"
            )

            results[col] = {
                "psi": round(psi_val, 6),
                "ks_statistic": round(float(ks_stat), 6),
                "ks_p_value": round(float(ks_p), 6),
                "drift_level": drift_level,
                "current_mean": round(float(np.mean(current)), 4),
                "baseline_mean": round(self._baseline[col]["mean"], 4),
            }

            if drift_level in ("HIGH", "MEDIUM"):
                alerts.append({"feature": col, "psi": psi_val, "drift_level": drift_level})

        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "total_features_monitored": len(results),
            "drifted_features": len(alerts),
            "alerts": alerts,
            "feature_details": results,
        }

        # Persist report
        report_path = DRIFT_REPORTS_DIR / f"drift_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return report

    def latest_report(self) -> dict:
        reports = sorted(DRIFT_REPORTS_DIR.glob("drift_*.json"), reverse=True)
        if not reports:
            return {"message": "Nenhum relatório de drift disponível ainda."}
        return json.loads(reports[0].read_text())
