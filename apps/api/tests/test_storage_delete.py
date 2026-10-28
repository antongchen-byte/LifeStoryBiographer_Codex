from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from app.storage import S3Storage


@pytest.mark.parametrize("code", ["404", "NoSuchKey", "NotFound", "AccessDenied"])
def test_delete_is_idempotent_but_does_not_hide_permission_errors(code):
    storage = object.__new__(S3Storage)
    storage.bucket = "fixture"
    storage.internal = Mock()
    storage.internal.delete_object.side_effect = ClientError({"Error": {"Code": code}}, "DeleteObject")
    if code == "AccessDenied":
        with pytest.raises(ClientError):
            storage.delete("missing")
    else:
        storage.delete("missing")
