import io
import json
import subprocess
import zipfile

import pytest
from conftest import account
from sqlalchemy.orm import sessionmaker
from test_screenplays import create, run, source  # noqa: F401

from app.cinema_models import CinemaJob
from app.workflows.cinema_activities import run_cinema


@pytest.fixture
def production(client, owner, source, interview_db):  # noqa: F811
    s = run(client, owner, create(client, owner, source), interview_db)
    s = run(client, owner, s, interview_db, "breakdown")
    assert client.post(f"/api/interviews/screenplays/{s['id']}/export", headers=owner).status_code == 200
    response = client.post(f"/api/cinema/screenplays/{s['id']}", headers=owner)
    assert response.status_code == 200, response.text
    return response.json()


def generate(client, owner, p, index, **kwargs):
    unit = p["units"][index]
    return client.post(
        f"/api/cinema/{p['id']}/subsections/{unit['id']}/generate",
        headers=owner,
        json={
            "prompt": "A hand opens the garden gate.",
            "continuity": "The same gardener in a blue coat, brick garden wall.",
            "consent": True,
            "expected_clip_id": unit["clip"]["id"] if unit["clip"] else None,
            **kwargs,
        },
    )


def ready(interview_db, p, index):
    job = interview_db.get(CinemaJob, p["units"][index]["clip"]["id"])
    job.state, job.output_key, job.frame_key, job.duration = "ready", f"{job.id}.mp4", f"{job.id}.png", 8
    interview_db.commit()
    return job


def approve(client, owner, p, index):
    clip = p["units"][index]["clip"]
    path = f"/api/cinema/{p['id']}/clips/{clip['id']}"
    assert client.post(path + "/previewed", headers=owner).status_code == 200
    response = client.post(path + "/review", headers=owner, json={"approved": True})
    assert response.status_code == 200, response.text
    return response.json()


def test_scope_snapshots_and_clip_validation(client, owner, production, interview_db):
    p = production
    assert client.post(f"/api/cinema/screenplays/{p['screenplay_id']}", headers=owner).json()["id"] == p["id"]
    other = account(client, "cinema-other@example.com")
    assert client.get(f"/api/cinema/{p['id']}", headers=other).status_code == 404
    assert generate(client, other, p, 0).status_code == 404
    assert generate(client, owner, p, 0, consent=False).status_code == 422
    assert generate(client, owner, p, 0, previous_frame=True).status_code == 422
    assert generate(client, owner, p, 1, previous_frame=True).status_code == 409
    assert generate(client, owner, p, 0, material_ids=["foreign-photo"]).status_code == 422
    response = generate(client, owner, p, 0)
    assert response.status_code == 202
    assert generate(client, owner, p, 0).status_code == 409
    assert client.post(f"/api/cinema/{p['id']}/renders/bundle", headers=owner).status_code == 409
    assert (
        client.delete(f"/api/interviews/screenplays/{p['screenplay_id']}", headers=owner).status_code == 409
    )
    job = ready(interview_db, response.json(), 0)
    assert (
        client.post(
            f"/api/cinema/{p['id']}/clips/{job.id}/review", headers=owner, json={"approved": True}
        ).status_code
        == 409
    )


def test_continuity_inherits_seed_and_invalidates_downstream(client, owner, production, interview_db):
    p = generate(client, owner, production, 0).json()
    ready(interview_db, p, 0)
    p = approve(client, owner, p, 0)
    p = generate(client, owner, p, 1, previous_frame=True, continuity="should not replace seed").json()
    assert p["units"][1]["clip"]["request"]["continuity"] == p["units"][0]["clip"]["request"]["continuity"]
    ready(interview_db, p, 1)
    p = approve(client, owner, p, 1)
    p = generate(client, owner, p, 2, previous_frame=True).json()
    ready(interview_db, p, 2)
    p = approve(client, owner, p, 2)
    p = generate(client, owner, p, 3).json()  # A fresh seed breaks the dependency chain.
    ready(interview_db, p, 3)
    p = approve(client, owner, p, 3)
    p = generate(client, owner, p, 0).json()
    assert p["units"][1]["stale"] and p["units"][2]["stale"]
    assert not p["units"][3]["stale"]
    clip = p["units"][1]["clip"]
    assert (
        client.post(
            f"/api/cinema/{p['id']}/clips/{clip['id']}/review", headers=owner, json={"approved": True}
        ).status_code
        == 409
    )


