"""
Model versioning — tracks trained model artifacts with hash integrity.
"""

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

VERSION_DB = Path("governance/model_versions.json")
VERSION_DB.parent.mkdir(parents=True, exist_ok=True)


def _file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha.update(chunk)
    return sha.hexdigest()


class ModelVersion:
    def __init__(
        self,
        version_id: str,
        model_name: str,
        artifact_path: str,
        model_hash: str,
        created_by: str,
        metrics: Optional[Dict] = None,
        status: str = "pending",
        created_at: Optional[str] = None,
        approved_by: Optional[str] = None,
        approved_at: Optional[str] = None,
        comment: Optional[str] = None,
    ):
        self.version_id = version_id
        self.model_name = model_name
        self.artifact_path = artifact_path
        self.model_hash = model_hash
        self.created_by = created_by
        self.metrics = metrics or {}
        self.status = status
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.approved_by = approved_by
        self.approved_at = approved_at
        self.comment = comment

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "ModelVersion":
        return cls(**d)

    def verify_hash(self) -> bool:
        return _file_hash(Path(self.artifact_path)) == self.model_hash


class ModelVersionRegistry:
    def __init__(self, path: Path = VERSION_DB):
        self.path = path
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> List[dict]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, versions: List[dict]):
        self.path.write_text(
            json.dumps(versions, indent=2, default=str), encoding="utf-8"
        )

    def register(
        self,
        model_name: str,
        artifact_path: str,
        created_by: str,
        metrics: Optional[Dict] = None,
    ) -> ModelVersion:
        version_id = str(uuid.uuid4())
        model_hash = _file_hash(Path(artifact_path))
        v = ModelVersion(
            version_id=version_id,
            model_name=model_name,
            artifact_path=artifact_path,
            model_hash=model_hash,
            created_by=created_by,
            metrics=metrics or {},
            status="pending",
        )
        versions = self._load()
        versions.append(v.to_dict())
        self._save(versions)
        return v

    def get_version(self, version_id: str) -> Optional[ModelVersion]:
        for d in self._load():
            if d["version_id"] == version_id:
                return ModelVersion.from_dict(d)
        return None

    def list_versions(self) -> List[ModelVersion]:
        return [ModelVersion.from_dict(d) for d in self._load()]

    def update_status(
        self,
        version_id: str,
        new_status: str,
        actor: str,
        comment: Optional[str] = None,
    ) -> ModelVersion:
        versions = self._load()
        for v in versions:
            if v["version_id"] == version_id:
                v["status"] = new_status
                v["approved_by"] = actor
                v["approved_at"] = datetime.utcnow().isoformat()
                v["comment"] = comment
                self._save(versions)
                return ModelVersion.from_dict(v)
        raise ValueError(f"Version {version_id} not found.")

    def get_approved(self, model_name: str) -> Optional[ModelVersion]:
        for v in reversed(self.list_versions()):
            if v.model_name == model_name and v.status == "approved":
                return v
        return None
