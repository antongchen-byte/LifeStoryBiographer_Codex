import hashlib
from uuid import uuid4

import pytest
from conftest import account
from sqlalchemy.orm import sessionmaker

from app.interview_models import InterviewSession, InterviewTurn, Screenplay
from app.models import MediaAsset, MediaStatus, new_id
from app.screenplay_schemas import BreakdownOutput, Content, DraftOutput
from app.workflows.screenplay_activities import run_generation

BASE = "/api/interviews/screenplays"


def content(text="A PHOTO fills the screen."):
    return Content(
        elements=[
            {"kind": "scene", "text": "INT. FAMILY HOME - DAY"},
            {"kind": "action", "text": text},
            {"kind": "character", "text": "NARRATOR (V.O.)"},
            {"kind": "parenthetical", "text": "quietly"},
            {"kind": "dialogue", "text": "I remember our garden."},
        ],
        notes="Proposed visual staging.",
    )


class Provider:
    def __init__(self, model):
        pass

    def generate(self, task, data, schema):
        if schema is DraftOutput:
            return DraftOutput(sections=[content()])
        return BreakdownOutput(
            subsections=[content(f"Garden detail {i}.") for i in range(6 if "6 consecutive" in task else 4)]
        )


@pytest.fixture
def source(client, owner, project, interview_db):
    cid = client.post(
        "/api/interviews/configs",
        headers=owner,
        json={"project_id": project, "avatar": "flame", "name": "Ember"},
    ).json()["id"]
    sid = client.post(
        "/api/interviews/sessions",
        headers=owner,
        json={"config_id": cid, "title": "Garden interview", "provider_consent": True},
    ).json()["id"]
    interview_db.add(
        InterviewTurn(
            session_id=sid,
            request_id="fixture-source",
            sequence=1,
            role="user",
            text="I remember our garden.",
            original_text="I remember our garden.",
        )
    )
    interview_db.get(InterviewSession, sid).status = "review"
    interview_db.commit()
    return sid


def create(client, owner, source):
    response = client.post(BASE, headers=owner, json={"session_id": source})
    assert response.status_code == 201, response.text
    return response.json()


def run(client, owner, state, interview_db, kind="draft", seconds=10, provider=Provider):
    response = client.post(
        BASE + "/" + state["id"] + "/generate",
        headers=owner,
        json={
            "revision": state["revision"],
            "kind": kind,
            "sections": 1,
            "seconds": seconds,
            "consent": True,
        },
    )
    assert response.status_code == 200, response.text
    interview_db.expire_all()
    generation = interview_db.get(Screenplay, state["id"]).generation
    run_generation(
        state["id"], generation, sessionmaker(bind=interview_db.bind, expire_on_commit=False), provider
    )
    interview_db.expire_all()
    return client.get(BASE + "/" + state["id"], headers=owner).json()


def save_payload(s):
    return {
        "revision": s["revision"],
        "title": s["title"],
        "reviewed_markdown": s["reviewed_markdown"],
        "sections": [
            {
                "id": p["id"],
                "content": p["content"],
                "subsections": [
                    {"id": u["id"], "seconds": u["seconds"], "content": u["content"]}
                    for u in p["subsections"]
                ],
            }
            for p in s["sections"]
        ],
    }


