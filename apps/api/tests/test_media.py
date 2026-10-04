import hashlib
import zipfile

import pytest
from PIL import Image
from pydantic import ValidationError

from app.domain.errors import DomainError, InvalidMedia
from app.domain.formats import part_sizes, validate_upload
from app.domain.processing import process
from app.schemas import ProjectUpdate, UploadCreate
from app.services.auth import password_hash, password_matches


@pytest.mark.parametrize(
    "filename,mime",
    [
        ("a.jpg", "application/pdf"),
        ("../a.jpg", "image/jpeg"),
        ("a.exe", "application/octet-stream"),
        ("a\n.jpg", "image/jpeg"),
    ],
)
def test_upload_rejects_invalid_names_and_formats(filename, mime):
    with pytest.raises(DomainError):
        validate_upload(filename, mime, 100)


def test_upload_requires_permission():
    with pytest.raises(ValidationError):
        UploadCreate(
            filename="a.jpg",
            mime_type="image/jpeg",
            size_bytes=10,
            idempotency_key="1234567890abcdef",
            ownership_declared=False,
        )


def test_update_cannot_erase_required_fields():
    with pytest.raises(ValidationError):
        ProjectUpdate(subject_name=None)
    assert ProjectUpdate(title=None).model_dump(exclude_unset=True) == {"title": None}


def test_size_and_multipart_boundaries():
    with pytest.raises(DomainError):
        validate_upload("a.jpg", "image/jpeg", 2**31 + 1)
    assert part_sizes(8 * 1024 * 1024 + 123) == [8 * 1024 * 1024, 123]


def test_password_salts_and_verification():
    first, second = password_hash("test-password"), password_hash("test-password")
    assert first != second
    assert password_matches("test-password", first)
    assert not password_matches("wrong-password", first)


def test_image_checksum_and_thumbnail(tmp_path):
    path = tmp_path / "original.jpg"
    Image.new("RGB", (800, 400), "#aabbcc").save(path)
    result = process(path, "image/jpeg", tmp_path)
    assert result["checksum_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert (result["width"], result["height"]) == (800, 400)
    with Image.open(result["thumbnail"]) as thumbnail:
        assert thumbnail.size == (640, 320)


def test_disguised_file_is_rejected(tmp_path):
    path = tmp_path / "pretend.jpg"
    path.write_text("This is text masquerading as an image.")
    with pytest.raises(InvalidMedia):
        process(path, "image/jpeg", tmp_path)


def test_docx_missing_document_is_rejected(tmp_path):
    path = tmp_path / "broken.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("something.txt", "not a word document")
    with pytest.raises(InvalidMedia):
        process(path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", tmp_path)


def test_docx_metadata(tmp_path):
    path = tmp_path / "memoir.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>A memory</w:t></w:r></w:p></w:body></w:document>',
        )
    result = process(
        path, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", tmp_path
    )
    assert result["details"]["character_count"] == 8


def test_image_declared_with_wrong_image_format_is_rejected(tmp_path):
    path = tmp_path / "pretend.jpg"
    Image.new("RGB", (32, 32)).save(path, format="PNG")
    with pytest.raises(InvalidMedia):
        process(path, "image/jpeg", tmp_path)


def test_large_recordings_and_adaptive_part_boundaries():
    from app.domain.formats import part_size

    for filename, mime in [("long.mp4", "video/mp4"), ("long.wav", "audio/wav")]:
        validate_upload(filename, mime, 3 * 1024**3)
        validate_upload(filename, mime, 100 * 1024**3)
    with pytest.raises(DomainError):
        validate_upload("empty.mp4", "video/mp4", 0)
    with pytest.raises(DomainError):
        validate_upload("large.pdf", "application/pdf", 3 * 1024**3)
    for size in [2 * 1024**3 + 1, 8 * 1024**2 * 10000, 8 * 1024**2 * 10000 + 1, 100 * 1024**3]:
        parts = part_sizes(size)
        assert len(parts) <= 10000
        assert sum(parts) == size
        assert all(p == part_size(size) for p in parts[:-1])
        assert 0 < parts[-1] <= part_size(size)
    with pytest.raises(DomainError, match="multipart capacity"):
        validate_upload("huge.mp4", "video/mp4", 5 * 1024**3 * 10000 + 1)
