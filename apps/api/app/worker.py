import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select, update
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

from .cinema_models import CinemaJob
from .config import settings
from .database import SessionLocal
from .interview_database import SessionLocal as InterviewDB
from .interview_models import InterviewMaterial, Screenplay
from .models import ProcessingJob, StyleJob
from .workflows.activities import mark_media_failed, process_media
from .workflows.cinema import CinemaWorkflow
from .workflows.cinema_activities import fail_cinema, process_cinema
from .workflows.material_activities import analyze_interview_material, fail_interview_material
from .workflows.materials import AnalyzeMaterialWorkflow
from .workflows.media import ProcessMediaWorkflow
from .workflows.screenplay import GenerateScreenplayWorkflow
from .workflows.screenplay_activities import fail_screenplay, generate_screenplay
from .workflows.style import ProcessStyleWorkflow
from .workflows.style_activities import mark_style_failed, process_style


def pending_materials():
    with InterviewDB() as db:
        return [
            (m.id, m.analysis_generation)
            for m in db.scalars(
                select(InterviewMaterial).where(InterviewMaterial.analysis_state == "pending").limit(100)
            )
        ]


def material_dispatched(identifier, generation):
    with InterviewDB() as db:
        db.execute(
            update(InterviewMaterial)
            .where(
                InterviewMaterial.id == identifier,
                InterviewMaterial.analysis_generation == generation,
                InterviewMaterial.analysis_state == "pending",
            )
            .values(analysis_state="dispatched")
        )
        db.commit()


def pending_screenplays():
    with InterviewDB() as db:
        return [
            (s.id, s.generation)
            for s in db.scalars(select(Screenplay).where(Screenplay.state == "pending").limit(100))
        ]


def screenplay_dispatched(identifier, generation):
    with InterviewDB() as db:
        db.execute(
            update(Screenplay)
            .where(
                Screenplay.id == identifier,
                Screenplay.generation == generation,
                Screenplay.state == "pending",
            )
            .values(state="dispatched")
        )
        db.commit()


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


def pending_cinema():
    with InterviewDB() as db:
        return list(db.scalars(select(CinemaJob.id).where(CinemaJob.state == "pending").limit(100)))


def cinema_dispatched(identifier):
    with InterviewDB() as db:
        db.execute(
            update(CinemaJob)
            .where(CinemaJob.id == identifier, CinemaJob.state == "pending")
            .values(state="dispatched")
        )
        db.commit()


async def dispatch(client: Client) -> None:
    while True:
        try:
            for identifier in await asyncio.to_thread(pending_cinema):
                try:
                    await client.start_workflow(
                        CinemaWorkflow.run,
                        identifier,
                        id=f"cinema-{identifier}",
                        task_queue=settings.temporal_task_queue,
                    )
                except WorkflowAlreadyStartedError:
                    pass
                await asyncio.to_thread(cinema_dispatched, identifier)
            for identifier, generation in await asyncio.to_thread(pending_screenplays):
                try:
                    await client.start_workflow(
                        GenerateScreenplayWorkflow.run,
                        [identifier, generation],
                        id=f"screenplay-{identifier}-{generation}",
                        task_queue=settings.temporal_task_queue,
                    )
                except WorkflowAlreadyStartedError:
                    pass
                await asyncio.to_thread(screenplay_dispatched, identifier, generation)
            for identifier, generation in await asyncio.to_thread(pending_materials):
                try:
                    await client.start_workflow(
                        AnalyzeMaterialWorkflow.run,
                        [identifier, generation],
                        id=f"material-{identifier}-{generation}",
                        task_queue=settings.temporal_task_queue,
                    )
                except WorkflowAlreadyStartedError:
                    pass
                await asyncio.to_thread(material_dispatched, identifier, generation)
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
            workflows=[
                ProcessMediaWorkflow,
                ProcessStyleWorkflow,
                AnalyzeMaterialWorkflow,
                GenerateScreenplayWorkflow,
                CinemaWorkflow,
            ],
            activities=[
                process_cinema,
                fail_cinema,
                process_media,
                mark_media_failed,
                process_style,
                mark_style_failed,
                generate_screenplay,
                fail_screenplay,
                analyze_interview_material,
                fail_interview_material,
            ],
            activity_executor=executor,
            max_concurrent_activities=2,
        )
        async with worker:
            await dispatch(client)


if __name__ == "__main__":
    asyncio.run(run())
