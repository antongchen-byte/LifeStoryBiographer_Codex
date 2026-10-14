"""Non-destructive 16:9 crops of uploaded and archived photo materials."""

import base64
import io
import math
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from pydantic import Field

from .cinema_routes import production_access
from .domain.errors import DomainError
from .domain.processing import checksum
from .interview_models import InterviewMaterial
from .interview_routes import IDB, material_record, session_access
from .main import DB, Actor, Storage
from .models import MediaAsset, MediaStatus, new_id
from .schemas import Boundary
from .screenplay_routes import access
from .services import media, projects

router = APIRouter(prefix="/api/photos", tags=["photos"])


class Redaction(Boundary):
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    width: float = Field(gt=0, le=1, allow_inf_nan=False)
    height: float = Field(gt=0, le=1, allow_inf_nan=False)


class Crop(Boundary):
    crop_enabled: bool = True
    redactions: list[Redaction] = Field(default_factory=list, max_length=100)
    x: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    y: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    zoom: float = Field(default=1, ge=1, le=8, allow_inf_nan=False)
    resolution: Literal["original", "720p", "1080p", "4k"] = "original"


def surrounding_color(image, box):
    """Average samples immediately outside the selection, from the unchanged source."""
    left, top, right, bottom = box
    samples = []
    for i in range(32):
        x = min(image.width - 1, left + int((right - left) * (i + .5) / 32))
        y = min(image.height - 1, top + int((bottom - top) * (i + .5) / 32))
        if top > 0:
            samples.append(image.getpixel((x, top - 1)))
        if bottom < image.height:
            samples.append(image.getpixel((x, bottom)))
        if left > 0:
            samples.append(image.getpixel((left - 1, y)))
        if right < image.width:
            samples.append(image.getpixel((right, y)))
    if not samples:
        raise DomainError(422, "Leave some surrounding photo outside the box to sample its color")
    return tuple(round(sum(pixel[c] for pixel in samples) / len(samples)) for c in range(3))


def crop_box(width, height, crop):
    # Whole multiples of 16x9 preserve exact aspect ratio without native-mode upscaling.
    scale = math.floor(min(width / 16, height / 9) / crop.zoom)
    if scale < 1:
        raise DomainError(
            422, "This crop is too small. Reduce zoom; at least 16 × 9 source pixels are required"
        )
    w, h = scale * 16, scale * 9
    left, top = round((width - w) * crop.x), round((height - h) * crop.y)
    return left, top, left + w, top + h


def source(main, db, user, scope, container, identifier, write=False):
    if scope == "media":
        projects.access(main, container, user, write=write)
        asset = media.find(main, container, identifier)
        if asset.status != MediaStatus.ready:
            raise DomainError(409, "Wait for photo processing to finish")
        record = {
            "id": asset.id,
            "filename": asset.original_filename,
            "mime_type": asset.mime_type,
            "storage_key": asset.storage_key,
            "sha256": asset.checksum_sha256,
        }
        project_id, uid = container, None
    elif scope == "interview":
        session = session_access(db, main, user, container)
        material = db.get(InterviewMaterial, identifier)
        if not material or material.session_id != session.id:
            raise DomainError(404, "Photo not found")
        record, project_id, uid = material_record(material), session.project_id, session.id
    elif scope in {"screenplay", "cinema"}:
        if scope == "screenplay":
            owner = access(main, db, user, container)
            materials, project_id, uid = owner.materials, owner.project_id, owner.interview_uid
        else:
            owner = production_access(main, db, user, container)
            materials, project_id, uid = (
                owner.snapshot["materials"],
                owner.snapshot["project_id"],
                owner.interview_uid,
            )
        record = next((m for m in materials if m["id"] == identifier), None)
        if not record:
            raise DomainError(404, "Photo not found")
    else:
        raise DomainError(404, "Photo source not found")
    if not record["mime_type"].startswith("image/"):
        raise DomainError(422, "Only uploaded pictures can be cropped")
    return record, project_id, uid


