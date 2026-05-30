"""
SHAP-based explainability for the Isolation Forest model.
Produces feature contribution values used as input to the Claude API narrator.
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import shap

from models.isolation_forest import IsolationForestDetector, _build_features


class SHAPExplainer:
    def __init__(self, detector: IsolationForestDetector):
        self.detector = detector
        self._explainer: Optional[shap.TreeExplainer] = None

    def fit(self, bsak: pd.DataFrame, bkpf: pd.DataFrame, lfa1: pd.DataFrame, max_background: int = 200):
        """Build SHAP TreeExplainer using a background sample."""
        features_df = _build_features(bsak, bkpf, lfa1)
        X = features_df[self.detector.feature_names].fillna(0).values
        X_scaled = self.detector.scaler.transform(X)

        background = shap.sample(X_scaled, min(max_background, len(X_scaled)))
        self._explainer = shap.TreeExplainer(self.detector.model, data=background)

    def explain(
        self,
        bsak: pd.DataFrame,
        bkpf: pd.DataFrame,
        lfa1: pd.DataFrame,
        top_n: int = 5,
    ) -> List[Dict]:
        """
        Returns a list of dicts — one per record — with top contributing features.
        Each dict is ready to be serialised and sent to the Claude narrator.
        """
        if self._explainer is None:
            raise RuntimeError("Call fit() before explain().")

        features_df = _build_features(bsak, bkpf, lfa1)
        X = features_df[self.detector.feature_names].fillna(0).values
        X_scaled = self.detector.scaler.transform(X)

        shap_values = self._explainer.shap_values(X_scaled)

        results = []
        for i in range(len(X)):
            contribs = dict(zip(self.detector.feature_names, shap_values[i]))
            sorted_contribs = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)
            top = sorted_contribs[:top_n]
            results.append({
                "record_idx": i,
                "shap_contributions": [
                    {
                        "feature": feat,
                        "shap_value": round(float(val), 6),
                        "raw_value": round(float(X[i, self.detector.feature_names.index(feat)]), 4),
                        "direction": "increase_risk" if val > 0 else "decrease_risk",
                    }
                    for feat, val in top
                ],
                "base_value": round(float(self._explainer.expected_value), 6),
                "total_shap": round(float(sum(v for _, v in top)), 6),
            })
        return results

    def explain_single(
        self,
        record: pd.Series,
        bkpf: pd.DataFrame,
        lfa1: pd.DataFrame,
        top_n: int = 5,
    ) -> Dict:
        """Explain a single BSAK record."""
        bsak_single = record.to_frame().T.reset_index(drop=True)
        results = self.explain(bsak_single, bkpf, lfa1, top_n=top_n)
        return results[0] if results else {}


FEATURE_LABELS_PT = {
    "DMBTR":                             "Valor em moeda local",
    "WRBTR":                             "Valor em moeda do documento",
    "days_to_pay":                       "Dias até pagamento",
    "hour_of_entry":                     "Hora de lançamento",
    "vendor_payment_count_30d":          "Qtde pagamentos ao fornecedor (30d)",
    "amount_deviation_from_vendor_mean": "Desvio do valor médio do fornecedor",
    "is_round_amount":                   "Valor redondo",
    "days_since_vendor_created":         "Dias desde criação do fornecedor",
    "po_invoice_ratio":                  "Proporção PO / Fatura",
}


def format_shap_for_prompt(explanation: Dict) -> str:
    """Formats SHAP output into a readable Portuguese text block for Claude prompt."""
    lines = ["Contribuições dos fatores para o score de risco:"]
    for c in explanation.get("shap_contributions", []):
        feature_label = FEATURE_LABELS_PT.get(c["feature"], c["feature"])
        direction = "aumenta risco" if c["direction"] == "increase_risk" else "reduz risco"
        lines.append(
            f"  • {feature_label}: valor={c['raw_value']:.4f}, "
            f"contribuição SHAP={c['shap_value']:+.4f} ({direction})"
        )
    lines.append(f"Valor base SHAP: {explanation.get('base_value', 0):.4f}")
    return "\n".join(lines)
