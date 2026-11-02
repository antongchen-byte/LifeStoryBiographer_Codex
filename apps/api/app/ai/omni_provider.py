"""Gemini Omni video generation through resumable Interactions requests."""
import base64
import binascii
import re

from .veo_provider import VeoProvider, VideoFailure

MODEL = "gemini-omni-1.1-flash"


class OmniProvider(VeoProvider):
    def api(self, method, path, **kwargs):
        try:
            return super().api(method, path, **kwargs)
        except VideoFailure as error:
            raise VideoFailure(str(error).replace("Veo", "Gemini Omni")) from None

    def submit(self, prompt, continuity, first_frame, references, seconds=8):
        if seconds not in {4, 6, 8}:
            raise VideoFailure("Choose a 4-, 6- or 8-second planned clip")
        if first_frame and references:
            raise VideoFailure("Choose the previous final frame or reference photos, not both")
        images = [first_frame] if first_frame else references
        parts = [{"type": "image", "mime_type": "image/png",
                  "data": base64.b64encode(path.read_bytes()).decode()} for path in images]
        mode = "image_to_video" if first_frame else "reference_to_video" if references else "text_to_video"
        instruction = "Use the supplied image as the starting frame. " if first_frame else ""
        parts.append({"type": "text", "text":
            f"Generate a {seconds}-second video with audio. " + instruction
            + "Consistent characters and environment:\n" + continuity
            + "\nCurrent shot action, dialogue and camera direction:\n" + prompt})
        result = self.api("POST", "/interactions", json={
            "model": MODEL, "input": parts, "background": True, "store": True,
            "response_format": {"type": "video", "aspect_ratio": "16:9", "resolution": "720p"},
            "generation_config": {"video_config": {"task": mode}},
        })
        identifier = result.get("id", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
            raise VideoFailure("Gemini Omni did not return a valid interaction ID; check usage before retrying")
        return "interactions/" + identifier

    def poll(self, operation):
        if operation.startswith("models/veo-3.1-generate-preview/operations/"):
            return super().poll(operation)
        if not re.fullmatch(r"interactions/[A-Za-z0-9_-]+", operation):
            raise VideoFailure("Invalid stored interaction ID")
        result = self.api("GET", "/" + operation)
        status = result.get("status")
        if status in {"in_progress", "queued"}:
            return None
        if status != "completed":
            raise VideoFailure("Gemini Omni generation failed or was blocked; review the prompt and references before retrying")
        for step in result.get("steps", []):
            if step.get("type") != "model_output":
                continue
            for content in step.get("content", []):
                if content.get("type") == "video" and content.get("mime_type", "video/mp4") == "video/mp4":
                    if content.get("data"):
                        return "data:video/mp4;base64," + content["data"]
                    if content.get("uri"):
                        return content["uri"]
        raise VideoFailure("Gemini Omni returned no video; review the prompt or references")

    def download(self, uri, path):
        if uri.startswith("data:video/mp4;base64,"):
            try:
                data = base64.b64decode(uri.split(",", 1)[1], validate=True)
            except (ValueError, binascii.Error):
                raise VideoFailure("Gemini Omni returned invalid video data") from None
            if not data:
                raise VideoFailure("Gemini Omni returned an empty video")
            path.write_bytes(data)
            return
        return super().download(uri, path)
