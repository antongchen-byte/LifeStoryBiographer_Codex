"""Real API -> signed S3 upload -> Temporal -> FFmpeg acceptance test.
Run against the Compose stack with RUN_LIVE=1. Creates synthetic test data only.
"""

import hashlib
import os
import subprocess
import time
import uuid
import zipfile
from urllib.parse import urlsplit, urlunsplit

import httpx
import pytest
from PIL import Image

pytestmark = pytest.mark.skipif(os.getenv("RUN_LIVE") != "1", reason="Requires the Compose stack")


def storage_request(method, url, **kwargs):
    parsed = urlsplit(url)
    host = os.getenv("STORAGE_CONNECT_HOST")
    if host:
        url = urlunsplit((parsed.scheme, f"{host}:{parsed.port}", parsed.path, parsed.query, parsed.fragment))
    return httpx.request(
        method, url, headers={"Host": parsed.netloc, "Origin": "http://localhost:3000"}, timeout=60, **kwargs
    )


def test_four_formats_processed_and_provenance_retained(tmp_path):
    files = []
    jpg = tmp_path / "portrait.jpg"
    Image.new("RGB", (640, 480), "#8b9e83").save(jpg)
    files.append((jpg, "image/jpeg"))
    for filename, args, mime in [
        (
            "clip.mp4",
            ["-f", "lavfi", "-i", "color=c=green:s=320x240:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p"],
            "video/mp4",
        ),
        (
            "memory.mp3",
            ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:a", "libmp3lame"],
            "audio/mpeg",
        ),
    ]:
        path = tmp_path / filename
        subprocess.run(["ffmpeg", "-v", "error", "-y", *args, str(path)], check=True)
        files.append((path, mime))
    document = tmp_path / "memoir.docx"
    with zipfile.ZipFile(document, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Synthetic test memory.</w:t></w:r></w:p></w:body></w:document>',
        )
    files.append((document, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
    multipart = tmp_path / "long-memory.txt"
    multipart.write_bytes(b"Synthetic memory.\n" * 500000)
    files.append((multipart, "text/plain"))
    with httpx.Client(base_url=os.getenv("API_BASE", "http://api:8000"), timeout=60) as client:
        credentials = {
            "email": f"acceptance-{uuid.uuid4().hex[:12]}@example.com",
            "password": "synthetic-test-password",
        }
        assert (
            client.post("/api/auth/register", json={**credentials, "name": "Acceptance Test"}).status_code
            == 201
        )
        login = client.post("/api/auth/login", json=credentials)
        assert login.status_code == 200
        client.headers["Authorization"] = "Bearer " + login.json()["token"]
        created = client.post("/api/projects", json={"subject_name": "Synthetic Acceptance Subject"})
        assert created.status_code == 201
        project = created.json()["id"]
        expected = {}
        for path, mime in files:
            data = path.read_bytes()
            response = client.post(
                f"/api/projects/{project}/media/uploads",
                json={
                    "filename": path.name,
                    "mime_type": mime,
                    "size_bytes": len(data),
                    "idempotency_key": str(uuid.uuid4()),
                    "ownership_declared": True,
                },
            )
            assert response.status_code == 201, response.text
            upload = response.json()
            parts = []
            for index, url in enumerate(upload["part_urls"]):
                part = storage_request(
                    "PUT", url, content=data[index * upload["part_size"] : (index + 1) * upload["part_size"]]
                )
                assert part.status_code == 200, part.text
                assert "etag" in part.headers
                assert part.headers.get("access-control-allow-origin") == "http://localhost:3000"
                if index == 0 and len(upload["part_urls"]) > 1:
                    resumed = client.get(f"/api/projects/{project}/media/{upload['asset_id']}/upload").json()
                    assert len(resumed["uploaded_parts"]) == 1
                    assert resumed["uploaded_parts"][0]["etag"] == part.headers["etag"]
                parts.append({"part_number": index + 1, "etag": part.headers["etag"]})
            complete = client.post(
                f"/api/projects/{project}/media/{upload['asset_id']}/complete", json={"parts": parts}
            )
            assert complete.status_code == 200, complete.text
            expected[upload["asset_id"]] = hashlib.sha256(data).hexdigest()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            assets = client.get(f"/api/projects/{project}/media").json()
            assert not any(a["status"] == "failed" for a in assets), assets
            if len(assets) == len(files) and all(a["status"] == "ready" for a in assets):
                break
            time.sleep(2)
        assert all(a["status"] == "ready" for a in assets), assets
        for asset in assets:
            assert asset["checksum_sha256"] == expected[asset["id"]]
            if asset["mime_type"].startswith(("image/", "video/")):
                assert asset["has_thumbnail"]
            if asset["mime_type"].startswith(("audio/", "video/")):
                assert asset["duration_ms"] > 0 and asset["has_proxy"]
            url = client.get(f"/api/projects/{project}/media/{asset['id']}/download").json()["url"]
            assert hashlib.sha256(storage_request("GET", url).content).hexdigest() == expected[asset["id"]]
            assert client.delete(f"/api/projects/{project}/media/{asset['id']}").status_code == 204
        assert client.delete(f"/api/projects/{project}").status_code == 204
