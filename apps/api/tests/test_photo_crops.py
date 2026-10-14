import io

import pytest
from conftest import account
from PIL import Image

from app.models import MediaAsset, MediaStatus, new_id
from app.photo_routes import Crop, crop_box


@pytest.fixture
def photo(project, db, storage):
    data = io.BytesIO()
    image = Image.new("RGB", (1600, 1200), "red")
    image.paste("blue", (0, 600, 1600, 1200))
    image.paste("black", (250, 250, 350, 350))
    image.save(data, "PNG")
    asset = MediaAsset(
        id=new_id(),
        project_id=project,
        original_filename="family.png",
        mime_type="image/png",
        size_bytes=len(data.getvalue()),
        storage_key="fixture-photo",
        status=MediaStatus.ready,
        width=1600,
        height=1200,
        ownership_declared=True,
    )
    storage.objects[asset.storage_key] = data.getvalue()
    db.add(asset)
    db.commit()
    return asset


def test_native_crop_preserves_original_and_stores_provenance(client, owner, photo, storage, db):
    base = f"/api/photos/media/{photo.project_id}/{photo.id}"
    original = storage.objects[photo.storage_key]
    preview = client.get(base + "/preview", headers=owner)
    assert preview.status_code == 200
    assert preview.json()["width"] == 1600 and preview.json()["height"] == 1200
    result = client.post(base + "/crop", headers=owner, json={"zoom": 2, "x": 0, "y": 1})
    assert result.status_code == 201, result.text
    asset = result.json()["asset"]
    assert (asset["width"], asset["height"]) == (800, 450)
    assert asset["status"] == "ready" and asset["has_thumbnail"]
    derived = db.get(MediaAsset, asset["id"])
    with Image.open(io.BytesIO(storage.objects[derived.storage_key])) as image:
        assert image.size == (800, 450)
        assert image.getpixel((100, 100))[2] > 240
    assert derived.details["crop_source"]["id"] == photo.id
    assert storage.objects[photo.storage_key] == original
    assert db.get(MediaAsset, photo.id).width == 1600


@pytest.mark.parametrize(
    "resolution,size", [("720p", (1280, 720)), ("1080p", (1920, 1080)), ("4k", (3840, 2160))]
)
def test_resize_dimensions(client, owner, photo, resolution, size):
    result = client.post(
        f"/api/photos/media/{photo.project_id}/{photo.id}/crop",
        headers=owner,
        json={"resolution": resolution},
    )
    assert result.status_code == 201, result.text
    assert (result.json()["asset"]["width"], result.json()["asset"]["height"]) == size


def test_crop_scope_and_bounds(client, owner, photo):
    other = account(client, "crop-other@example.com")
    base = f"/api/photos/media/{photo.project_id}/{photo.id}"
    assert client.get(base + "/preview", headers=other).status_code in {403, 404}
    assert client.post(base + "/crop", headers=other, json={}).status_code in {403, 404}
    for payload in [{"x": -1}, {"y": 2}, {"zoom": 0}, {"resolution": "huge"}]:
        assert client.post(base + "/crop", headers=owner, json=payload).status_code == 422
    assert crop_box(900, 1600, Crop()) == (2, 548, 898, 1052)


def test_text_removal_covers_pixels_preserves_dimensions_and_original(client, owner, photo, storage, db):
    original = storage.objects[photo.storage_key]
    base = f"/api/photos/media/{photo.project_id}/{photo.id}/crop"
    result = client.post(base, headers=owner, json={"crop_enabled": False, "redactions": [
        {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.3}
    ]})
    assert result.status_code == 201, result.text
    asset = db.get(MediaAsset, result.json()["asset"]["id"])
    with Image.open(io.BytesIO(storage.objects[asset.storage_key])) as image:
        assert image.size == (1600, 1200)
        assert image.getpixel((300, 300))[0] > 240
        assert image.getpixel((300, 300))[1] < 10
        assert image.getpixel((1000, 300))[0] > 240
        assert not image.getexif()
    assert storage.objects[photo.storage_key] == original
    assert "text-removed" in asset.original_filename
    assert client.post(base, headers=owner, json={"crop_enabled": False}).status_code == 422
    assert client.post(base, headers=owner, json={"redactions": [
        {"x": .9, "y": 0, "width": .3, "height": .2}
    ]}).status_code == 422