def decoded(storage, key, directory):
    original = directory / "source"
    storage.download(key, original)
    try:
        with Image.open(original) as raw:
            raw.load()
            oriented = ImageOps.exif_transpose(raw)
            image = Image.new("RGB", oriented.size, "white")
            if "A" in oriented.getbands() or "transparency" in oriented.info:
                rgba = oriented.convert("RGBA")
                image.paste(rgba, mask=rgba.getchannel("A"))
            else:
                image.paste(oriented.convert("RGB"))
            return image
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise DomainError(422, "This photo could not be decoded safely") from error


@router.get("/{scope}/{container}/{identifier}/preview")
def preview(scope: str, container: str, identifier: str, main: DB, db: IDB, user: Actor, storage: Storage):
    record, _, _ = source(main, db, user, scope, container, identifier)
    with tempfile.TemporaryDirectory() as tmp:
        image = decoded(storage, record["storage_key"], Path(tmp))
        width, height = image.size
        image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        data = io.BytesIO()
        image.save(data, "JPEG", quality=90)
        return {
            "width": width,
            "height": height,
            "url": "data:image/jpeg;base64," + base64.b64encode(data.getvalue()).decode(),
        }


@router.post("/{scope}/{container}/{identifier}/crop", status_code=201)
def save_crop(
    scope: str, container: str, identifier: str, body: Crop, main: DB, db: IDB, user: Actor, storage: Storage
):
    record, project_id, uid = source(main, db, user, scope, container, identifier, write=True)
    aid = new_id()
    key = f"projects/{project_id}/originals/{aid}.jpg"
    thumb_key = f"projects/{project_id}/processed/{aid}/thumbnail.jpg"
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        image = decoded(storage, record["storage_key"], work)
        if not body.crop_enabled and not body.redactions:
            raise DomainError(422, "Mark at least one text area to remove")
        original_pixels = image.copy()
        draw = ImageDraw.Draw(image)
        for area in body.redactions:
            if area.x + area.width > 1.000001 or area.y + area.height > 1.000001:
                raise DomainError(422, "Text areas must stay inside the photo")
            bounds = (math.floor(area.x * image.width), math.floor(area.y * image.height),
                      min(image.width, math.ceil((area.x + area.width) * image.width)),
                      min(image.height, math.ceil((area.y + area.height) * image.height)))
            color = surrounding_color(original_pixels, bounds)
            draw.rectangle((bounds[0], bounds[1], bounds[2] - 1, bounds[3] - 1), fill=color)

        box = crop_box(*image.size, body) if body.crop_enabled else (0, 0, *image.size)
        cropped = image.crop(box)
        size = {"720p": (1280, 720), "1080p": (1920, 1080), "4k": (3840, 2160)}.get(
            body.resolution, cropped.size
        )
        if size != cropped.size:
            cropped = cropped.resize(size, Image.Resampling.LANCZOS)
        output, thumbnail = work / "crop.jpg", work / "thumbnail.jpg"
        cropped.save(output, "JPEG", quality=95, subsampling=0)
        cropped.thumbnail((640, 640), Image.Resampling.LANCZOS)
        cropped.save(thumbnail, "JPEG", quality=85)
        suffix = "text-removed" if body.redactions else "16x9"
        filename = Path(record["filename"]).stem[:200] + f"-{suffix}-{aid[:8]}.jpg"
        asset = MediaAsset(
            id=aid,
            project_id=project_id,
            original_filename=filename,
            mime_type="image/jpeg",
            size_bytes=output.stat().st_size,
            storage_key=key,
            thumbnail_key=thumb_key,
            width=size[0],
            height=size[1],
            checksum_sha256=checksum(output),
            status=MediaStatus.ready,
            ownership_declared=True,
            details={
                "crop_source": {"scope": scope, "container": container, "id": identifier},
                "source_sha256": record.get("sha256"),
                "interview_uid": uid,
                "crop": body.model_dump(),
                "crop_box": box,
            },
        )
        try:
            storage.put(key, output, "image/jpeg")
            storage.put(thumb_key, thumbnail, "image/jpeg")
            main.add(asset)
            projects.audit(main, project_id, user.id, "media.cropped", aid)
            main.commit()
        except Exception:
            main.rollback()
            storage.delete(key)
            storage.delete(thumb_key)
            raise
        return {"asset": media.present(asset), "download_url": storage.sign_download(key, filename)}
