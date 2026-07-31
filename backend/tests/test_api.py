from fastapi.testclient import TestClient

from app.main import app

OWNER = {"X-User-Id": "vratislav", "X-User-Role": "owner"}
PETR = {"X-User-Id": "petr-novak", "X-User-Role": "employee"}
MILAN = {"X-User-Id": "milan-dvorak", "X-User-Role": "employee"}


def test_seeded_dashboard_and_document_queues():
    with TestClient(app) as client:
        health = client.get("/api/health")
        dashboard = client.get("/api/dashboard", headers=OWNER)
        documents = client.get("/api/documents", headers=OWNER)
        transports = client.get("/api/transports", headers=OWNER)

    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert dashboard.status_code == 200
    assert dashboard.json()["documents_total"] >= 5
    assert documents.status_code == 200
    assert transports.status_code == 200
    assert len(transports.json()) >= 6


def test_employee_cannot_access_owner_management_apis():
    with TestClient(app) as client:
        assert client.get("/api/dashboard", headers=PETR).status_code == 403
        assert client.get("/api/documents", headers=PETR).status_code == 403
        assert client.get("/api/transports", headers=PETR).status_code == 403
        assert client.get("/api/accounting/export.csv", headers=PETR).status_code == 403


def test_employee_statement_contains_only_own_documents():
    with TestClient(app) as client:
        petr_documents = client.get("/api/me/documents", headers=PETR)
        milan_documents = client.get("/api/me/documents", headers=MILAN)

    assert petr_documents.status_code == 200
    assert milan_documents.status_code == 200
    assert {item["original_name"] for item in petr_documents.json()} == {
        "CMR_2026_001.jpg", "PHM_Benzina_28-07.jpg"
    }
    assert {item["original_name"] for item in milan_documents.json()} == {
        "CMR_2026_002.pdf", "Uctenka_Shell.jpg"
    }
    assert all("gross_amount" not in item and "dispatcher" not in item for item in petr_documents.json())


def test_missing_identity_is_rejected():
    with TestClient(app) as client:
        assert client.get("/api/dashboard").status_code == 401
        assert client.get("/api/me/documents").status_code == 401