@pytest.mark.parametrize("seconds,count", [(10, 6), (15, 4)])
def test_edit_generate_breakdown_export_reload(client, owner, source, interview_db, storage, seconds, count):
    s = create(client, owner, source)
    assert s["interview_uid"] == source and "garden" in s["reviewed_markdown"]
    payload = save_payload(s)
    payload["reviewed_markdown"] += "\nThe garden belonged to my father."
    saved = client.put(BASE + "/" + s["id"], headers=owner, json=payload)
    assert saved.status_code == 200, saved.text
    s = run(client, owner, saved.json(), interview_db)
    assert len(s["sections"]) == 1 and s["sections"][0]["seconds"] == 60
    s = run(client, owner, s, interview_db, "breakdown", seconds)
    subs = s["sections"][0]["subsections"]
    assert len(subs) == count and sum(u["seconds"] for u in subs) == 60
    assert [u["start_seconds"] for u in subs] == list(range(0, 60, seconds))
    assert all(u["interview_uid"] == source and u["section_id"] == s["sections"][0]["id"] for u in subs)
    payload = save_payload(s)
    payload["sections"][0]["subsections"][0]["content"]["elements"][1]["text"] = (
        "Sunlight falls across the FAMILY PHOTO."
    )
    saved = client.put(BASE + "/" + s["id"], headers=owner, json=payload)
    assert saved.status_code == 200, saved.text
    parent = saved.json()["sections"][0]
    assert not parent["breakdown_stale"]
    assert [u["id"] for u in parent["subsections"]] == [u["id"] for u in subs]
    assert parent["content"]["elements"] == [
        e for sub in parent["subsections"] for e in sub["content"]["elements"]
    ]
    reloaded = client.get(BASE + "/" + s["id"], headers=owner).json()
    assert reloaded["sections"][0]["content"] == parent["content"]
    saved_again = client.put(BASE + "/" + s["id"], headers=owner, json=save_payload(reloaded))
    assert saved_again.status_code == 200
    assert saved_again.json()["sections"][0]["content"] == parent["content"]
    export = client.post(BASE + "/" + s["id"] + "/export", headers=owner)
    assert export.status_code == 200, export.text
    text = export.json()["markdown"]
    assert source in text and subs[0]["id"] in text and "FAMILY PHOTO" in text
    assert "                      NARRATOR (V.O.)" in text
    assert storage.objects[export.json()["storage_key"]].decode() == text
    assert export.json()["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert client.get(BASE + "/" + s["id"], headers=owner).json()["exports"]
    assert client.delete("/api/interviews/sessions/" + source, headers=owner).status_code == 409


def test_scope_ids_revision_and_timing_validation(client, owner, source, interview_db):
    s = run(client, owner, create(client, owner, source), interview_db)
    s = run(client, owner, s, interview_db, "breakdown")
    other = account(client, "screenplay-other@example.com")
    assert client.get(BASE + "/" + s["id"], headers=other).status_code == 404
    assert client.post(BASE, headers=other, json={"session_id": source}).status_code == 404
    payload = save_payload(s)
    payload["revision"] -= 1
    assert client.put(BASE + "/" + s["id"], headers=owner, json=payload).status_code == 409
    payload = save_payload(s)
    payload["sections"][0]["subsections"][0]["seconds"] = 15
    assert client.put(BASE + "/" + s["id"], headers=owner, json=payload).status_code == 422
    payload = save_payload(s)
    payload["sections"][0]["subsections"][0]["id"] = str(uuid4())
    assert client.put(BASE + "/" + s["id"], headers=owner, json=payload).status_code == 422
    payload = save_payload(s)
    payload["sections"][0]["content"]["material_ids"] = ["foreign-material"]
    assert client.put(BASE + "/" + s["id"], headers=owner, json=payload).status_code == 422


def test_source_and_section_edits_invalidate_derived_content(client, owner, source, interview_db):
    s = run(client, owner, create(client, owner, source), interview_db)
    s = run(client, owner, s, interview_db, "breakdown")
    payload = save_payload(s)
    payload["sections"][0]["content"]["notes"] = "Revised staging"
    s = client.put(BASE + "/" + s["id"], headers=owner, json=payload).json()
    assert s["sections"][0]["breakdown_stale"]
    assert client.post(BASE + "/" + s["id"] + "/export", headers=owner).status_code == 409
    payload = save_payload(s)
    payload["reviewed_markdown"] += "\nA corrected memory."
    s = client.put(BASE + "/" + s["id"], headers=owner, json=payload).json()
    assert s["draft_stale"]
    assert (
        client.post(
            BASE + "/" + s["id"] + "/generate",
            headers=owner,
            json={"revision": s["revision"], "kind": "breakdown", "consent": True},
        ).status_code
        == 409
    )


def test_failed_and_stopped_generation_preserves_saved_sections(client, owner, source, interview_db):
    s = run(client, owner, create(client, owner, source), interview_db)
    original = s["sections"][0]["id"]

    class Invalid(Provider):
        def generate(self, task, data, schema):
            return DraftOutput(sections=[content(), content()])

    failed = run(client, owner, s, interview_db, provider=Invalid)
    assert failed["state"] == "failed" and failed["sections"][0]["id"] == original

    class Stop(Provider):
        def generate(self, task, data, schema):
            assert client.post(BASE + "/" + s["id"] + "/stop", headers=owner).status_code == 200
            return super().generate(task, data, schema)

    stopped = run(client, owner, failed, interview_db, provider=Stop)
    assert stopped["state"] == "idle" and stopped["sections"][0]["id"] == original


def test_markdown_import_uid_materials_and_delete(client, owner, project, db, storage):
    uid = str(uuid4())
    response = client.post(
        BASE,
        headers=owner,
        json={
            "project_id": project,
            "filename": "interview.md",
            "markdown": f"# Story\nInterview UID: {uid}\nAn old photograph shows a garden.",
        },
    )
    assert response.status_code == 201, response.text
    s = response.json()
    assert s["interview_uid"] == uid and s["session_id"] is None
    original = b"An old family article"
    asset = MediaAsset(
        project_id=project,
        original_filename="article.txt",
        mime_type="text/plain",
        size_bytes=len(original),
        status=MediaStatus.ready,
        storage_key="source-" + new_id(),
        checksum_sha256=hashlib.sha256(original).hexdigest(),
    )
    db.add(asset)
    db.commit()
    storage.objects[asset.storage_key] = original
    attached = client.post(
        BASE + "/" + s["id"] + "/materials",
        headers=owner,
        json={"asset_ids": [asset.id], "revision": s["revision"]},
    )
    assert attached.status_code == 200, attached.text
    s = attached.json()
    m = s["materials"][0]
    assert m["session_id"] == uid and uid in m["storage_key"]
    assert storage.objects[m["storage_key"]] == original
    assert client.delete("/api/projects/" + project, headers=owner).status_code == 409
    assert client.delete(BASE + "/" + s["id"], headers=owner).status_code == 204
    assert m["storage_key"] not in storage.objects and asset.storage_key in storage.objects


def test_subsection_merge_uses_stored_order_and_accepts_long_sections(client, owner, source, interview_db):
    s = run(client, owner, create(client, owner, source), interview_db)
    s = run(client, owner, s, interview_db, "breakdown")
    payload = save_payload(s)
    children = payload["sections"][0]["subsections"]
    for i, sub in enumerate(children):
        sub["content"]["elements"] = [{"kind": "action", "text": f"Shot {i}.{j}"} for j in range(12)]
    children.reverse()
    response = client.put(BASE + "/" + s["id"], headers=owner, json=payload)
    assert response.status_code == 200, response.text
    parent = response.json()["sections"][0]
    assert len(parent["content"]["elements"]) == 73
    assert parent["content"]["elements"][1]["text"] == "Shot 0.0"
    assert parent["content"]["elements"][-1]["text"] == "Shot 5.11"
    assert not parent["breakdown_stale"]
    assert (
        client.put(BASE + "/" + s["id"], headers=owner, json=save_payload(response.json())).status_code == 200
    )


def test_subsection_save_does_not_overwrite_separate_parent_edits(client, owner, source, interview_db):
    s = run(client, owner, create(client, owner, source), interview_db)
    s = run(client, owner, s, interview_db, "breakdown")
    payload = save_payload(s)
    payload["sections"][0]["content"]["notes"] = "Keep this parent edit"
    payload["sections"][0]["subsections"][0]["content"]["notes"] = "Child edit"
    assert client.put(BASE + "/" + s["id"], headers=owner, json=payload).status_code == 409
    assert client.get(BASE + "/" + s["id"], headers=owner).json()["revision"] == s["revision"]
    payload = save_payload(client.get(BASE + "/" + s["id"], headers=owner).json())
    payload["sections"][0]["content"]["notes"] = "Saved parent edit"
    saved = client.put(BASE + "/" + s["id"], headers=owner, json=payload).json()
    payload = save_payload(saved)
    payload["sections"][0]["subsections"][0]["content"]["notes"] = "Stale child edit"
    assert client.put(BASE + "/" + s["id"], headers=owner, json=payload).status_code == 409
    assert (
        client.get(BASE + "/" + s["id"], headers=owner).json()["sections"][0]["content"]["notes"]
        == "Saved parent edit"
    )


def test_export_fences_preserve_literal_script_text():
    from app.screenplay_routes import fenced_content

    script = {"elements": [{"kind": "action", "text": "A sign reads ~~remember~~ and ~~~.\n```"}]}
    assert fenced_content(script) == "````text\nA sign reads ~~remember~~ and ~~~.\n```\n````"
