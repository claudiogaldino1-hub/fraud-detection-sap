"""
Power BI star schema builder.
Produces fact_alerts + dimension tables (dim_vendor, dim_time, dim_fraud_type, dim_model).
Exported as Parquet — connect Power BI Desktop via "Pasta" connector.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd


def build_star_schema(alerts_df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    Input: flat alerts DataFrame (output of EnsembleDetector.predict()).
    Output: dict of table_name -> DataFrame ready for Power BI import.
    """
    df = alerts_df.copy()

    # ------------------------------------------------------------------
    # dim_vendor
    # ------------------------------------------------------------------
    dim_vendor_cols = ["vendor_id", "company_code"]
    available_vendor = [c for c in dim_vendor_cols if c in df.columns]
    if available_vendor:
        dim_vendor = df[available_vendor].drop_duplicates().reset_index(drop=True)
        dim_vendor["vendor_key"] = range(1, len(dim_vendor) + 1)
    else:
        dim_vendor = pd.DataFrame({"vendor_key": [], "vendor_id": [], "company_code": []})

    # ------------------------------------------------------------------
    # dim_time
    # ------------------------------------------------------------------
    if "date" in df.columns:
        dates = pd.to_datetime(df["date"], errors="coerce").dropna().unique()
        dim_time = pd.DataFrame({"full_date": pd.DatetimeIndex(dates)})
    else:
        dim_time = pd.DataFrame({"full_date": pd.date_range("2023-01-01", periods=1)})

    dim_time["date_key"] = range(1, len(dim_time) + 1)
    dim_time["year"] = dim_time["full_date"].dt.year
    dim_time["quarter"] = dim_time["full_date"].dt.quarter
    dim_time["month"] = dim_time["full_date"].dt.month
    dim_time["month_name"] = dim_time["full_date"].dt.strftime("%B")
    dim_time["week"] = dim_time["full_date"].dt.isocalendar().week.astype(int)
    dim_time["day_of_week"] = dim_time["full_date"].dt.dayofweek
    dim_time["is_weekend"] = dim_time["day_of_week"] >= 5

    # ------------------------------------------------------------------
    # dim_fraud_type
    # ------------------------------------------------------------------
    fraud_types_raw = df.get("fraud_type", pd.Series(["UNKNOWN"] * len(df))).fillna("UNKNOWN").unique()
    dim_fraud_type = pd.DataFrame({
        "fraud_type_key": range(1, len(fraud_types_raw) + 1),
        "fraud_type_code": fraud_types_raw,
        "fraud_type_label": [_fraud_label(ft) for ft in fraud_types_raw],
        "fraud_category": [_fraud_category(ft) for ft in fraud_types_raw],
    })

    # ------------------------------------------------------------------
    # dim_model
    # ------------------------------------------------------------------
    dim_model = pd.DataFrame([
        {"model_key": 1, "model_name": "Isolation Forest", "model_type": "Statistical", "weight": 0.35},
        {"model_key": 2, "model_name": "AutoEncoder",       "model_type": "Deep Learning","weight": 0.35},
        {"model_key": 3, "model_name": "Graph Analysis",    "model_type": "Graph",        "weight": 0.30},
        {"model_key": 4, "model_name": "Ensemble",          "model_type": "Ensemble",     "weight": 1.00},
    ])

    # ------------------------------------------------------------------
    # fact_alerts
    # ------------------------------------------------------------------
    fact = df.copy()

    if "vendor_id" in fact.columns and not dim_vendor.empty:
        fact = fact.merge(dim_vendor[["vendor_id", "vendor_key"]], on="vendor_id", how="left")
    else:
        fact["vendor_key"] = 0

    if "date" in fact.columns and not dim_time.empty:
        fact["full_date_str"] = pd.to_datetime(fact["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        dim_time_map = dim_time.set_index(dim_time["full_date"].dt.strftime("%Y-%m-%d"))["date_key"].to_dict()
        fact["date_key"] = fact["full_date_str"].map(dim_time_map).fillna(0).astype(int)
    else:
        fact["date_key"] = 0

    if "fraud_type" in fact.columns and not dim_fraud_type.empty:
        ft_map = dim_fraud_type.set_index("fraud_type_code")["fraud_type_key"].to_dict()
        fact["fraud_type_key"] = fact["fraud_type"].fillna("UNKNOWN").map(ft_map).fillna(0).astype(int)
    else:
        fact["fraud_type_key"] = 0

    fact_cols = [
        "alert_id", "record_idx", "vendor_key", "date_key", "fraud_type_key",
        "if_score", "ae_score", "graph_score", "ensemble_score",
        "risk_tier", "is_alert", "amount", "narrative",
    ]
    available_fact_cols = [c for c in fact_cols if c in fact.columns]
    fact_alerts = fact[available_fact_cols].reset_index(drop=True)

    return {
        "fact_alerts": fact_alerts,
        "dim_vendor": dim_vendor,
        "dim_time": dim_time,
        "dim_fraud_type": dim_fraud_type,
        "dim_model": dim_model,
    }


_FRAUD_LABELS = {
    "GHOST_VENDOR":              "Fornecedor Fantasma",
    "DUPLICATE_VENDOR":          "Fornecedor Duplicado",
    "BANK_CHANGE_BEFORE_PAYMENT":"Dados Bancários Alterados",
    "VENDOR_EMPLOYEE_SHARED_BANK":"Fornecedor e Funcionário — Mesmo Banco",
    "FAST_VENDOR_PAYMENT":       "Fornecedor Criado e Pago Rapidamente",
    "DUPLICATE_PO":              "Pedido Duplicado",
    "PO_WITHOUT_CONTRACT":       "Compra Sem Contrato",
    "THRESHOLD_SPLITTING":       "Fracionamento de Pedido",
    "DUPLICATE_PAYMENT":         "Pagamento Duplicado",
    "MAVERICK_SPEND":            "Fatura Sem PO (Maverick Spend)",
    "BELOW_THRESHOLD":           "Valor Abaixo do Limite de Aprovação",
    "CANCELLED_NOT_REVERSED":    "NF Cancelada Sem Estorno",
    "THREE_WAY_MISMATCH":        "Divergência PO/Recebimento/Fatura",
    "ROUND_PAYMENT":             "Pagamento em Valor Redondo",
    "EARLY_PAYMENT":             "Pagamento Antecipado",
    "WRONG_BANK_ACCOUNT":        "Pagamento para Conta Diferente",
    "PAYMENT_BURST":             "Volume Alto de Pagamentos",
    "AFTER_HOURS_PAYMENT":       "Pagamento Fora do Horário",
    "SUSPICIOUS_RECURRENCE":     "Recorrência Suspeita",
    "SOD_VENDOR_AND_PAYMENT":    "SoD: Cadastrou e Pagou Fornecedor",
    "SOD_PO_AND_RECEIPT":        "SoD: Criou PO e Aprovou Recebimento",
    "UNKNOWN":                   "Anomalia Genérica",
}

_FRAUD_CATEGORIES = {
    "GHOST_VENDOR":              "Cadastro de Fornecedor",
    "DUPLICATE_VENDOR":          "Cadastro de Fornecedor",
    "BANK_CHANGE_BEFORE_PAYMENT":"Cadastro de Fornecedor",
    "VENDOR_EMPLOYEE_SHARED_BANK":"Cadastro de Fornecedor",
    "FAST_VENDOR_PAYMENT":       "Cadastro de Fornecedor",
    "DUPLICATE_PO":              "Pedido de Compra",
    "PO_WITHOUT_CONTRACT":       "Pedido de Compra",
    "THRESHOLD_SPLITTING":       "Pedido de Compra",
    "DUPLICATE_PAYMENT":         "Fatura",
    "MAVERICK_SPEND":            "Fatura",
    "BELOW_THRESHOLD":           "Fatura",
    "CANCELLED_NOT_REVERSED":    "Fatura",
    "THREE_WAY_MISMATCH":        "Fatura",
    "ROUND_PAYMENT":             "Pagamento",
    "EARLY_PAYMENT":             "Pagamento",
    "WRONG_BANK_ACCOUNT":        "Pagamento",
    "PAYMENT_BURST":             "Pagamento",
    "AFTER_HOURS_PAYMENT":       "Pagamento",
    "SUSPICIOUS_RECURRENCE":     "Pagamento",
    "SOD_VENDOR_AND_PAYMENT":    "SoD / Conluio",
    "SOD_PO_AND_RECEIPT":        "SoD / Conluio",
    "UNKNOWN":                   "Outros",
}


def _fraud_label(code: str) -> str:
    return _FRAUD_LABELS.get(code, code)


def _fraud_category(code: str) -> str:
    return _FRAUD_CATEGORIES.get(code, "Outros")
