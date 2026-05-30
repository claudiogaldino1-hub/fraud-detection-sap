"""
Alert contestation service — business logic layer (decoupled from HTTP).
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional

CONTESTATION_FILE = Path("data/processed/contestations.jsonl")


class ContestationService:
    def __init__(self, storage_path: Path = CONTESTATION_FILE):
        self.path = storage_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    def _load_all(self) -> List[dict]:
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def open_contestation(
        self,
        alert_id: str,
        reason: str,
        submitted_by: str,
        evidence: Optional[str] = None,
    ) -> dict:
        record = {
            "contestation_id": str(uuid.uuid4()),
            "alert_id": alert_id,
            "reason": reason,
            "evidence": evidence,
            "submitted_by": submitted_by,
            "status": "open",
            "submitted_at": datetime.utcnow().isoformat(),
            "resolution": None,
            "resolved_at": None,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def get_by_alert(self, alert_id: str) -> List[dict]:
        return [c for c in self._load_all() if c["alert_id"] == alert_id]

    def resolve(self, contestation_id: str, resolution: str, resolved_by: str) -> dict:
        records = self._load_all()
        found = None
        updated = []
        for r in records:
            if r["contestation_id"] == contestation_id:
                r["status"] = "closed"
                r["resolution"] = resolution
                r["resolved_at"] = datetime.utcnow().isoformat()
                r["resolved_by"] = resolved_by
                found = r
            updated.append(r)

        if not found:
            raise ValueError(f"Contestação {contestation_id} não encontrada.")

        with open(self.path, "w", encoding="utf-8") as f:
            for r in updated:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        return found

    def stats(self) -> dict:
        records = self._load_all()
        open_count = sum(1 for r in records if r["status"] == "open")
        closed_count = sum(1 for r in records if r["status"] == "closed")
        return {
            "total": len(records),
            "open": open_count,
            "closed": closed_count,
        }
