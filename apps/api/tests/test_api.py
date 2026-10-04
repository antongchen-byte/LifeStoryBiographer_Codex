import hashlib

from conftest import account
from sqlalchemy import func, select

from app.models import MediaAsset, ProcessingJob


def test_authentication_and_revocation(client, owner):
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/auth/me", headers=owner).status_code == 200
    assert client.post("/api/auth/logout", headers=owner).status_code == 204
    assert client.get("/api/auth/me", headers=owner).status_code == 401


def test_project_isolation_and_roles(client, owner, project):
    other = account(client, "other@example.com")
    assert client.get(f"/api/projects/{project}", headers=other).status_code == 404
    assert client.get("/api/projects", headers=other).json() == []
    assert (
        client.post(
            f"/api/projects/{project}/members",
            headers=owner,
            json={"email": "other@example.com", "role": "VIEWER"},
        ).status_code
        == 204
    )
    assert client.get(f"/api/projects/{project}", headers=other).json()["role"] == "VIEWER"
    assert client.patch(f"/api/projects/{project}", headers=other, json={"title": "No"}).status_code == 403
    assert client.delete(f"/api/projects/{project}", headers=other).status_code == 403
    assert (
        client.post(
            f"/api/projects/{project}/members",
            headers=owner,
            json={"email": "other@example.com", "role": "EDITOR"},
        ).status_code
        == 204
    )
    assert (
        client.patch(f"/api/projects/{project}", headers=other, json={"title": "Edited"}).status_code == 200
    )


def test_project_crud_and_audit(client, owner, project):
    assert (
        client.patch(f"/api/projects/{project}", headers=owner, json={"title": "New title"}).json()["title"]
        == "New title"
    )
    assert len(client.get(f"/api/projects/{project}/audit", headers=owner).json()) == 2
    assert client.delete(f"/api/projects/{project}", headers=owner).status_code == 204
    assert client.get(f"/api/projects/{project}", headers=owner).status_code == 404


def begin(client, owner, project):
    body = {
        "filename": "memory.txt",
        "mime_type": "text/plain",
        "size_bytes": 5,
        "idempotency_key": "a-stable-upload-key",
        "ownership_declared": True,
    }
    response = client.post(f"/api/projects/{project}/media/uploads", headers=owner, json=body)
    assert response.status_code == 201
    return response.json(), body


def test_upload_resume_completion_idempotency_and_outbox(client, owner, project, storage, db):
    started, body = begin(client, owner, project)
    asset = db.get(MediaAsset, started["asset_id"])
    storage.uploads[asset.storage_key][1] = b"hello"
    resumed = client.post(f"/api/projects/{project}/media/uploads", headers=owner, json=body).json()
    assert resumed["asset_id"] == asset.id
    assert resumed["uploaded_parts"][0]["part_number"] == 1
    complete = {"parts": [{"part_number": 1, "etag": hashlib.md5(b"hello").hexdigest()}]}
    endpoint = f"/api/projects/{project}/media/{asset.id}/complete"
    assert client.post(endpoint, headers=owner, json=complete).json()["status"] == "uploaded"
    assert client.post(endpoint, headers=owner, json=complete).status_code == 200
    assert storage.completions == 1
    assert db.scalar(select(func.count()).select_from(ProcessingJob)) == 1
    assert db.scalar(select(ProcessingJob)).state == "pending"
    assert client.get(f"/api/projects/{project}/media/{asset.id}/download", headers=owner).status_code == 409
    assert client.delete(f"/api/projects/{project}/media/{asset.id}", headers=owner).status_code == 409


def test_completion_recovers_storage_success_before_database_commit(client, owner, project, storage, db):
    started, _ = begin(client, owner, project)
    asset = db.get(MediaAsset, started["asset_id"])
    storage.objects[asset.storage_key] = b"hello"
    endpoint = f"/api/projects/{project}/media/{asset.id}/complete"
    assert client.post(endpoint, headers=owner, json={"parts": []}).status_code == 200
    assert db.scalar(select(func.count()).select_from(ProcessingJob)) == 1


def test_wrong_parts_do_not_enqueue(client, owner, project, storage, db):
    started, _ = begin(client, owner, project)
    asset = db.get(MediaAsset, started["asset_id"])
    storage.uploads[asset.storage_key][1] = b"wrong size"
    response = client.post(
        f"/api/projects/{project}/media/{asset.id}/complete",
        headers=owner,
        json={"parts": [{"part_number": 1, "etag": "abcdef"}]},
    )
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(ProcessingJob)) == 0


def test_upload_key_cannot_be_reused_for_different_file(client, owner, project):
    _, body = begin(client, owner, project)
    body["filename"] = "different.txt"
    assert client.post(f"/api/projects/{project}/media/uploads", headers=owner, json=body).status_code == 409


def test_duplicate_reminder_across_projects_and_explicit_override(client, owner, project):
    original, body = begin(client, owner, project)
    base = f"/api/projects/{project}/media"
    # Resume identity is not a second copy.
    assert client.post(f"{base}/duplicates", headers=owner, json=body).json() == []
    new = {**body, "idempotency_key": "another-upload-key"}
    matches = client.post(f"{base}/duplicates", headers=owner, json=new).json()
    assert matches[0]["asset_id"] == original["asset_id"]
    assert client.post(f"{base}/uploads", headers=owner, json=new).status_code == 409
    assert (
        client.post(f"{base}/uploads", headers=owner, json={**new, "allow_duplicate": True}).status_code
        == 201
    )
    second = client.post(
        "/api/projects", headers=owner, json={"subject_name": "Second", "title": "Second biography"}
    ).json()["id"]
    other_base = f"/api/projects/{second}/media"
    assert len(client.post(f"{other_base}/duplicates", headers=owner, json=body).json()) == 2
    assert client.post(f"{other_base}/duplicates", headers=owner, json={**body, "size_bytes": 6}).json() == []
    stranger = account(client, "duplicate-stranger@example.com")
    assert client.post(f"{base}/duplicates", headers=stranger, json=body).status_code == 404
    own = client.post(
        "/api/projects", headers=stranger, json={"subject_name": "Other", "title": "Other biography"}
    ).json()["id"]
    assert client.post(f"/api/projects/{own}/media/duplicates", headers=stranger, json=body).json() == []


def test_large_recording_upload_can_start_and_resume(client, owner, project):
    body = {
        "filename": "large-video.mp4",
        "mime_type": "video/mp4",
        "size_bytes": 100 * 1024**3,
        "idempotency_key": "large-recording-fixture",
        "ownership_declared": True,
    }
    url = f"/api/projects/{project}/media/uploads"
    response = client.post(url, headers=owner, json=body)
    assert response.status_code == 201
    data = response.json()
    assert len(data["part_urls"]) <= 10000
    assert data["part_size"] > 8 * 1024**2
    resumed = client.post(url, headers=owner, json=body).json()
    assert resumed == data
