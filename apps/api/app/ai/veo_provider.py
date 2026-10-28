"""Veo REST adapter: one paid submission, resumable operation polling."""

import base64
import re
from urllib.parse import urlparse

import httpx

from ..config import settings

BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "veo-3.1-generate-preview"


class VideoFailure(Exception):
    pass


def image_data(path):
    # Match google-genai's _Image_to_mldev wire format for predictLongRunning.
    return {"mimeType": "image/png", "bytesBase64Encoded": base64.b64encode(path.read_bytes()).decode()}


class VeoProvider:
    def __init__(self):
        if not settings.gemini_api_key:
            raise VideoFailure("Set GEMINI_API_KEY on the server and restart the API and worker")
        self.key = settings.gemini_api_key

    def api(self, method, path, **kwargs):
        try:
            response = httpx.request(
                method, BASE + path, headers={"x-goog-api-key": self.key}, timeout=120, **kwargs
            )
        except httpx.HTTPError:
            raise VideoFailure(
                "Veo connection interrupted. Check the saved operation before retrying generation"
            ) from None
        if response.status_code >= 400:
            explanation = {
                400: "Unsupported prompt or image combination; edit the prompt or references",
                401: "Check the Gemini API key",
                403: "Check Veo access and billing",
                402: "Check Gemini billing and credits",
                429: "Veo quota exhausted; retry later",
            }.get(response.status_code, "Veo is unavailable; retry later")
            try:
                error = response.json().get("error", {})
                detail = error.get("message", "") if isinstance(error, dict) else ""
            except (ValueError, AttributeError):
                detail = ""
            if isinstance(detail, str) and detail:
                detail = detail.replace(self.key, "[redacted]")
                detail = re.sub(r"AIza[\w-]+", "[redacted]", detail)
                detail = " ".join(detail.split())[:1200]
                explanation += f". Google detail: {detail}"
            raise VideoFailure(f"Veo HTTP {response.status_code}: {explanation}")
        return response.json()

    def submit(self, prompt, continuity, first_frame, references):
        if first_frame and references:
            raise VideoFailure("Choose either the previous clip's final frame or reference photos, not both")
        instance = {
            "prompt": "Consistent characters and environment:\n"
            + continuity
            + "\n\nCurrent shot action, dialogue and camera direction:\n"
            + prompt
        }
        if first_frame:
            instance["image"] = image_data(first_frame)
        if references:
            instance["referenceImages"] = [
                {"image": image_data(path), "referenceType": "asset"} for path in references
            ]
        result = self.api(
            "POST",
            f"/models/{MODEL}:predictLongRunning",
            json={
                "instances": [instance],
                "parameters": {
                    "durationSeconds": 8,
                    "aspectRatio": "16:9",
                    "resolution": "720p",
                    "sampleCount": 1,
                    "personGeneration": "allow_adult" if first_frame or references else "allow_all",
                },
            },
        )
        name = result.get("name", "")
        if not name.startswith(f"models/{MODEL}/operations/"):
            raise VideoFailure("Veo did not return a valid operation ID; submission may have been accepted")
        return name

    def poll(self, operation):
        if not operation.startswith(f"models/{MODEL}/operations/") or ".." in operation or "?" in operation:
            raise VideoFailure("Invalid stored Veo operation")
        result = self.api("GET", "/" + operation)
        if not result.get("done"):
            return None
        if result.get("error"):
            raise VideoFailure(
                "Veo could not generate this clip. Check billing/access or revise the prompt and photos"
            )
        samples = result.get("response", {}).get("generateVideoResponse", {}).get("generatedSamples", [])
        if not samples or not samples[0].get("video", {}).get("uri"):
            raise VideoFailure(
                "Veo returned no clip. The prompt or photos may have been filtered; revise and retry"
            )
        return samples[0]["video"]["uri"]

    def download(self, uri, path):
        # API keys are sent only to Google's API host, never redirected storage hosts.
        with httpx.Client(timeout=120) as client:
            for _ in range(5):
                parsed = urlparse(uri)
                host = parsed.hostname or ""
                if parsed.scheme != "https" or not (
                    host.endswith(".googleapis.com") or host.endswith(".googleusercontent.com")
                ):
                    raise VideoFailure("Veo returned an unsupported download host")
                headers = {"x-goog-api-key": self.key} if host == "generativelanguage.googleapis.com" else {}
                with client.stream("GET", uri, headers=headers) as response:
                    if response.is_redirect:
                        from urllib.parse import urljoin

                        uri = urljoin(uri, response.headers["location"])
                        continue
                    if response.status_code != 200:
                        raise VideoFailure("Could not download the generated clip; retry recovery")
                    with path.open("wb") as output:
                        for chunk in response.iter_bytes():
                            output.write(chunk)
                    return
        raise VideoFailure("Too many video download redirects")
