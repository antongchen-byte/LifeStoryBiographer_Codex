import base64
import io
import wave
from types import SimpleNamespace

import pytest
from conftest import account
from sqlalchemy import select

from app import interview_routes as routes
from app.ai.style_provider import ProviderFailure
from app.config import settings
from app.interview_models import InterviewConfig, InterviewSession, InterviewTurn
from app.models import MediaAsset, MediaStatus, now


@pytest.fixture
def setup(client, owner, project, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "synthetic-test-key")
    monkeypatch.setattr(settings, "gemini_model", "test-model")
    response = client.post(
        "/api/interviews/configs",
        headers=owner,
        json={"project_id": project, "avatar": "flame", "name": "Ember", "genre": "oral_history"},
    )
    assert response.status_code == 201, response.text
    config = response.json()
    response = client.post(
        "/api/interviews/sessions",
        headers=owner,
        json={"config_id": config["id"], "title": "Childhood", "provider_consent": True},
    )
    assert response.status_code == 201, response.text
    return config, response.json()["id"]


@pytest.fixture
def provider(monkeypatch):
    calls = []

    def generate(self, task, data, schema, audio=None):
        calls.append((task, data))
        return routes.Reply(
            text="What do you remember about the garden?",
            citations=[c["id"] for c in data["retrieved_context"][:1]],
        )

    monkeypatch.setattr(routes.GeminiStyleProvider, "generate", generate)
    return calls


def turn(client, owner, sid, **body):
    return client.post(
        f"/api/interviews/sessions/{sid}/turns", headers=owner, json={"request_id": "request-0001", **body}
    )


def test_configuration_scope_and_project_guard(client, owner, project, setup):
    config, sid = setup
    assert config["id"] in config["markdown"] and config["avatar_id"] in config["markdown"]
    assert "oral_history" in config["markdown"]
    assert len(client.get("/api/interviews/configs", headers=owner).json()) == 1
    other = account(client, "other-interviewer@example.com")
    assert client.get("/api/interviews/configs", headers=other).json() == []
    assert client.get(f"/api/interviews/sessions/{sid}", headers=other).status_code == 404
    assert client.get(f"/api/interviews/configs/{config['id']}/markdown", headers=other).status_code == 404
    assert (
        client.get("/api/interviews/approved", headers=other, params={"project_id": project}).status_code
        == 404
    )
    assert client.delete(f"/api/projects/{project}", headers=owner).status_code == 409
    assert client.delete(f"/api/interviews/configs/{config['id']}", headers=owner).status_code == 409
    assert client.delete(f"/api/interviews/sessions/{sid}", headers=owner).status_code == 204
    assert client.delete(f"/api/interviews/configs/{config['id']}", headers=owner).status_code == 204
    assert client.delete(f"/api/projects/{project}", headers=owner).status_code == 204


