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


@pytest.mark.skipif(os.environ.get("RUN_LIVE") != "1", reason="Needs local migrated PostgreSQL")
def test_postgresql_screenplay_generation_and_export(client, owner, project):
    from app.interview_models import Screenplay
    from app.screenplay_schemas import BreakdownOutput, Content, DraftOutput
    from app.workflows.screenplay_activities import run_generation

    class Provider:
        def __init__(self, model):
            pass

        def generate(self, task, data, schema):
            content = Content(
                elements=[
                    {"kind": "scene", "text": "EXT. GARDEN - DAY"},
                    {"kind": "action", "text": "Leaves stir."},
                ]
            )
            return (
                DraftOutput(sections=[content])
                if schema is DraftOutput
                else BreakdownOutput(subsections=[content] * 4)
            )

    previous = app.dependency_overrides[get_interview_db]
    with engine.connect() as conn:
        transaction = conn.begin()
        with Session(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint") as db:
            app.dependency_overrides[get_interview_db] = lambda: db
            try:
                base = "/api/interviews/screenplays"
                created = client.post(
                    base,
                    headers=owner,
                    json={
                        "project_id": project,
                        "filename": "story.md",
                        "markdown": "# Garden\nI remember our garden.",
                    },
                )
                assert created.status_code == 201, created.text
                state = created.json()
                sid = state["id"]
                for kind in ["draft", "breakdown"]:
                    queued = client.post(
                        base + "/" + sid + "/generate",
                        headers=owner,
                        json={
                            "revision": state["revision"],
                            "kind": kind,
                            "sections": 1,
                            "seconds": 15,
                            "consent": True,
                        },
                    )
                    assert queued.status_code == 200, queued.text
                    db.expire_all()
                    generation = db.get(Screenplay, sid).generation
                    run_generation(
                        sid,
                        generation,
                        lambda: Session(
                            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
                        ),
                        Provider,
                    )
                    db.expire_all()
                    state = client.get(base + "/" + sid, headers=owner).json()
                    assert state["state"] == "idle", state
                assert len(state["sections"][0]["subsections"]) == 4
                exported = client.post(base + "/" + sid + "/export", headers=owner)
                assert exported.status_code == 200, exported.text
                assert state["interview_uid"] in exported.json()["markdown"]
                cinema = client.post(f"/api/cinema/screenplays/{sid}", headers=owner)
                assert cinema.status_code == 200, cinema.text
                production = cinema.json()
                clip = client.post(
                    f"/api/cinema/{production['id']}/subsections/{production['units'][0]['id']}/generate",
                    headers=owner,
                    json={"prompt": "Leaves stir in the garden.", "consent": True},
                )
                assert clip.status_code == 202, clip.text
                reloaded = client.get(f"/api/cinema/{production['id']}", headers=owner)
                assert reloaded.json()["units"][0]["clip"]["state"] == "pending"
                assert reloaded.json()["interview_uid"] == state["interview_uid"]

            finally:
                app.dependency_overrides[get_interview_db] = previous
        transaction.rollback()
