"""
Export router — exports alert data in formats ready for Power BI or Excel.
"""

import io
import json
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse

from api.auth import TokenData, require_permission
from api.routers.alerts import _ALERTS_STORE
from api.schemas import ExportRequest
from dashboard.powerbi.star_schema import build_star_schema

router = APIRouter(prefix="/export", tags=["Export"])

EXPORT_DIR = Path("data/processed/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/alerts")
async def export_alerts(
    body: ExportRequest,
    current_user: TokenData = Depends(require_permission("export:read")),
):
    alerts = [a for a in _ALERTS_STORE if a.get("is_alert")]

    if body.risk_tiers:
        tiers = [t.value if hasattr(t, "value") else t for t in body.risk_tiers]
        alerts = [a for a in alerts if a.get("risk_tier") in tiers]

    if not alerts:
        raise HTTPException(status_code=404, detail="Nenhum alerta encontrado com os filtros aplicados.")

    df = pd.DataFrame(alerts)

    if body.format == "csv":
        content = df.to_csv(index=False).encode("utf-8")
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=alerts_export.csv"},
        )
    elif body.format == "json":
        content = df.to_json(orient="records", force_ascii=False, indent=2).encode("utf-8")
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=alerts_export.json"},
        )
    else:  # parquet
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename=alerts_export.parquet"},
        )


@router.get("/powerbi/star-schema")
async def export_star_schema(
    current_user: TokenData = Depends(require_permission("export:read")),
):
    """
    Builds and returns the Power BI semantic star schema as multiple parquet files
    (fact + dimensions). Returns a JSON manifest with file paths.
    """
    df = pd.DataFrame(_ALERTS_STORE)
    if df.empty:
        raise HTTPException(status_code=404, detail="Sem dados para exportar.")

    star = build_star_schema(df)
    manifest = {}
    for table_name, table_df in star.items():
        out_path = EXPORT_DIR / f"pbi_{table_name}.parquet"
        table_df.to_parquet(out_path, index=False)
        manifest[table_name] = {
            "path": str(out_path),
            "rows": len(table_df),
            "columns": list(table_df.columns),
        }

    return {"status": "ok", "tables": manifest, "exported_at": datetime.utcnow().isoformat()}


@router.get("/audit-log")
async def export_audit_log(
    current_user: TokenData = Depends(require_permission("audit_log:read")),
):
    audit_path = Path("governance/AUDIT_LOG.json")
    if not audit_path.exists():
        return {"entries": []}
    with open(audit_path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    return {"entries": entries, "total": len(entries)}
