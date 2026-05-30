"""
Feedback router — analysts mark alerts as true/false positives.
Feedback is persisted in JSONL and used for model retraining signals.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import TokenData, require_permission
from api.schemas import FeedbackIn, FeedbackOut
from governance.audit_log import AuditLogger

FEEDBACK_FILE = Path("data/processed/feedback.jsonl")
FEEDBACK_FILE.parent.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/feedback", tags=["Feedback"])
_audit = AuditLogger()


@router.post("", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackIn,
    current_user: TokenData = Depends(require_permission("feedback:write")),
):
    feedback_id = str(uuid.uuid4())
    record = FeedbackOut(
        feedback_id=feedback_id,
        alert_id=body.alert_id,
        label=body.label,
        comment=body.comment,
        analyst=current_user.username or body.analyst,
        submitted_at=datetime.utcnow(),
    )

    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")

    _audit.log(
        action="FEEDBACK_SUBMITTED",
        user=current_user.username,
        details={"alert_id": body.alert_id, "label": body.label, "feedback_id": feedback_id},
    )

    return record


@router.get("", response_model=List[FeedbackOut])
async def list_feedback(
    alert_id: str = None,
    current_user: TokenData = Depends(require_permission("feedback:write")),
):
    if not FEEDBACK_FILE.exists():
        return []
    records = []
    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if alert_id and obj.get("alert_id") != alert_id:
                continue
            records.append(FeedbackOut(**obj))
    return records


@router.get("/stats")
async def feedback_stats(
    current_user: TokenData = Depends(require_permission("feedback:write")),
):
    if not FEEDBACK_FILE.exists():
        return {"total": 0}
    from collections import Counter
    labels = []
    with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                labels.append(json.loads(line).get("label", "unknown"))
    counts = Counter(labels)
    total = sum(counts.values())
    precision = counts.get("true_positive", 0) / total if total else 0
    return {
        "total": total,
        "true_positives": counts.get("true_positive", 0),
        "false_positives": counts.get("false_positive", 0),
        "under_investigation": counts.get("under_investigation", 0),
        "estimated_precision": round(precision, 4),
    }
