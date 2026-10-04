import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, update
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

from .config import settings
from .database import SessionLocal
from .models import ProcessingJob, StyleJob
from .workflows.activities import mark_media_failed, process_media
from .workflows.media import ProcessMediaWorkflow
from .workflows.style import ProcessStyleWorkflow
from .workflows.style_activities import mark_style_failed, process_style

logger = logging.getLogger("biographer.worker")


def pending_jobs() -> list[str]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(ProcessingJob.id)
                .where(ProcessingJob.state == "pending")
                .order_by(ProcessingJob.created_at)
                .limit(100)
            )
        )


def mark_dispatched(identifier: str) -> None:
    with SessionLocal() as db:
        db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == identifier, ProcessingJob.state == "pending")
            .values(state="dispatched")
        )
        db.commit()


def pending_style_jobs():
    with SessionLocal() as db:
        return [
            (j.id, j.generation)
            for j in db.scalars(select(StyleJob).where(StyleJob.state == "pending").limit(100))
        ]


def style_dispatched(identifier, generation):
    with SessionLocal() as db:
        db.execute(
            update(StyleJob)
            .where(StyleJob.id == identifier, StyleJob.state == "pending", StyleJob.generation == generation)
            .values(state="dispatched")
        )
        db.commit()


async def dispatch(client: Client) -> None:
    while True:
        try:
            for identifier in await asyncio.to_thread(pending_jobs):
                try:
                    await client.start_workflow(
                        ProcessMediaWorkflow.run,
                        identifier,
                        id=f"process-media-{identifier}",
                        task_queue=settings.temporal_task_queue,
                    )
                except WorkflowAlreadyStartedError:
                    pass
                await asyncio.to_thread(mark_dispatched, identifier)
            for identifier, generation in await asyncio.to_thread(pending_style_jobs):
                try:
                    await client.start_workflow(
                        ProcessStyleWorkflow.run,
                        identifier,
                        id=f"style-{identifier}-{generation}",
                        task_queue=settings.temporal_task_queue,
                    )
                except WorkflowAlreadyStartedError:
                    pass
                await asyncio.to_thread(style_dispatched, identifier, generation)
        except Exception as error:
            logger.warning("Dispatch deferred: %s", type(error).__name__)
        await asyncio.sleep(2)


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
            break
        except Exception as error:
            logger.warning("Waiting for Temporal: %s", type(error).__name__)
            await asyncio.sleep(3)
    with ThreadPoolExecutor(max_workers=4) as executor:
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[ProcessMediaWorkflow, ProcessStyleWorkflow],
            activities=[process_media, mark_media_failed, process_style, mark_style_failed],
            activity_executor=executor,
            max_concurrent_activities=2,
        )
        async with worker:
            await dispatch(client)


if __name__ == "__main__":
    asyncio.run(run())
