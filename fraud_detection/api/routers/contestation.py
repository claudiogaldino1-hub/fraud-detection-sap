"""
Alert contestation router — allows users to dispute fraud alerts.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import TokenData, require_permission
from api.schemas import ContestationIn, ContestationOut
from governance.audit_log import AuditLogger

CONTESTATION_FILE = Path("data/processed/contestations.jsonl")
CONTESTATION_FILE.parent.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/contestations", tags=["Contestações"])
_audit = AuditLogger()


@router.post("", response_model=ContestationOut, status_code=status.HTTP_201_CREATED)
async def submit_contestation(
    body: ContestationIn,
    current_user: TokenData = Depends(require_permission("feedback:write")),
):
    contestation_id = str(uuid.uuid4())
    record = ContestationOut(
        contestation_id=contestation_id,
        alert_id=body.alert_id,
        reason=body.reason,
        evidence=body.evidence,
        submitted_by=current_user.username or body.submitted_by,
        status="open",
        submitted_at=datetime.utcnow(),
    )

    with open(CONTESTATION_FILE, "a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")

    _audit.log(
        action="CONTESTATION_SUBMITTED",
        user=current_user.username,
        details={"alert_id": body.alert_id, "contestation_id": contestation_id},
    )

    return record


@router.get("", response_model=List[ContestationOut])
async def list_contestations(
    alert_id: Optional[str] = None,
    contestation_status: Optional[str] = None,
    current_user: TokenData = Depends(require_permission("contestation:read")),
):
    if not CONTESTATION_FILE.exists():
        return []
    records = []
    with open(CONTESTATION_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if alert_id and obj.get("alert_id") != alert_id:
                continue
            if contestation_status and obj.get("status") != contestation_status:
                continue
            records.append(ContestationOut(**obj))
    return records


@router.patch("/{contestation_id}/resolve")
async def resolve_contestation(
    contestation_id: str,
    resolution: str,
    current_user: TokenData = Depends(require_permission("contestation:write")),
):
    """Auditors resolve open contestations."""
    if not CONTESTATION_FILE.exists():
        raise HTTPException(status_code=404, detail="Nenhuma contestação encontrada.")

    lines = CONTESTATION_FILE.read_text(encoding="utf-8").splitlines()
    updated_lines = []
    found = False
    for line in lines:
        if not line.strip():
            continue
        obj = json.loads(line)
        if obj.get("contestation_id") == contestation_id:
            obj["status"] = "closed"
            obj["resolution"] = resolution
            obj["resolved_at"] = datetime.utcnow().isoformat()
            found = True
        updated_lines.append(json.dumps(obj, ensure_ascii=False))

    if not found:
        raise HTTPException(status_code=404, detail=f"Contestação {contestation_id} não encontrada.")

    CONTESTATION_FILE.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

    _audit.log(
        action="CONTESTATION_RESOLVED",
        user=current_user.username,
        details={"contestation_id": contestation_id, "resolution": resolution},
    )

    return {"status": "closed", "contestation_id": contestation_id, "resolution": resolution}
