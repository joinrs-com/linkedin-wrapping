#!/usr/bin/env python3
"""
Script dimostrativo / manuale: legge alcuni record da job_posting_pre,
chiama OpenAI su job_description e stampa il confronto in console.

Non fa parte della suite pytest (vedi pytest.ini, testpaths = tests).
"""

import sys
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from sqlmodel import Session, select

project_root = Path(__file__).resolve().parent.parent
scripts_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(scripts_dir))

env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

from api.wrapping.models import JobPostingPre

import improve_job_descriptions


def fetch_limited_job_postings_pre(session: Session, limit: int = 10) -> List[JobPostingPre]:
    print(f"Leggendo {limit} record da job_posting_pre...")
    statement = select(JobPostingPre).limit(limit)
    results = session.exec(statement)
    job_postings = list(results.all())
    print(f"Trovati {len(job_postings)} job postings da processare.\n")
    return job_postings


def truncate_text(text: str | None, max_length: int = 500) -> str:
    if not text:
        return "(vuoto)"
    if len(text) <= max_length:
        return text
    return text[:max_length] + "... [troncato]"


def display_comparison(job_pre: JobPostingPre, improved_description: str | None, show_full: bool = False):
    print("=" * 80)
    print(f"ID: {job_pre.id}")
    print(f"Position: {job_pre.position}")
    print(f"Company: {job_pre.company or 'N/A'}")
    print(f"Location: {job_pre.location or 'N/A'}")
    print("-" * 80)
    print("\n📄 JOB DESCRIPTION ORIGINALE:")
    print("-" * 80)
    if show_full:
        original = job_pre.job_description or "(vuoto)"
    else:
        original = truncate_text(job_pre.job_description, max_length=800)
    print(original)
    print("\n✨ JOB DESCRIPTION MIGLIORATA:")
    print("-" * 80)
    if show_full:
        improved = improved_description or "(vuoto)"
    else:
        improved = truncate_text(improved_description, max_length=800)
    print(improved)
    print("\n" + "=" * 80)
    print()


def main():
    print("=" * 80)
    print("DEMO - Miglioramento Job Descriptions (OpenAI, solo output console)")
    print("=" * 80)
    print()
    try:
        if not improve_job_descriptions.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY non trovata nel file .env")
        if not improve_job_descriptions.DATABASE_URL:
            raise ValueError("DATABASE_URL non trovata nel file .env")
        engine = improve_job_descriptions.create_database_engine()
        with Session(engine) as session:
            job_postings_pre = fetch_limited_job_postings_pre(session, limit=10)
            if not job_postings_pre:
                print("Nessun job posting trovato in job_posting_pre. Script terminato.")
                return
            print("Processando job postings con OpenAI...\n")
            for i, job_pre in enumerate(job_postings_pre, 1):
                print(f"[{i}/{len(job_postings_pre)}] Processando job posting ID {job_pre.id}...")
                improved_description = improve_job_descriptions.improve_job_description_with_openai(
                    job_pre.job_description
                )
                display_comparison(job_pre, improved_description, show_full=(i == 1))
        print("=" * 80)
        print("Demo completata con successo!")
        print("=" * 80)
    except Exception as e:
        print(f"Errore durante l'esecuzione dello script: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
