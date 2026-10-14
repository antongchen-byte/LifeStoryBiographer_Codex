import tempfile
from pathlib import Path

from sqlalchemy import select
from temporalio import activity

from ..ai.style_provider import GeminiStyleProvider, ProviderFailure
from ..domain.processing import checksum
from ..interview_database import SessionLocal
from ..interview_models import InterviewMaterial, InterviewSession, InterviewTurn
from ..material_analysis import ANALYZE_PROMPT, MaterialInterpretation, sections
from ..storage import get_storage


def analyze_material(
    identifier,
    generation,
    session_factory=SessionLocal,
    storage=None,
    provider_factory=GeminiStyleProvider,
    heartbeat=lambda: None,
):
    storage = storage or get_storage()
    with session_factory() as db:
        m = db.get(InterviewMaterial, identifier, with_for_update=True)
        if (
            not m
            or m.analysis_generation != generation
            or m.analysis_state not in {"pending", "dispatched", "running"}
        ):
            return
        s = db.get(InterviewSession, m.session_id)
        if not s or s.status == "approved":
            return
        model = s.model
        language = list(
            db.scalars(
                select(InterviewTurn.text)
                .where(InterviewTurn.session_id == s.id, InterviewTurn.role == "user")
                .order_by(InterviewTurn.sequence.desc())
                .limit(3)
            )
        )
        key, filename, mime, expected = m.storage_key, m.filename, m.mime_type, m.sha256
        results = list(m.analysis.get("sections", []))
        m.analysis_state, m.analysis_error = "running", None
        db.commit()
    try:
        provider = provider_factory(model)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / ("source" + Path(filename).suffix.lower())
            storage.download(key, source)
            if checksum(source) != expected:
                raise ValueError("The archived material failed its integrity check")
            for index, (coverage, parts) in enumerate(sections(source, mime, folder)):
                heartbeat()
                with session_factory() as db:
                    m = db.get(InterviewMaterial, identifier, with_for_update=True)
                    if not m or m.analysis_generation != generation or m.analysis_state != "running":
                        return
                if index < len(results):
                    continue
                result = provider.generate(
                    ANALYZE_PROMPT,
                    {
                        "filename": filename,
                        "coverage": coverage,
                        "language_context": language,
                    },
                    MaterialInterpretation,
                    media=parts,
                )
                results.append({"coverage": coverage, **result.model_dump()})
                with session_factory() as db:
                    m = db.get(InterviewMaterial, identifier, with_for_update=True)
                    if not m or m.analysis_generation != generation or m.analysis_state != "running":
                        return
                    m.analysis = {"sections": results, "model": model}
                    m.analysis_progress = len(results)
                    db.commit()
            if not results:
                raise ValueError("No readable material was found")
            # Hierarchical synthesis keeps provider requests bounded; preserve every section in provenance.
            summaries = results
            while len(summaries) > 1:
                merged = []
                for start in range(0, len(summaries), 8):
                    heartbeat()
                    merged.append(
                        provider.generate(
                            ANALYZE_PROMPT
                            + " Synthesize these section analyses without erasing uncertainty.",
                            {"sections": summaries[start : start + 8], "language_context": language},
                            MaterialInterpretation,
                        ).model_dump()
                    )
                summaries = merged
            final = summaries[0]
        with session_factory() as db:
            m = db.get(InterviewMaterial, identifier, with_for_update=True)
            if m and m.analysis_generation == generation and m.analysis_state == "running":
                m.analysis = {**final, "sections": results, "model": model}
                m.analysis_state = "ready"
                db.commit()
    except Exception as error:
        with session_factory() as db:
            m = db.get(InterviewMaterial, identifier, with_for_update=True)
            if m and m.analysis_generation == generation and m.analysis_state == "running":
                m.analysis_state = "failed"
                m.analysis_error = (
                    str(error)
                    if isinstance(error, (ProviderFailure, ValueError))
                    else "Material analysis failed. Retry or describe the material yourself."
                )
                db.commit()


@activity.defn
def analyze_interview_material(args: list):
    analyze_material(*args, heartbeat=lambda: activity.heartbeat())


@activity.defn
def fail_interview_material(args: list):
    identifier, generation = args
    with SessionLocal() as db:
        m = db.get(InterviewMaterial, identifier, with_for_update=True)
        if (
            m
            and m.analysis_generation == generation
            and m.analysis_state in {"pending", "dispatched", "running"}
        ):
            m.analysis_state = "failed"
            m.analysis_error = "Analysis was interrupted. Retry to continue from completed sections."
            db.commit()
