"""Provider contracts only. No synthetic AI output is returned by the foundation."""

from dataclasses import dataclass
from typing import AsyncIterator, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class InvocationContext:
    project_id: str
    trace_id: str
    prompt_version: str


@dataclass(frozen=True)
class StoredMedia:
    storage_key: str
    mime_type: str


class StructuredTextProvider(Protocol):
    async def generate(self, prompt: str, schema: type[T], context: InvocationContext) -> T: ...


class MediaUnderstandingProvider(Protocol):
    async def analyze(
        self, media: StoredMedia, prompt: str, schema: type[T], context: InvocationContext
    ) -> T: ...


class LiveInterviewProvider(Protocol):
    async def ephemeral_token(self, context: InvocationContext) -> str: ...
    def stream(self, audio: AsyncIterator[bytes], context: InvocationContext) -> AsyncIterator[bytes]: ...


class VideoGenerationProvider(Protocol):
    async def start(self, prompt: str, references: list[StoredMedia], context: InvocationContext) -> str: ...
    async def retrieve(self, operation_id: str, context: InvocationContext) -> StoredMedia | None: ...
