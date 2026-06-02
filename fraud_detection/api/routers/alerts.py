"""
Alerts router — exposes detected fraud alerts with pagination and filtering.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.auth import TokenData, require_permission
from api.schemas import AlertListResponse, AlertOut, RiskTier

router = APIRouter(prefix="/alerts", tags=["Alerts"])

# In production, this would come from a database / cache populated by the MLOps pipeline.
_ALERTS_STORE: List[dict] = []


def set_alerts(alerts: List[dict]):
    """Called by pipeline after model inference to populate the store."""
    global _ALERTS_STORE
    _ALERTS_STORE = alerts


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    risk_tier: Optional[RiskTier] = None,
    vendor_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: TokenData = Depends(require_permission("alerts:read")),
):
    alerts = _ALERTS_STORE

    if risk_tier:
        alerts = [a for a in alerts if a.get("risk_tier") == risk_tier.value]
    if vendor_id:
        alerts = [a for a in alerts if a.get("vendor_id") == vendor_id]
    if date_from:
        alerts = [a for a in alerts if str(a.get("date", "")) >= date_from]
    if date_to:
        alerts = [a for a in alerts if str(a.get("date", "")) <= date_to]

    total = len(alerts)
    start = (page - 1) * page_size
    page_alerts = alerts[start : start + page_size]

    return AlertListResponse(
        total=total,
        page=page,
        page_size=page_size,
        alerts=[AlertOut(**a) for a in page_alerts],
    )


@router.get("/{alert_id}", response_model=AlertOut)
async def get_alert(
    alert_id: str,
    current_user: TokenData = Depends(require_permission("alerts:read")),
):
    for alert in _ALERTS_STORE:
        if alert.get("alert_id") == alert_id:
            return AlertOut(**alert)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Alerta {alert_id} não encontrado.")


@router.get("/summary/by-type")
async def alerts_by_type(
    current_user: TokenData = Depends(require_permission("alerts:read")),
):
    from collections import Counter
    types = Counter(a.get("fraud_type", "unknown") for a in _ALERTS_STORE if a.get("is_alert"))
    return {"by_fraud_type": dict(types)}


@router.get("/summary/by-risk")
async def alerts_by_risk(
    current_user: TokenData = Depends(require_permission("alerts:read")),
):
    from collections import Counter
    tiers = Counter(a.get("risk_tier", "LOW") for a in _ALERTS_STORE if a.get("is_alert"))
    return {"by_risk_tier": dict(tiers)}
