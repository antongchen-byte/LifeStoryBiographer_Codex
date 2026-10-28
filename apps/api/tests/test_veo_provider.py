import base64
from unittest.mock import Mock

import pytest

from app.ai.veo_provider import VeoProvider, VideoFailure


@pytest.mark.parametrize("use_frame", [True, False])
def test_request_payload_uses_separate_image_modes(tmp_path, use_frame):
    path = tmp_path / "image.png"
    path.write_bytes(b"png-bytes")
    provider = object.__new__(VeoProvider)
    provider.api = Mock(return_value={"name": "models/veo-3.1-generate-preview/operations/test"})
    provider.submit("Current action", "Same gardener", path if use_frame else None, [] if use_frame else [path])
    args, kwargs = provider.api.call_args
    assert args == ("POST", "/models/veo-3.1-generate-preview:predictLongRunning")
    payload = kwargs["json"]
    assert payload["parameters"]["durationSeconds"] == 8
    assert payload["parameters"]["personGeneration"] == "allow_adult"
    instance = payload["instances"][0]
    if use_frame:
        assert base64.b64decode(instance["image"]["bytesBase64Encoded"]) == b"png-bytes"
        assert "referenceImages" not in instance
    else:
        assert instance["referenceImages"][0]["referenceType"] == "asset"
        assert "image" not in instance
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


def test_conflicting_images_rejected_before_submission(tmp_path):
    provider = object.__new__(VeoProvider)
    provider.api = Mock()
    with pytest.raises(VideoFailure, match="not both"):
        provider.submit("prompt", "context", tmp_path / "frame", [tmp_path / "photo"])
    provider.api.assert_not_called()


def test_google_error_detail_is_preserved_without_key(monkeypatch):
    import httpx
    provider = object.__new__(VeoProvider)
    provider.key = "test-secret-key"
    response = httpx.Response(400, json={"error": {"message": "Invalid image parameter test-secret-key"}})
    monkeypatch.setattr(httpx, "request", Mock(return_value=response))
    with pytest.raises(VideoFailure) as caught:
        provider.api("POST", "/test")
    assert "Invalid image parameter" in str(caught.value)
    assert provider.key not in str(caught.value)
