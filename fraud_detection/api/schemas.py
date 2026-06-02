"""Pydantic schemas shared across API routers."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RiskTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FeedbackLabel(str, Enum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    UNDER_INVESTIGATION = "under_investigation"


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------

class AlertOut(BaseModel):
    alert_id: str
    record_idx: int
    vendor_id: str
    company_code: str
    doc_number: str
    amount: float
    date: Optional[str]
    if_score: float
    ae_score: float
    graph_score: float
    ensemble_score: float
    risk_tier: RiskTier
    fraud_type: Optional[str]
    narrative: Optional[str]
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        use_enum_values = True


class AlertListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    alerts: List[AlertOut]


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackIn(BaseModel):
    alert_id: str
    label: FeedbackLabel
    comment: Optional[str] = None
    analyst: Optional[str] = None


class FeedbackOut(BaseModel):
    feedback_id: str
    alert_id: str
    label: FeedbackLabel
    comment: Optional[str]
    analyst: Optional[str]
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Model version
# ---------------------------------------------------------------------------

class ModelVersionOut(BaseModel):
    version_id: str
    model_name: str
    model_hash: str
    created_at: datetime
    created_by: str
    status: str               # pending | approved | rejected | retired
    metrics: Dict[str, Any] = Field(default_factory=dict)
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None


class ModelApprovalIn(BaseModel):
    version_id: str
    action: str               # approve | reject
    comment: Optional[str] = None


# ---------------------------------------------------------------------------
# Contestation
# ---------------------------------------------------------------------------

class ContestationIn(BaseModel):
    alert_id: str
    reason: str
    evidence: Optional[str] = None
    submitted_by: str


class ContestationOut(BaseModel):
    contestation_id: str
    alert_id: str
    reason: str
    evidence: Optional[str]
    submitted_by: str
    status: str               # open | under_review | closed
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

class ExportRequest(BaseModel):
    format: str = "parquet"   # parquet | csv | json
    risk_tiers: List[RiskTier] = Field(default_factory=lambda: [RiskTier.HIGH, RiskTier.MEDIUM])
    date_from: Optional[str] = None
    date_to: Optional[str] = None
