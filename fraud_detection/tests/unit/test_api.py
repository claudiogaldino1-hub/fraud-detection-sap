"""Unit tests for API auth and schemas."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.auth.rbac import authenticate_user, create_access_token, ROLE_PERMISSIONS


client = TestClient(app)


class TestAuth:
    def test_login_valid_analyst(self):
        response = client.post(
            "/auth/token",
            data={"username": "ana.analista", "password": "analista123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "analista"

    def test_login_invalid_password(self):
        response = client.post(
            "/auth/token",
            data={"username": "ana.analista", "password": "wrong"},
        )
        assert response.status_code == 401

    def test_login_unknown_user(self):
        response = client.post(
            "/auth/token",
            data={"username": "nobody", "password": "pass"},
        )
        assert response.status_code == 401

    def test_authenticate_user_returns_user(self):
        user = authenticate_user("mario.gestor", "gestor456")
        assert user is not None
        assert user.role == "gestor"

    def test_authenticate_user_wrong_pass(self):
        user = authenticate_user("mario.gestor", "bad")
        assert user is None


class TestRBAC:
    def test_analyst_can_read_alerts(self):
        perms = ROLE_PERMISSIONS["analista"]
        assert "alerts:read" in perms

    def test_analyst_cannot_approve_models(self):
        perms = ROLE_PERMISSIONS["analista"]
        assert "models:approve" not in perms

    def test_auditor_has_all_permissions(self):
        auditor_perms = set(ROLE_PERMISSIONS["auditor"])
        analyst_perms = set(ROLE_PERMISSIONS["analista"])
        assert analyst_perms.issubset(auditor_perms)

    def test_gestor_has_model_approval(self):
        assert "models:approve" in ROLE_PERMISSIONS["gestor"]


def _get_token(username: str, password: str) -> str:
    response = client.post("/auth/token", data={"username": username, "password": password})
    return response.json()["access_token"]


class TestAlertsEndpoint:
    def test_alerts_requires_auth(self):
        response = client.get("/alerts")
        assert response.status_code == 403

    def test_alerts_with_valid_token(self):
        token = _get_token("ana.analista", "analista123")
        response = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "alerts" in data

    def test_alerts_pagination(self):
        token = _get_token("ana.analista", "analista123")
        response = client.get("/alerts?page=1&page_size=10", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert len(response.json()["alerts"]) <= 10


class TestFeedbackEndpoint:
    def test_submit_feedback(self):
        token = _get_token("ana.analista", "analista123")
        response = client.post(
            "/feedback",
            json={"alert_id": "test-alert-123", "label": "false_positive", "comment": "Teste"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["label"] == "false_positive"
        assert data["alert_id"] == "test-alert-123"

    def test_feedback_stats(self):
        token = _get_token("ana.analista", "analista123")
        response = client.get("/feedback/stats", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert "total" in response.json()


class TestHealthEndpoint:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
