"""Normalize common office formats into PDF without executing document macros."""

import tempfile
import zipfile
from pathlib import Path

from .errors import InvalidMedia
from .processing import command

OFFICE_EXTENSIONS = {".doc", ".docx", ".odt", ".rtf", ".ppt", ".pptx", ".odp", ".xls", ".xlsx", ".ods"}


def office_pdf(source: Path, directory: Path) -> Path:
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(e.file_size for e in entries) > 100 * 1024**2:
                raise InvalidMedia("This document exceeds the uncompressed document limit")
            if any(e.flag_bits & 1 or e.file_size / max(e.compress_size, 1) > 1000 for e in entries):
                raise InvalidMedia("Encrypted or unusually compressed documents are unsupported")
    with tempfile.TemporaryDirectory(dir=directory) as profile:
        user = Path(profile) / "user"
        user.mkdir()
        (user / "registrymodifications.xcu").write_text(
            '<?xml version="1.0"?><oor:items xmlns:oor="http://openoffice.org/2001/registry">'
            '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
            '<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>'
            "</item></oor:items>"
        )
        command(
            [
                "libreoffice",
                "-env:UserInstallation=" + Path(profile).as_uri(),
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                str(directory),
                str(source),
            ],
            180,
        )
    result = directory / (source.stem + ".pdf")
    if not result.exists() or not result.stat().st_size:
        raise InvalidMedia("Document conversion failed. Export an unlocked PDF and try again")
    return result
