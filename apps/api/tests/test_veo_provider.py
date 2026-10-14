import base64
from unittest.mock import Mock

import pytest

from app.ai.veo_provider import VeoProvider, VideoFailure


def test_request_payload_uses_start_frame_and_reference_photos(tmp_path):
    path = tmp_path / "image.png"
    path.write_bytes(b"png-bytes")
    provider = object.__new__(VeoProvider)
    provider.api = Mock(return_value={"name": "models/veo-3.1-generate-preview/operations/test"})
    provider.submit("Current action", "Same gardener", path, [path])
    args, kwargs = provider.api.call_args
    assert args == ("POST", "/models/veo-3.1-generate-preview:predictLongRunning")
    payload = kwargs["json"]
    assert payload["parameters"]["durationSeconds"] == 8
    assert payload["parameters"]["personGeneration"] == "allow_adult"
    instance = payload["instances"][0]
    assert base64.b64decode(instance["image"]["bytesBase64Encoded"]) == b"png-bytes"
    assert instance["referenceImages"][0]["referenceType"] == "asset"
    assert "Same gardener" in instance["prompt"] and "Current action" in instance["prompt"]


def test_poll_pending_ready_and_filtered():
    provider = object.__new__(VeoProvider)
    provider.api = Mock(return_value={"done": False})
    operation = "models/veo-3.1-generate-preview/operations/test"
    assert provider.poll(operation) is None
    provider.api.return_value = {
        "done": True,
        "response": {
            "generateVideoResponse": {
                "generatedSamples": [{"video": {"uri": "https://generativelanguage.googleapis.com/video"}}]
            }
        },
    }
    assert provider.poll(operation).endswith("/video")
    provider.api.return_value = {
        "done": True,
        "response": {"generateVideoResponse": {"raiMediaFilteredCount": 1}},
    }
    with pytest.raises(VideoFailure, match="filtered"):
        provider.poll(operation)
    with pytest.raises(VideoFailure, match="Invalid"):
        provider.poll("../arbitrary")
