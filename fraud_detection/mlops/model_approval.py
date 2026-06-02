"""Model approval workflow — re-exports registry for use by API routers."""

from governance.model_versioning import ModelVersionRegistry, ModelVersion

__all__ = ["ModelVersionRegistry", "ModelVersion"]