def test_idempotency_review_approval_search(client, owner, project, setup, provider):
    _, sid = setup
    first = turn(client, owner, sid, text="I grew up near a garden.")
    assert first.status_code == 200, first.text
    data = first.json()
    assert len(data["turns"]) == 2
    retried = turn(client, owner, sid, text="I grew up near a garden.").json()
    assert [t["id"] for t in retried["turns"]] == [t["id"] for t in data["turns"]]
    assert retried["revision"] == data["revision"]
    assert len(provider) == 1
    assert turn(client, owner, sid, text="Changed message").status_code == 409
    assert (
        client.post(
            f"/api/interviews/sessions/{sid}/approve", headers=owner, json={"revision": data["revision"]}
        ).status_code
        == 409
    )
    assert client.get("/api/interviews/approved", headers=owner, params={"project_id": project}).json() == []
    review = client.post(f"/api/interviews/sessions/{sid}/finish", headers=owner).json()
    edit_url = f"/api/interviews/sessions/{sid}/turns/{data['turns'][0]['id']}"
    assert (
        client.patch(edit_url, headers=owner, json={"text": "A railway garden.", "revision": 0}).status_code
        == 409
    )
    edited = client.patch(
        edit_url, headers=owner, json={"text": "A railway garden.", "revision": review["revision"]}
    ).json()
    approved = client.post(
        f"/api/interviews/sessions/{sid}/approve", headers=owner, json={"revision": edited["revision"]}
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert (
        len(
            client.post(
                f"/api/interviews/sessions/{sid}/approve",
                headers=owner,
                json={"revision": edited["revision"]},
            ).json()["approvals"]
        )
        == 1
    )
    assert (
        client.patch(
            edit_url, headers=owner, json={"text": "New text", "revision": edited["revision"]}
        ).status_code
        == 409
    )
    assert turn(client, owner, sid, request_id="request-0002", text="More").status_code == 409
    exported = client.get(f"/api/interviews/sessions/{sid}/export", headers=owner).json()
    assert exported["snapshot"]["turns"][0]["original_text"] == "I grew up near a garden."
    assert exported["snapshot"]["turns"][0]["text"] == "A railway garden."
    assert len(exported["sha256"]) == 64
    assert (
        len(
            client.get(
                "/api/interviews/approved", headers=owner, params={"project_id": project, "q": "railway"}
            ).json()
        )
        == 1
    )


def test_failure_retry_busy_guard(client, owner, setup, monkeypatch, interview_db):
    _, sid = setup

    def fail(*args, **kwargs):
        raise ProviderFailure("Synthetic unavailable provider")

    monkeypatch.setattr(routes.GeminiStyleProvider, "generate", fail)
    assert turn(client, owner, sid, text="Keep this answer.").status_code == 502
    state = client.get(f"/api/interviews/sessions/{sid}", headers=owner).json()
    assert state["turns"][0]["state"] == "failed"
    assert state["turns"][0]["text"] == "Keep this answer."
    assert not state["busy"]
    assert turn(client, owner, sid, request_id="request-0002", text="Another answer").status_code == 409
    s = interview_db.get(InterviewSession, sid)
    s.active_token, s.busy_since = "pending", now()
    interview_db.commit()
    assert turn(client, owner, sid).status_code == 409
    assert client.delete(f"/api/interviews/sessions/{sid}", headers=owner).status_code == 409
    s.active_token = None
    interview_db.commit()
    monkeypatch.setattr(
        routes.GeminiStyleProvider, "generate", lambda *args: routes.Reply(text="Tell me more.")
    )
    result = turn(client, owner, sid)
    assert result.status_code == 200, result.text
    assert len(result.json()["turns"]) == 2
    assert result.json()["turns"][0]["state"] == "complete"


def test_multiple_templates_immutable_rag_bad_citations(
    client, owner, project, db, interview_db, storage, monkeypatch, provider
):
    monkeypatch.setattr(settings, "gemini_api_key", "synthetic")
    ids = []
    for index, text in enumerate(["Ask about childhood gardens.", "Ask one question, then listen."]):
        a = MediaAsset(
            project_id=project,
            original_filename=f"template-{index}.md",
            mime_type="text/plain",
            size_bytes=len(text),
            storage_key=f"template-{index}",
            status=MediaStatus.ready,
            ownership_declared=True,
        )
        db.add(a)
        db.commit()
        storage.objects[a.storage_key] = text.encode()
        ids.append(a.id)
    response = client.post(
        "/api/interviews/configs",
        headers=owner,
        json={"project_id": project, "avatar": "female", "name": "Maya", "asset_ids": ids},
    )
    assert response.status_code == 201, response.text
    config = response.json()
    storage.objects["template-0"] = b"Changed original"
    c = interview_db.get(InterviewConfig, config["id"])
    assert "childhood gardens" in c.context["materials"][0]["text"]
    sid = client.post(
        "/api/interviews/sessions",
        headers=owner,
        json={"config_id": c.id, "title": "Garden", "provider_consent": True},
    ).json()["id"]
    result = turn(client, owner, sid, text="The garden was wonderful.")
    assert result.status_code == 200, result.text
    assert len(provider[0][1]["in_context_examples"]) == 2
    assert result.json()["turns"][1]["citations"][0]["source"] == "template-0.md"
    assert "untrusted reference data" in provider[0][0]
    monkeypatch.setattr(
        routes.GeminiStyleProvider,
        "generate",
        lambda *args: routes.Reply(text="Question?", citations=["invented-source"]),
    )
    assert turn(client, owner, sid, request_id="request-0002", text="More.").status_code == 502
    assert len(list(interview_db.scalars(select(InterviewTurn).where(InterviewTurn.session_id == sid)))) == 3


def wav_bytes():
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000)
    return out.getvalue()


def test_voice_recording_speech_and_delete(client, owner, setup, provider, monkeypatch, storage):
    _, sid = setup
    monkeypatch.setattr(
        routes.GeminiStyleProvider,
        "transcribe",
        lambda *args: SimpleNamespace(turns=[SimpleNamespace(text="I remember the garden.")]),
    )
    raw = wav_bytes()
    response = turn(client, owner, sid, audio=base64.b64encode(raw).decode(), mime="audio/wav")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["turns"][0]["has_audio"]
    assert data["turns"][0]["duration_ms"] >= 1000
    assert raw in storage.objects.values()
    calls = []

    def speech(*args):
        calls.append(args)
        return raw

    monkeypatch.setattr(routes, "generate_speech", speech)
    tid = data["turns"][1]["id"]
    url = f"/api/interviews/sessions/{sid}/turns/{tid}/speech"
    assert client.post(url, headers=owner).status_code == 200
    assert client.post(url, headers=owner).status_code == 200
    assert len(calls) == 1
    other = account(client, "voice-other@example.com")
    assert client.get(f"/api/interviews/sessions/{sid}/turns/{tid}/audio", headers=other).status_code == 404
    assert client.delete(f"/api/interviews/sessions/{sid}", headers=owner).status_code == 204
    assert not storage.objects


