"""
Claude API narrator — generates Portuguese audit narratives for each fraud alert.
SHAP values are passed as context so explanations are grounded in data, not hallucinated.
"""

import os
from typing import Dict, List, Optional

import anthropic

from .shap_explainer import format_shap_for_prompt

_CLIENT: Optional[anthropic.Anthropic] = None


def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY environment variable not set.")
        _CLIENT = anthropic.Anthropic(api_key=api_key)
    return _CLIENT


SYSTEM_PROMPT = """Você é um especialista sênior em auditoria financeira e detecção de fraudes em processos
de compras (Procure to Pay — P2P) de sistemas SAP. Seu papel é analisar alertas gerados por modelos de
machine learning e redigir narrativas claras, objetivas e em português do Brasil para uso em relatórios
de auditoria interna.

Diretrizes:
- Use linguagem técnica mas compreensível para gestores financeiros.
- Cite os valores SHAP como evidência objetiva — não os invente.
- Indique o nível de risco: ALTO, MÉDIO ou BAIXO.
- Sugira ações investigativas específicas.
- Mantenha o texto em 3–5 parágrafos.
- Nunca afirme que fraude é certeza — use termos como "indício", "padrão atípico", "requer investigação".
- Referências a campos SAP devem usar o nome técnico seguido do nome em português entre parênteses."""


def generate_narrative(
    alert: Dict,
    shap_explanation: Dict,
    model: str = "claude-sonnet-4-6",
) -> str:
    """
    Generates a Portuguese audit narrative for a single alert.

    Parameters
    ----------
    alert : dict with keys: record_idx, fraud_type, ensemble_score, risk_tier, vendor_id, amount, date
    shap_explanation : output from SHAPExplainer.explain_single()
    """
    client = _get_client()
    shap_text = format_shap_for_prompt(shap_explanation)

    user_message = f"""Analise o seguinte alerta de risco financeiro e redija a narrativa de auditoria:

**Informações do Alerta:**
- Índice do registro: {alert.get('record_idx', 'N/A')}
- Tipo de fraude detectada: {alert.get('fraud_type', 'Anomalia genérica')}
- Score de risco ensemble: {alert.get('ensemble_score', 0):.4f}
- Nível de risco: {alert.get('risk_tier', 'N/A')}
- Score Isolation Forest: {alert.get('if_score', 0):.4f}
- Score AutoEncoder: {alert.get('ae_score', 0):.4f}
- Score de grafo (conluio/SoD): {alert.get('graph_score', 0):.4f}
- Fornecedor (LIFNR): {alert.get('vendor_id', 'N/A')}
- Valor do pagamento (DMBTR): R$ {alert.get('amount', 0):,.2f}
- Data de compensação (AUGDT): {alert.get('date', 'N/A')}
- Empresa (BUKRS): {alert.get('company_code', 'N/A')}
- Documento contábil (BELNR): {alert.get('doc_number', 'N/A')}

**Explicabilidade SHAP:**
{shap_text}

Redija a narrativa completa de auditoria seguindo as diretrizes do sistema."""

    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def generate_batch_narratives(
    alerts: List[Dict],
    shap_explanations: List[Dict],
    model: str = "claude-sonnet-4-6",
    max_alerts: int = 50,
) -> List[Dict]:
    """
    Generates narratives for a batch of alerts.
    Returns list of dicts with original alert + 'narrative' field.
    """
    results = []
    for alert, explanation in zip(alerts[:max_alerts], shap_explanations[:max_alerts]):
        try:
            narrative = generate_narrative(alert, explanation, model=model)
        except Exception as e:
            narrative = f"[Erro ao gerar narrativa: {str(e)}]"
        results.append({**alert, "narrative": narrative})
    return results


def generate_summary_report(alerts_df, model: str = "claude-sonnet-4-6") -> str:
    """Generates an executive summary report for all alerts."""
    client = _get_client()

    stats = {
        "total_alerts": len(alerts_df),
        "high_risk": int((alerts_df["risk_tier"] == "HIGH").sum()),
        "medium_risk": int((alerts_df["risk_tier"] == "MEDIUM").sum()),
        "fraud_types": alerts_df["FRAUD_TYPE"].value_counts().to_dict()
        if "FRAUD_TYPE" in alerts_df.columns else {},
        "total_value_at_risk": float(
            alerts_df.loc[alerts_df["is_alert"] == True, "DMBTR"].sum()
        ) if "is_alert" in alerts_df.columns else 0,
    }

    user_message = f"""Gere um relatório executivo de auditoria P2P com base nos seguintes dados agregados:

- Total de alertas gerados: {stats['total_alerts']}
- Alertas de risco ALTO: {stats['high_risk']}
- Alertas de risco MÉDIO: {stats['medium_risk']}
- Tipos de fraude detectados: {stats['fraud_types']}
- Valor total em risco (R$): {stats['total_value_at_risk']:,.2f}

O relatório deve conter: resumo executivo, principais achados por categoria de risco,
recomendações de controle e próximas ações prioritárias. Máximo 500 palavras."""

    response = client.messages.create(
        model=model,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text