@pytest.fixture
def sample_video(tmp_path):
    path = tmp_path / "sample.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=320x180:r=24:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path.read_bytes()


def test_worker_generation_archive_and_stitch(client, owner, production, interview_db, storage, sample_video):
    calls = []

    class Provider:
        def submit(self, prompt, continuity, first_frame, references):
            calls.append((prompt, first_frame.read_bytes() if first_frame else None, references))
            return "models/veo-3.1-generate-preview/operations/fixture"

        def poll(self, operation):
            return "fixture"

        def download(self, uri, path):
            path.write_bytes(sample_video)

    factory = sessionmaker(bind=interview_db.bind, expire_on_commit=False)
    p = production
    for i in range(len(p["units"])):
        p = generate(client, owner, p, i, previous_frame=i > 0).json()
        run_cinema(p["units"][i]["clip"]["id"], factory, storage, Provider, pause=lambda _: None)
        interview_db.expire_all()
        p = approve(client, owner, p, i)
    assert p["all_approved"]
    assert calls[0][1] is None and calls[1][1].startswith(b"\x89PNG")
    assert client.post(f"/api/cinema/{p['id']}/renders/stitch", headers=owner).status_code == 409
    p = client.post(f"/api/cinema/{p['id']}/renders/bundle", headers=owner).json()
    bundle = p["renders"][-1]
    run_cinema(bundle["id"], factory, storage)
    interview_db.expire_all()
    job = interview_db.get(CinemaJob, bundle["id"])
    assert job.state == "ready", job.error
    with zipfile.ZipFile(io.BytesIO(storage.objects[job.output_key])) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["interview_uid"] == p["interview_uid"]
        assert [clip["subsection_id"] for clip in manifest["clips"]] == [u["id"] for u in p["units"]]
        assert len([name for name in archive.namelist() if name.endswith(".mp4")]) == 6
    response = client.post(f"/api/cinema/{p['id']}/renders/stitch", headers=owner)
    assert response.status_code == 202
    film = next(j for j in response.json()["renders"] if j["kind"] == "stitch")
    run_cinema(film["id"], factory, storage)
    interview_db.expire_all()
    stitched = interview_db.get(CinemaJob, film["id"])
    assert stitched.state == "ready", stitched.error
    assert 5.9 <= stitched.duration <= 6.5
    # Duplicate requests reuse the same archive and film.
    assert len(client.post(f"/api/cinema/{p['id']}/renders/stitch", headers=owner).json()["renders"]) == 2


def test_restart_resumes_operation_without_resubmitting(
    client, owner, production, interview_db, storage, sample_video
):
    p = generate(client, owner, production, 0).json()
    job = interview_db.get(CinemaJob, p["units"][0]["clip"]["id"])
    job.operation, job.state = "models/veo-3.1-generate-preview/operations/recovered", "polling"
    interview_db.commit()

    class Provider:
        def submit(self, *args):
            raise AssertionError("Must not create another paid request")

        def poll(self, operation):
            assert operation.endswith("recovered")
            return "fixture"

        def download(self, uri, path):
            path.write_bytes(sample_video)

    run_cinema(job.id, sessionmaker(bind=interview_db.bind), storage, Provider)
    interview_db.expire_all()
    assert interview_db.get(CinemaJob, job.id).state == "ready"


def test_interrupted_submission_is_not_automatically_resubmitted(
    client, owner, production, interview_db, storage
):
    p = generate(client, owner, production, 0).json()
    job = interview_db.get(CinemaJob, p["units"][0]["clip"]["id"])
    job.state = "submitting"
    interview_db.commit()

    def forbidden():
        raise AssertionError("Must not submit an ambiguous request twice")

    run_cinema(job.id, sessionmaker(bind=interview_db.bind), storage, forbidden)
    interview_db.expire_all()
    assert interview_db.get(CinemaJob, job.id).state == "failed"