def test_invalid_voice_retained_for_review(client, owner, setup, provider, storage):
    _, sid = setup
    response = turn(client, owner, sid, audio=base64.b64encode(b"not audio").decode(), mime="audio/wav")
    assert response.status_code == 502
    assert b"not audio" in storage.objects.values()
    review = client.post(f"/api/interviews/sessions/{sid}/finish", headers=owner).json()
    assert (
        client.post(
            f"/api/interviews/sessions/{sid}/approve", headers=owner, json={"revision": review["revision"]}
        ).status_code
        == 422
    )
    assert not provider


def test_saved_script_role_selection(client, owner, project, db, interview_db):
    from test_style import reviewed
    from test_style import studio as studio_fixture

    studio_data = studio_fixture.__wrapped__(client, owner, project, db)
    reviewed(client, owner, studio_data)
    profile, source, _ = studio_data
    base = f"/api/profiles/{profile}"
    revision = client.get(base, headers=owner).json()["sources"][0]["revision"]
    archive = client.post(
        f"{base}/sources/{source}/archives", headers=owner, json={"revision": revision}
    ).json()
    assert client.get("/api/interviews/sources", headers=owner).json() == []
    assert (
        client.post(
            f"{base}/archives/{archive['id']}/saved",
            headers=owner,
            json={"sha256": archive["sha256"], "folder_label": "Scripts"},
        ).status_code
        == 200
    )
    found = client.get("/api/interviews/sources?q=train", headers=owner).json()
    assert len(found) == 1 and "interviewer" in found[0]["roles"]
    response = client.post(
        "/api/interviews/configs",
        headers=owner,
        json={
            "project_id": project,
            "avatar": "male",
            "name": "Eli",
            "scripts": [{"archive_id": archive["id"], "role": "interviewer"}],
        },
    )
    assert response.status_code == 201, response.text
    config = interview_db.get(InterviewConfig, response.json()["id"])
    assert len(config.context["materials"]) == 1
    assert config.context["materials"][0]["provenance"]["role"] == "interviewer"
    assert "train" not in config.context["materials"][0]["text"]
    other = account(client, "script-other@example.com")
    assert client.get("/api/interviews/sources", headers=other).json() == []


def test_tts_pcm_conversion_and_safe_errors(monkeypatch):
    import httpx

    monkeypatch.setattr(settings, "gemini_api_key", "synthetic")
    monkeypatch.setattr(settings, "gemini_tts_model", "gemini-2.5-flash-preview-tts")
    seen = []

    def respond(url, **kwargs):
        seen.append(kwargs["json"])
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "inlineData": {
                                        "mimeType": "audio/L16;codec=pcm;rate=24000",
                                        "data": base64.b64encode(b"\x00\x00" * 24000).decode(),
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(routes.httpx, "post", respond)
    result = routes.generate_speech("What happened next?", "male")
    with wave.open(io.BytesIO(result)) as wav:
        assert wav.getframerate() == 24000 and wav.getnframes() == 24000
    assert (
        seen[0]["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"]
        == "Charon"
    )
    monkeypatch.setattr(
        routes.httpx,
        "post",
        lambda *args, **kwargs: httpx.Response(
            403, json={"error": {"status": "PERMISSION_DENIED", "message": "sensitive response text"}}
        ),
    )
    with pytest.raises(ProviderFailure) as error:
        routes.generate_speech("Test", "flame")
    assert "sensitive response text" not in str(error.value)
    assert "403" in str(error.value)


@pytest.mark.parametrize(
    "avatar,label",
    [("flame", "Calm and reflective"), ("female", "Warm and curious"), ("male", "Thoughtful and focused")],
)
def test_avatar_personality_is_shown_pinned_and_used(
    client, owner, project, interview_db, monkeypatch, provider, avatar, label
):
    monkeypatch.setattr(settings, "gemini_api_key", "synthetic")
    options = client.get("/api/interviews/options", headers=owner).json()
    assert options["personalities"][avatar]["label"] == label
    result = client.post(
        "/api/interviews/configs",
        headers=owner,
        json={"project_id": project, "avatar": avatar, "name": "Custom name", "genre": "career"},
    )
    assert result.status_code == 201
    config = result.json()
    assert label in config["markdown"]
    stored = interview_db.get(InterviewConfig, config["id"])
    instruction = stored.context["personality"]["instruction"]
    monkeypatch.setitem(
        routes.PERSONALITIES, avatar, {"label": "Changed", "description": "Changed", "instruction": "Changed"}
    )
    sid = client.post(
        "/api/interviews/sessions",
        headers=owner,
        json={"config_id": config["id"], "title": "Test", "provider_consent": True},
    ).json()["id"]
    assert turn(client, owner, sid, text="I changed careers.").status_code == 200
    assert provider[0][1]["trusted_personality"] == instruction
    assert provider[0][1]["trusted_genre"] == routes.GENRES["career"]
    assert provider[0][1]["avatar_name"] == "Custom name"
