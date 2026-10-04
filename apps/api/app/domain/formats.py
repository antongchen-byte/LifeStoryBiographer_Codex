from pathlib import PurePath

from ..config import settings
from .errors import DomainError

MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg",
    ".m4v": "video/x-m4v",
    ".webm": "video/webm",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
}


def validate_upload(filename: str, mime: str, size: int) -> None:
    if "/" in filename or "\\" in filename or any(ord(c) < 32 for c in filename):
        raise DomainError(422, "Use a filename without paths or control characters")
    if MIME.get(PurePath(filename).suffix.lower()) != mime:
        raise DomainError(422, "The file format is unsupported or its MIME type does not match")
    if size <= 0:
        raise DomainError(413, "The file must be nonempty")
    if not mime.startswith(("audio/", "video/")) and size > settings.upload_max_bytes:
        raise DomainError(413, "This non-recording file exceeds the configured upload limit")
    part_size(size)  # Validate storage protocol bounds before initiating an upload.


def part_size(size: int) -> int:
    # Preserve old chunk boundaries for existing uploads; grow only above 10,000 parts.
    step = max(settings.upload_part_bytes, (size + 9999) // 10000)
    if step > 5 * 1024**3:
        raise DomainError(413, "This file exceeds the storage service's multipart capacity")
    return step


def part_sizes(size: int) -> list[int]:
    step = part_size(size)
    return [min(step, size - offset) for offset in range(0, size, step)]
