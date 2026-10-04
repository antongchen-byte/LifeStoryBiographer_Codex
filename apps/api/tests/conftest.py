import hashlib
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.interview_database import InterviewBase, get_interview_db
from app.main import app
from app.services import auth
from app.storage import get_storage


class FakeStorage:
    def __init__(self):
        self.uploads = {}
        self.objects = {}
        self.completions = 0

    def begin(self, key, mime):
        self.uploads[key] = {}
        return "test-upload"

    def sign_part(self, key, upload_id, number, size):
        return f"https://storage.test/{key}?part={number}"

    def parts(self, key, upload_id):
        return [
            {"PartNumber": n, "Size": len(data), "ETag": hashlib.md5(data).hexdigest()}
            for n, data in sorted(self.uploads[key].items())
        ]

    def complete(self, key, upload_id, parts):
        self.objects[key] = b"".join(self.uploads[key][p["PartNumber"]] for p in parts)
        self.completions += 1

    def head(self, key):
        return {"ContentLength": len(self.objects[key])} if key in self.objects else None

    def abort(self, key, upload_id):
        self.uploads.pop(key, None)

    def delete(self, key):
        self.objects.pop(key, None)

    def download(self, key, path: Path):
        path.write_bytes(self.objects[key])

    def put(self, key, path, mime):
        self.objects[key] = path.read_bytes()

    def sign_download(self, key, filename=None):
        return "https://storage.test/" + key


@pytest.fixture
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def interview_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    InterviewBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


@pytest.fixture
def storage():
    return FakeStorage()


@pytest.fixture
def client(db, interview_db, storage, monkeypatch):
    app.dependency_overrides[get_interview_db] = lambda: interview_db
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_storage] = lambda: storage
    monkeypatch.setattr(auth, "rate_limit", lambda key: None)
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def account(client, email="owner@example.com"):
    credentials = {"email": email, "password": "a-long-test-password"}
    assert client.post("/api/auth/register", json={**credentials, "name": "Test Author"}).status_code == 201
    response = client.post("/api/auth/login", json=credentials)
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


@pytest.fixture
def owner(client):
    return account(client)


@pytest.fixture
def project(client, owner):
    response = client.post("/api/projects", headers=owner, json={"subject_name": "Test Subject"})
    assert response.status_code == 201
    return response.json()["id"]
