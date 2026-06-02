"""
Model version management router.
Gestores and auditores can list versions, approve or reject candidates.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status

from api.auth import TokenData, require_permission
from api.schemas import ModelApprovalIn, ModelVersionOut
from governance.audit_log import AuditLogger
from mlops.model_approval import ModelVersionRegistry

router = APIRouter(prefix="/models", tags=["Model Versions"])
_audit = AuditLogger()
_registry = ModelVersionRegistry()


@router.get("", response_model=List[ModelVersionOut])
async def list_versions(
    current_user: TokenData = Depends(require_permission("models:read")),
):
    return _registry.list_versions()


@router.get("/{version_id}", response_model=ModelVersionOut)
async def get_version(
    version_id: str,
    current_user: TokenData = Depends(require_permission("models:read")),
):
    v = _registry.get_version(version_id)
    if not v:
        raise HTTPException(status_code=404, detail=f"Versão {version_id} não encontrada.")
    return v


@router.post("/approve", response_model=ModelVersionOut)
async def approve_or_reject(
    body: ModelApprovalIn,
    current_user: TokenData = Depends(require_permission("models:approve")),
):
    if body.action not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="action deve ser 'approve' ou 'reject'.")

    v = _registry.get_version(body.version_id)
    if not v:
        raise HTTPException(status_code=404, detail=f"Versão {body.version_id} não encontrada.")
    if v.status not in ("pending",):
        raise HTTPException(status_code=400, detail=f"Versão está em status '{v.status}' — apenas 'pending' pode ser aprovada/rejeitada.")

    updated = _registry.update_status(
        version_id=body.version_id,
        new_status="approved" if body.action == "approve" else "rejected",
        actor=current_user.username,
        comment=body.comment,
    )

    _audit.log(
        action=f"MODEL_{body.action.upper()}ED",
        user=current_user.username,
        details={
            "version_id": body.version_id,
            "action": body.action,
            "comment": body.comment,
        },
    )

    return updated


@router.get("/drift/report")
async def drift_report(
    current_user: TokenData = Depends(require_permission("models:read")),
):
    from governance.data_drift import DataDriftDetector
    detector = DataDriftDetector()
    return detector.latest_report()
