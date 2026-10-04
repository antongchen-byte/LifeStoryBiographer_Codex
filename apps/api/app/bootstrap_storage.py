import time

from botocore.exceptions import ClientError

from .storage import S3Storage


def run() -> None:
    storage = S3Storage()
    for attempt in range(30):
        try:
            storage.internal.list_buckets()
            break
        except Exception:
            if attempt == 29:
                raise
            time.sleep(2)
    try:
        storage.internal.head_bucket(Bucket=storage.bucket)
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchBucket"}:
            raise
        storage.internal.create_bucket(Bucket=storage.bucket)
    # MinIO expires incomplete uploads through its server configuration.
    print("Private development storage is ready")


if __name__ == "__main__":
    run()
