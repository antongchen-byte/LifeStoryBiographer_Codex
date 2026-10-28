from functools import lru_cache
from pathlib import Path
from typing import Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from .config import settings


class ObjectStorage(Protocol):
    def begin(self, key: str, mime: str) -> str: ...
    def sign_part(self, key: str, upload_id: str, number: int, size: int) -> str: ...
    def parts(self, key: str, upload_id: str) -> list[dict]: ...
    def complete(self, key: str, upload_id: str, parts: list[dict]) -> None: ...
    def head(self, key: str) -> dict | None: ...
    def abort(self, key: str, upload_id: str) -> None: ...
    def delete(self, key: str) -> None: ...
    def download(self, key: str, path: Path) -> None: ...
    def put(self, key: str, path: Path, mime: str) -> None: ...
    def sign_download(self, key: str, filename: str | None = None) -> str: ...


class S3Storage:
    def __init__(self) -> None:
        kwargs = dict(
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            config=Config(
                signature_version="s3v4", retries={"max_attempts": 3}, connect_timeout=5, read_timeout=60,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                s3={"addressing_style": "path"},
            ),
            region_name=settings.s3_region,
        )
        self.internal = boto3.client("s3", endpoint_url=settings.s3_endpoint, **kwargs)
        self.public = boto3.client("s3", endpoint_url=settings.s3_public_endpoint, **kwargs)
        self.bucket = settings.s3_bucket

    def encryption(self) -> dict:
        if settings.storage_provider == "gcs":
            return {}  # GCS encrypts objects at rest; do not send AWS SSE headers.
        return {"ServerSideEncryption": "AES256"} if settings.s3_server_side_encryption else {}

    def begin(self, key: str, mime: str) -> str:
        return self.internal.create_multipart_upload(
            Bucket=self.bucket, Key=key, ContentType=mime, **self.encryption()
        )["UploadId"]

    def sign_part(self, key: str, upload_id: str, number: int, size: int) -> str:
        return self.public.generate_presigned_url(
            "upload_part",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "UploadId": upload_id,
                "PartNumber": number,
                "ContentLength": size,
            },
            ExpiresIn=settings.upload_url_seconds,
        )

    def parts(self, key: str, upload_id: str) -> list[dict]:
        paginator = self.internal.get_paginator("list_parts")
        return [
            part
            for page in paginator.paginate(Bucket=self.bucket, Key=key, UploadId=upload_id)
            for part in page.get("Parts", [])
        ]

    def complete(self, key: str, upload_id: str, parts: list[dict]) -> None:
        self.internal.complete_multipart_upload(
            Bucket=self.bucket, Key=key, UploadId=upload_id, MultipartUpload={"Parts": parts}
        )

    def head(self, key: str) -> dict | None:
        try:
            return self.internal.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise

    def abort(self, key: str, upload_id: str) -> None:
        try:
            self.internal.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
        except ClientError as error:
            if error.response["Error"]["Code"] != "NoSuchUpload":
                raise

    def delete(self, key: str) -> None:
        try:
            self.internal.delete_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"404", "NoSuchKey", "NotFound"}:
                raise

    def download(self, key: str, path: Path) -> None:
        self.internal.download_file(self.bucket, key, str(path))

    def put(self, key: str, path: Path, mime: str) -> None:
        self.internal.upload_file(
            str(path), self.bucket, key, ExtraArgs={"ContentType": mime, **self.encryption()}
        )

    def sign_download(self, key: str, filename: str | None = None) -> str:
        from urllib.parse import quote

        params = {"Bucket": self.bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = "attachment; filename*=UTF-8''" + quote(filename, safe="")
        return self.public.generate_presigned_url("get_object", Params=params, ExpiresIn=300)


@lru_cache
def get_storage() -> ObjectStorage:
    return S3Storage()
