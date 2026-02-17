"""
CLI entrypoint for job enrichment pipeline.
Run: python -m enrichment --batch-size 200 --mode incremental
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import delete

from enrichment.classify_collar import classify_collar, CollarResult
from enrichment.classify_gpt import classify_gpt, GptResult, score_gpt_questions
from enrichment.classify_sector import classify_sector, SectorResult, score_micro_sectors
from enrichment.classify_seniority import classify_seniority, SeniorityResult
from enrichment.config import config
from enrichment.db import fetch_job_batch, session_scope
from enrichment.extract_education import (
    EducationResult,
    EducationTypeRef,
    ensure_education_type,
    extract_education,
)
from enrichment.language import detect_language
from enrichment.llm import init_llm_budget
from enrichment.models import BlueCollarCopy, JobEducationType, JobEnrichment
from enrichment.normalize import compute_normalized
from enrichment.taxonomy_cache import TaxonomyCache, load_taxonomy_cache

# Structured logger (plan rule 8)
logger = logging.getLogger("enrichment")


@dataclass
class JobInput:
    """Plain copy of job fields needed for processing. Avoids DetachedInstanceError after session.rollback()."""

    id: int
    position: Optional[str]
    description: Optional[str]


def _setup_logging() -> None:
    if not logger.handlers:
        try:
            from utils.logger import JsonFormatter
        except ImportError:
            import json as _json

            class JsonFormatter(logging.Formatter):
                def format(self, record: logging.LogRecord) -> str:
                    d = {"level": record.levelname, "logger": record.name, "message": record.getMessage()}
                    if getattr(record, "extra", None) and isinstance(record.extra, dict):
                        d.update(record.extra)
                    return _json.dumps(d, ensure_ascii=False)
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    logger.propagate = False


def process_one_job(
    job: JobInput,
    cache: TaxonomyCache,
    processing_version: str,
) -> tuple[Optional[JobEnrichment], list[EducationTypeRef], Optional[dict]]:
    """
    Run steps 1–8 for one job. Returns (enrichment_row, education_type_refs, explanation_dict).
    Never writes to blue_collar_copy.
    """
    try:
        position = job.position or ""
        description = job.description or ""
        normalized_title, normalized_text = compute_normalized(position, description)
        detected_lang = detect_language(normalized_text)

        # Collar from title only to avoid false positives from description
        collar: CollarResult = classify_collar(normalized_title, normalized_text, title_only=True)
        # Override: if title says white but sector taxonomy fits better -> blue; if blue but gpt fits better -> white
        scored_sectors = score_micro_sectors(cache, normalized_title, normalized_text)
        scored_gpt = score_gpt_questions(cache, normalized_title, normalized_text)
        best_sector_score = scored_sectors[0][1] if scored_sectors else 0.0
        best_gpt_score = scored_gpt[0][1] if scored_gpt else 0.0
        if collar.collar_type == "white" and best_sector_score > best_gpt_score:
            effective_collar = "blue"
        elif collar.collar_type == "blue" and best_gpt_score > best_sector_score:
            effective_collar = "white"
        else:
            effective_collar = collar.collar_type or "blue"
        collar_type = effective_collar
        # Blue -> sector from macro_sector_copy/micro_sector_copy; White -> gpt from gpt_questions_groups/gpt_questions
        if effective_collar == "blue":
            sector = classify_sector(cache, normalized_title, normalized_text)
            gpt_result = GptResult(None, None, 0.0, "skip", {"reason": "blue_collar"})
        else:
            sector = SectorResult(None, None, 0.0, "skip", {"reason": "white_collar_uses_gpt"})
            if cache.gpt_questions or cache.gpt_groups:
                gpt_result = classify_gpt(cache, normalized_title, normalized_text, force_llm=True)
            else:
                gpt_result = GptResult(None, None, 0.0, "skip", {"reason": "no_gpt_taxonomy"})
        seniority: SeniorityResult = classify_seniority(normalized_text, cache, collar_type)
        education: EducationResult = extract_education(normalized_text, cache, collar_type)

        explanation = {
            "collar": collar.explanation,
            "collar_effective": effective_collar,
            "sector": sector.explanation,
            "gpt": gpt_result.explanation,
            "seniority": seniority.explanation,
            "education": education.explanation,
        }
        now = datetime.utcnow()
        enrichment_row = JobEnrichment(
            job_id=job.id,
            normalized_title=normalized_title,
            normalized_text=normalized_text,
            detected_language=detected_lang,
            processing_version=processing_version,
            collar_type=collar_type,
            collar_confidence=collar.confidence,
            sector_macro_id=sector.sector_macro_id,
            sector_micro_id=sector.sector_micro_id,
            sector_confidence=sector.sector_confidence,
            sector_method=sector.sector_method,
            gpt_group_id=gpt_result.gpt_group_id,
            gpt_question_id=gpt_result.gpt_question_id,
            gpt_confidence=gpt_result.gpt_confidence,
            gpt_method=gpt_result.gpt_method,
            seniority_id=seniority.seniority_id,
            seniority_confidence=seniority.seniority_confidence,
            seniority_method=seniority.seniority_method,
            education_level_id=education.education_level_id,
            education_confidence=education.education_confidence,
            education_method=education.education_method,
            explanation_json=explanation,
            model_version=config.OPENAI_MODEL,
            created_at=now,
            updated_at=now,
        )
        return enrichment_row, education.education_types, explanation
    except Exception as e:
        logger.warning(
            "job_failed",
            extra={"extra": {"job_id": job.id, "error": str(e)}},
        )
        return None, [], None


def write_batch(
    session,
    cache: TaxonomyCache,
    enrichments: list[JobEnrichment],
    education_by_job: dict[int, list[tuple[int, float, Optional[str]]]],
) -> None:
    """Upsert job_enrichment (merge); delete existing job_education_types per job and bulk insert."""
    for enr in enrichments:
        session.merge(enr)
    session.flush()
    for jid, type_triples in education_by_job.items():
        session.execute(delete(JobEducationType).where(JobEducationType.job_id == jid))
        for type_id, conf, evidence in type_triples:
            session.add(
                JobEducationType(
                    job_id=jid,
                    education_type_id=type_id,
                    confidence=conf,
                    evidence=evidence,
                    created_at=datetime.utcnow(),
                )
            )


def run_batch(
    session,
    cache: TaxonomyCache,
    jobs: list[JobInput],
    processing_version: str,
) -> tuple[int, int, int]:
    """Process jobs and write to DB. Returns (ok_count, err_count, llm_used)."""
    from enrichment import llm as llm_mod

    enrichments: list[JobEnrichment] = []
    education_by_job: dict[int, list[tuple[int, float, Optional[str]]]] = {}
    err_count = 0
    budget_before = getattr(llm_mod, "_llm_calls_remaining", None)

    for job in jobs:
        enr, type_refs, _ = process_one_job(job, cache, processing_version)
        if enr is None:
            err_count += 1
            continue
        enrichments.append(enr)
        type_triples: list[tuple[int, float, Optional[str]]] = []
        for ref in type_refs:
            tid = ensure_education_type(session, cache, ref.normalized_name)
            type_triples.append((tid, ref.confidence, ref.evidence))
        if type_triples:
            education_by_job[enr.job_id] = type_triples

    budget_after = getattr(llm_mod, "_llm_calls_remaining", None)
    llm_used = (budget_before - budget_after) if isinstance(budget_before, int) and isinstance(budget_after, int) else 0
    llm_used = max(0, llm_used)
    write_batch(session, cache, enrichments, education_by_job)
    return len(enrichments), err_count, llm_used


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(description="Job enrichment pipeline")
    parser.add_argument("--batch-size", type=int, default=200, help="Batch size (keyset)")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental", "only_new"],
        default="incremental",
        help="full=all jobs; incremental=no row/updated/needs_repair; only_new=only blue_collar_copy without job_enrichment (new inserts)",
    )
    parser.add_argument(
        "--processing-version",
        type=str,
        default=config.DEFAULT_PROCESSING_VERSION,
        help="Value for job_enrichment.processing_version",
    )
    args = parser.parse_args()
    config.validate()

    cache = load_taxonomy_cache()
    init_llm_budget(config.MAX_LLM_CALLS_PER_RUN)

    total_ok = 0
    total_err = 0
    total_llm = 0
    batch_retries = 0
    last_id = 0
    batch_num = 0
    start_run = time.perf_counter()

    while True:
        batch_num += 1
        batch_start = time.perf_counter()
        ok, err, llm_used = 0, 0, 0
        with session_scope() as session:
            orm_jobs = fetch_job_batch(
                session,
                last_id=last_id,
                batch_size=args.batch_size,
                mode=args.mode,
            )
            if not orm_jobs:
                break
            next_last_id = orm_jobs[-1].id
            # Copy to plain dataclass so retries after session.rollback() don't hit DetachedInstanceError
            jobs = [
                JobInput(id=j.id, position=j.position, description=j.description)
                for j in orm_jobs
            ]

            for attempt in range(3):
                try:
                    ok, err, llm_used = run_batch(
                        session, cache, jobs, args.processing_version
                    )
                    break
                except Exception as e:
                    batch_retries += 1
                    session.rollback()
                    wait = 2 ** attempt
                    logger.warning(
                        "batch_retry",
                        extra={
                            "extra": {
                                "batch": batch_num,
                                "attempt": attempt + 1,
                                "error": str(e),
                                "wait_sec": wait,
                            }
                        },
                    )
                    time.sleep(wait)
            else:
                logger.error(
                    "batch_failed_skipping",
                    extra={"extra": {"batch": batch_num, "last_id": last_id}},
                )
                last_id = next_last_id
                continue

        total_ok += ok
        total_err += err
        total_llm += llm_used
        last_id = next_last_id
        batch_elapsed = time.perf_counter() - batch_start
        throughput = ok / batch_elapsed if batch_elapsed > 0 else 0
        logger.info(
            "batch_done",
            extra={
                "extra": {
                    "batch": batch_num,
                    "jobs_processed": ok,
                    "errors": err,
                    "llm_fallback_count": llm_used,
                    "batch_time_sec": round(batch_elapsed, 2),
                    "throughput_jobs_per_sec": round(throughput, 2),
                    "last_id": last_id,
                }
            },
        )

    run_elapsed = time.perf_counter() - start_run
    logger.info(
        "run_done",
        extra={
            "extra": {
                "total_jobs_processed": total_ok,
                "total_errors": total_err,
                "error_rate": round(total_err / max(1, total_ok + total_err), 4),
                "total_llm_fallback": total_llm,
                "batch_retry_count": batch_retries,
                "run_time_sec": round(run_elapsed, 2),
                "throughput_jobs_per_sec": round(total_ok / run_elapsed, 2) if run_elapsed > 0 else 0,
            }
        },
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
