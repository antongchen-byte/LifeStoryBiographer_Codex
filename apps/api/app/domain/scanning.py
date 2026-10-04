import socket
import struct
from pathlib import Path
from typing import Protocol

from ..config import settings
from .errors import InvalidMedia


class MalwareScanner(Protocol):
    def scan(self, path: Path) -> str: ...


class DevelopmentScanner:
    def scan(self, path: Path) -> str:
        return "disabled-for-development"


class ClamAVScanner:
    def scan(self, path: Path) -> str:
        with socket.create_connection((settings.clamav_host, settings.clamav_port), timeout=60) as connection:
            connection.settimeout(120)
            connection.sendall(b"zINSTREAM\0")
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    connection.sendall(struct.pack("!I", len(chunk)) + chunk)
            connection.sendall(struct.pack("!I", 0))
            response = b""
            while not response.endswith(b"\0") and len(response) < 4096:
                chunk = connection.recv(4096)
                if not chunk:
                    break
                response += chunk
        if b"FOUND" in response:
            raise InvalidMedia("The security scan rejected this file")
        if not response.rstrip(b"\0").endswith(b"OK"):
            raise RuntimeError("The security scanner could not complete its check")
        return "clean"


def get_scanner() -> MalwareScanner:
    return ClamAVScanner() if settings.scanner == "clamav" else DevelopmentScanner()