def test_selected_photo_is_decoded_and_sent_as_png(
    client, owner, production, interview_db, storage, sample_video
):
    from PIL import Image

    from app.cinema_models import CinemaProduction

    raw = io.BytesIO()
    Image.new("RGB", (30, 20), "red").save(raw, "JPEG")
    storage.objects["selected-photo"] = raw.getvalue()
    p = interview_db.get(CinemaProduction, production["id"])
    snapshot = json.loads(json.dumps(p.snapshot))
    snapshot["materials"] = [
        {"id": "photo", "filename": "family.jpg", "mime_type": "image/jpeg", "storage_key": "selected-photo"}
    ]
    snapshot["sections"][0]["subsections"][0]["content"]["material_ids"] = ["photo"]
    p.snapshot = snapshot
    interview_db.commit()
    state = generate(client, owner, production, 0, material_ids=["photo"]).json()
    seen = []

    class Provider:
        def submit(self, prompt, continuity, first_frame, references):
            seen.append(references[0].read_bytes())
            assert first_frame is None and len(references) == 1
            return "models/veo-3.1-generate-preview/operations/photo"

        def poll(self, operation):
            return "fixture"

        def download(self, uri, path):
            path.write_bytes(sample_video)

    run_cinema(state["units"][0]["clip"]["id"], sessionmaker(bind=interview_db.bind), storage, Provider)
    interview_db.expire_all()
    assert seen[0].startswith(b"\x89PNG")
    assert interview_db.get(CinemaJob, state["units"][0]["clip"]["id"]).state == "ready"


def test_continuity_can_start_from_unapproved_ready_clip(client, owner, production, interview_db):
    p = generate(client, owner, production, 0).json()
    ready(interview_db, p, 0)
    response = generate(client, owner, p, 1, previous_frame=True)
    assert response.status_code == 202, response.text
    p = response.json()
    assert not p["units"][0]["clip"]["approved"]
    assert p["units"][0]["clip"]["frame_ready"]
    assert not p["units"][1]["stale"]
    ready(interview_db, p, 1)
    response = generate(client, owner, p, 2, previous_frame=True)
    assert response.status_code == 202, response.text
    assert not response.json()["units"][2]["stale"]
    assert client.post(f"/api/cinema/{p['id']}/renders/bundle", headers=owner).status_code == 409


def test_cinema_crop_reference_is_frozen_and_scoped(client, owner, production, interview_db, storage, db):
    from PIL import Image

    from app.cinema_models import CinemaProduction
    from app.models import MediaAsset

    image = io.BytesIO()
    Image.new("RGB", (160, 120), "green").save(image, "PNG")
    storage.objects["cinema-photo"] = image.getvalue()
    p = interview_db.get(CinemaProduction, production["id"])
    snapshot = json.loads(json.dumps(p.snapshot))
    snapshot["materials"] = [
        {"id": "photo", "filename": "garden.png", "mime_type": "image/png", "storage_key": "cinema-photo"}
    ]
    snapshot["sections"][0]["subsections"][0]["content"]["material_ids"] = ["photo"]
    p.snapshot = snapshot
    interview_db.commit()
    cropped = client.post(f"/api/photos/cinema/{p.id}/photo/crop", headers=owner, json={})
    assert cropped.status_code == 201, cropped.text
    aid = cropped.json()["asset"]["id"]
    rejected = generate(
        client, owner, production, 0, material_ids=["photo"], material_variants={"photo": "foreign"}
    )
    assert rejected.status_code == 422
    queued = generate(client, owner, production, 0, material_ids=["photo"], material_variants={"photo": aid})
    assert queued.status_code == 202, queued.text
    job = queued.json()["units"][0]["clip"]
    frozen = job["request"]["reference_keys"]["photo"]
    asset = db.get(MediaAsset, aid)
    assert frozen != asset.storage_key
    assert storage.objects[frozen] == storage.objects[asset.storage_key]
    assert job["request"]["material_variants"] == {"photo": aid}
