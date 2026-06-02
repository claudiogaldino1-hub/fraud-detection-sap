"""
Audit log — append-only JSONL with SHA-256 chain integrity.
Each entry references the hash of the previous entry (blockchain-lite).
"""

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

AUDIT_FILE = Path("governance/AUDIT_LOG.json")
AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)


def _hash_entry(entry: dict) -> str:
    serialised = json.dumps(entry, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialised.encode()).hexdigest()


class AuditLogger:
    def __init__(self, path: Path = AUDIT_FILE):
        self.path = path
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> List[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save(self, entries: List[dict]):
        self.path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def log(
        self,
        action: str,
        user: Optional[str] = None,
        model_name: Optional[str] = None,
        model_hash: Optional[str] = None,
        model_version: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> dict:
        entries = self._load()
        prev_hash = _hash_entry(entries[-1]) if entries else "genesis"

        entry = {
            "seq": len(entries) + 1,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "action": action,
            "user": user or os.environ.get("AUDIT_USER", "system"),
            "model_name": model_name,
            "model_hash": model_hash,
            "model_version": model_version,
            "details": details or {},
            "prev_hash": prev_hash,
        }
        entry["entry_hash"] = _hash_entry(entry)

        entries.append(entry)
        self._save(entries)
        return entry

    def verify_integrity(self) -> bool:
        """Walks the chain verifying each entry's hash matches prev_hash of the next."""
        entries = self._load()
        for i in range(1, len(entries)):
            expected = _hash_entry({k: v for k, v in entries[i - 1].items() if k != "entry_hash"})
            if entries[i]["prev_hash"] != expected:
                return False
        return True

    def get_all(self) -> List[dict]:
        return self._load()

    def get_by_action(self, action: str) -> List[dict]:
        return [e for e in self._load() if e.get("action") == action]

    def get_by_user(self, user: str) -> List[dict]:
        return [e for e in self._load() if e.get("user") == user]
