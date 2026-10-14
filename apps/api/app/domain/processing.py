import hashlib
import json
import subprocess
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import magic
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
from pypdf import PdfReader

from .errors import InvalidMedia

register_heif_opener()
Image.MAX_IMAGE_PIXELS = 50_000_000


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(args: list[str], timeout: int = 600) -> str:
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True, timeout=timeout)
        return result.stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise InvalidMedia("The media file is damaged, unsupported, or exceeds processing limits") from error


def validate_content(path: Path, mime: str) -> str:
    detected = magic.from_file(str(path), mime=True)
    aliases = {
        "image/jpeg": {"image/jpeg"},
        "image/png": {"image/png"},
        "image/webp": {"image/webp"},
        "image/heic": {"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"},
        "video/mp4": {"video/mp4"},
        "video/x-m4v": {"video/mp4", "video/x-m4v"},
        "video/quicktime": {"video/quicktime"},
        "video/mpeg": {"video/mpeg"},
        "video/webm": {"video/webm"},
        "audio/mpeg": {"audio/mpeg"},
        "audio/wav": {"audio/x-wav", "audio/wav", "audio/vnd.wave"},
        "audio/mp4": {"audio/mp4", "video/mp4", "audio/x-m4a"},
        "audio/aac": {"audio/aac", "audio/x-hx-aac-adts", "audio/x-aac"},
    }
    if mime in aliases and detected not in aliases[mime]:
        raise InvalidMedia("The file content does not match its declared format")
    if mime.startswith("image/"):
        if not detected.startswith("image/"):
            raise InvalidMedia("The file content is not an image")
    elif mime.startswith(("video/", "audio/")):
        if not detected.startswith(("video/", "audio/")) and detected not in {
            "application/ogg",
            "application/octet-stream",
        }:
            raise InvalidMedia("The file content is not audio or video")
    elif mime == "application/pdf":
        if detected != "application/pdf":
            raise InvalidMedia("The file content is not a PDF")
    elif mime.endswith("wordprocessingml.document"):
        if not zipfile.is_zipfile(path):
            raise InvalidMedia("The file content is not a Word document")
    elif mime.startswith("text/"):
        if not detected.startswith("text/"):
            raise InvalidMedia("The file content is not text")
    return detected


def process(path: Path, mime: str, directory: Path) -> dict:
    details: dict = {"detected_mime": validate_content(path, mime)}
    result: dict = {"details": details, "checksum_sha256": checksum(path)}
    thumbnail = directory / "thumbnail.jpg"
    proxy = directory / "proxy.mp4"
    try:
        if mime.startswith("image/"):
            with Image.open(path) as source:
                source.load()
                image = ImageOps.exif_transpose(source)
                result.update(width=image.width, height=image.height)
                image.thumbnail((640, 640))
                image.convert("RGB").save(thumbnail, "JPEG", quality=85)
                result["thumbnail"] = thumbnail
        elif mime.startswith(("video/", "audio/")):
            info = json.loads(
                command(
                    ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], 120
                )
            )
            videos = [
                s
                for s in info["streams"]
                if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")
            ]
            audios = [s for s in info["streams"] if s.get("codec_type") == "audio"]
            if mime.startswith("video/") and not videos or mime.startswith("audio/") and not audios:
                raise InvalidMedia("The file does not contain the expected media stream")
            duration = float(info.get("format", {}).get("duration", 0))
            if duration <= 0 or duration > 4 * 3600:
                raise InvalidMedia("Media duration must be between zero and four hours")
            result["duration_ms"] = round(duration * 1000)
            details["codecs"] = sorted({s.get("codec_name", "unknown") for s in info["streams"]})
            if mime.startswith("video/"):
                video = videos[0]
                result.update(width=video["width"], height=video["height"])
                command(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(path),
                        "-map",
                        "0:v:0",
                        "-frames:v",
                        "1",
                        "-vf",
                        "scale=640:-2",
                        str(thumbnail),
                    ]
                )
                command(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(path),
                        "-map",
                        "0:v:0",
                        "-map",
                        "0:a?",
                        "-vf",
                        "scale='min(1280,iw)':-2",
                        "-c:v",
                        "libx264",
                        "-threads",
                        "2",
                        "-preset",
                        "veryfast",
                        "-crf",
                        "28",
                        "-pix_fmt",
                        "yuv420p",
                        "-c:a",
                        "aac",
                        "-movflags",
                        "+faststart",
                        str(proxy),
                    ],
                    1800,
                )
                result.update(thumbnail=thumbnail, proxy=proxy)
            else:
                audio_proxy = directory / "proxy.mp3"
                command(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(path),
                        "-vn",
                        "-c:a",
                        "libmp3lame",
                        "-b:a",
                        "128k",
                        str(audio_proxy),
                    ],
                    1800,
                )
                result["proxy"] = audio_proxy
        elif mime.endswith("wordprocessingml.document"):
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(e.file_size for e in entries) > 100 * 1024 * 1024:
                    raise InvalidMedia("This document exceeds the uncompressed document limit")
                if any(e.flag_bits & 1 or e.file_size / max(e.compress_size, 1) > 1000 for e in entries):
                    raise InvalidMedia("Encrypted or unusually compressed documents are unsupported")
                if (
                    "word/document.xml" not in archive.namelist()
                    or "[Content_Types].xml" not in archive.namelist()
                ):
                    raise InvalidMedia("The Word document is missing required contents")
                root = ElementTree.fromstring(archive.read("word/document.xml"))
                details["character_count"] = sum(
                    len(e.text or "") for e in root.iter() if e.tag.endswith("}t")
                )
        elif mime in {
            "application/msword",
            "application/rtf",
            "application/vnd.ms-powerpoint",
            "application/vnd.ms-excel",
            "application/vnd.oasis.opendocument.text",
            "application/vnd.oasis.opendocument.presentation",
            "application/vnd.oasis.opendocument.spreadsheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }:
            import shutil

            from .documents import office_pdf
            from .formats import MIME

            suffix = next(ext for ext, value in MIME.items() if value == mime)
            named = directory / ("document" + suffix)
            shutil.copyfile(path, named)
            converted = office_pdf(named, directory)
            details["page_count"] = len(PdfReader(converted).pages)
        elif mime == "application/pdf":
            document = PdfReader(path)
            if document.is_encrypted:
                raise InvalidMedia("Unlock this PDF before uploading it")
            details["page_count"] = len(document.pages)
        else:
            if path.stat().st_size > 20 * 1024 * 1024:
                raise InvalidMedia("Text documents must be smaller than 20 MiB")
            text = path.read_text(encoding="utf-8-sig")
            if "\0" in text:
                raise InvalidMedia("Text contains binary content")
            details.update(character_count=len(text), line_count=len(text.splitlines()))
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        UnicodeError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
        ValueError,
        KeyError,
    ) as error:
        raise InvalidMedia("The file is damaged or its content does not match its format") from error
    return result
