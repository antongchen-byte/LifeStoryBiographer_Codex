"""Exercise the migrated, separate PostgreSQL DB without live provider calls."""

import os

import pytest
from sqlalchemy.orm import Session

from app import interview_routes as routes
from app.config import settings
from app.interview_database import engine, get_interview_db
from app.main import app


@pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="Needs local migrated PostgreSQL")
def test_postgresql_interview_approval_search(client, owner, project, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "synthetic")
    monkeypatch.setattr(
        routes.GeminiStyleProvider,
        "generate",
        lambda *args: routes.Reply(text="What grew in the railway garden?"),
    )
    previous = app.dependency_overrides[get_interview_db]
    with engine.connect() as conn:
        transaction = conn.begin()
        with Session(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
            app.dependency_overrides[get_interview_db] = lambda: db
            try:
                created = client.post(
                    "/api/interviews/configs",
                    headers=owner,
                    json={"project_id": project, "avatar": "flame", "name": "Synthetic Ember"},
                )
                assert created.status_code == 201, created.text
                cid = created.json()["id"]
                started = client.post(
                    "/api/interviews/sessions",
                    headers=owner,
                    json={"config_id": cid, "title": "Synthetic garden", "provider_consent": True},
                )
                assert started.status_code == 201, started.text
                sid = started.json()["id"]
                response = client.post(
                    f"/api/interviews/sessions/{sid}/turns",
                    headers=owner,
                    json={"request_id": "live-fixture-001", "text": "My childhood railway garden."},
                )
                assert response.status_code == 200, response.text
                review = client.post(f"/api/interviews/sessions/{sid}/finish", headers=owner).json()
                assert (
                    client.post(
                        f"/api/interviews/sessions/{sid}/approve",
                        headers=owner,
                        json={"revision": review["revision"]},
                    ).status_code
                    == 200
                )
                result = client.get(
                    "/api/interviews/approved",
                    headers=owner,
                    params={"project_id": project, "q": "railway garden"},
                )
                assert result.status_code == 200, result.text
                assert len(result.json()) == 1
                assert (
                    client.get(
                        "/api/interviews/approved",
                        headers=owner,
                        params={"project_id": project, "q": "unmatched"},
                    ).json()
                    == []
                )
                assert client.delete(f"/api/interviews/sessions/{sid}", headers=owner).status_code == 204
                assert client.delete(f"/api/interviews/configs/{cid}", headers=owner).status_code == 204
            finally:
                app.dependency_overrides[get_interview_db] = previous
                transaction.rollback()
