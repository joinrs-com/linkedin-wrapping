#!/usr/bin/env python3
"""
Script per migliorare le job descriptions usando OpenAI e copiarle da job_posting_pre a job_postings.
"""

import os
import re
import sys
from pathlib import Path
from typing import List
from urllib.parse import parse_qs, urlparse
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlmodel import SQLModel, create_engine, Session, select

# Aggiungi il path del progetto per gli import
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.wrapping.models import JobPostings, JobPostingPre

# Carica variabili d'ambiente
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)

# Configurazione (caricate all'import, verificate in main())
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Solo priority 1–3 passano da OpenAI; employer esclusi mai (anche con priority 1–3).
OPENAI_PRIORITIES = frozenset({1, 2, 3})
SKIP_OPENAI_EMPLOYER_IDS = frozenset({829928, 1374217})

# Prompt OpenAI
OPENAI_PROMPT = """ Il tuo compito è:

#1) Migliorare il SUMMARY dell'annuncio:

Il summary è composto da una parte fissa e una parte variabile:
<p><strong>Riassunto dell'opportunità da parte della <i>Joinrs AI</i>:</strong>
    [TESTO DEL SUMMARY ORIGINALE PARTE VARIABILE]
</p>

Migliora il summary dell'annuncio come segue:

(Il riassunto dell'opportunità da parte della Joinrs AI: Canonical è alla ricerca di numerosi Junior Software Support Engineer da assumere a tempo pieno con laurea in ingegneria o discipline STEM. I candidati risolveranno problemi complessi, svilupperanno correzioni di bug e collaboreranno con team globali. I benefit includono lavoro da remoto o presso uno degli uffici, bonus annuale, budget per la formazione, ferie e opportunità di viaggio.);

come in questo esempio:
 - fai risaltare la posizione e la laurea richiesta mettendo in grassetto le informazioni più importanti; 
 - breve descrizione del ruolo;
 - benefit e RAL se sono presenti nell'annuncio; 
 - utilizza la "terza persona" nel summary;
 - il summary non deve essere più lungo di quello dell’esempio sopra;


La parte iniziale dell'annuncio è composta da:

- introduzione: <p><strong>Questa posizione è in NOME_AZIENDA</strong><p><br>

- intestazione summary: <p><strong>Riassunto dell'opportunità da parte della <i>Joinrs AI</i>:</strong>...

- summary: ...[TESTO DEL SUMMARY ORIGINALE]</p><br><br>

- conclusione: <br><p><em>Il processo di selezione sarà interamente gestito da NOME_AZIENDA.</em></p>
  
- locations: <br><br><p><em>Questa opportunità è disponibile su LOCATIONS</em></p>


NOTA: la STRUTTURA HTML della parte iniziale dell'annuncio deve essere mantenuta invariata tranne il summary che dovra essere migliorato.

 

#2) Formattare la DESCRIPTION ovvero la seconda parte dell'annuncio:

Per la DESCRIPTION (tutto il testo dopo il summary e prima delle etichette finali):

 - elimina tutti i link o collegamenti esterni dalla description;

 - non modificare il testo originale della description, ma elimina tutti i tag html non supportati e sostituiscili con quelli supportati (successivamente troverai quelli supportati);

 - la lingua della description NON deve essere modificata, mantieni la lingua originale dell'annuncio;

 - dividi il testo in paragrafi coerenti e inserisci gli elenchi puntati nel testo dove necessari per migliorare la leggibilità;

Restituisci la job description in HTML e tra un paragrafo e l'altro della description inserisci SEMPRE e SOLO due "<br><br>" consecutivi fuori dai tag <p> per garantire la corretta visualizzazione su LinkedIn Recruiter.

Le etichette finali utilizzate sono:

 - [#J-REMOTE]
 - [#J-INTERNAL]
 - [#J-MCITY]
 - [#J-ENTERPRISE]
 - [#J-ONE]
 - [#J-MIN]

Sono state inserite manualmente (alla fine della description) attraverso la query che genera i dati per la tabella "job_posting_pre", non modificarle,
assicurati che siano visualizzate correttamente a fine description se presenti.

Utilizza solo questi tag html supportati da LinkedIn Recruiter:
 <b>, <strong> Bold/Strong <u> Underline <i> italic <br> Line Break <p> Paragraph <ul> Unordered List <li> Ordered List <em> Emphasized text(italics)


"""


def create_database_engine():
    """Crea l'engine del database con configurazione appropriata."""
    url = DATABASE_URL
    if not url or not str(url).strip():
        raise ValueError(
            "DATABASE_URL mancante o vuota nel .env. "
            "Esempio: DATABASE_URL=mysql+pymysql://USER:PASSWORD@HOST:3306/NOME_DATABASE"
        )
    try:
        make_url(url)
    except Exception:
        raise ValueError(
            "DATABASE_URL nel .env non è una URL SQLAlchemy valida. "
            "Usa mysql+pymysql://USER:PASSWORD@HOST:PORT/DATABASE su una sola riga; "
            "nella password codifica i caratteri speciali con urllib.parse.quote_plus."
        ) from None

    engine = create_engine(
        url,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
        connect_args={"check_same_thread": False} if "sqlite" in url else {},
    )
    
    # Gestione schema per MySQL
    if engine.dialect.name == "mysql":
        engine = engine.execution_options(schema_translate_map={
            "lw": None,
        })
    
    return engine


def parse_employers_id_from_apply_url(url: str | None) -> int | None:
    """Se utm_medium è '<employers_id>-<priority>', restituisce employers_id; altrimenti None."""
    if not url or not str(url).strip():
        return None
    mediums = parse_qs(urlparse(url.strip()).query).get("utm_medium") or []
    if not mediums:
        return None
    m = re.fullmatch(r"(\d+)-(\d+)", str(mediums[0]).strip())
    if not m:
        return None
    return int(m.group(1))


def should_enrich_with_openai(*, priority: int | None, apply_url: str | None) -> bool:
    """True solo per priority 1–3 e employer non in SKIP_OPENAI_EMPLOYER_IDS (da apply_url)."""
    if priority not in OPENAI_PRIORITIES:
        return False
    emp_id = parse_employers_id_from_apply_url(apply_url)
    if emp_id is not None and emp_id in SKIP_OPENAI_EMPLOYER_IDS:
        return False
    return True


def truncate_job_postings(session: Session):
    """Trunca la tabella job_postings."""
    print("Truncando tabella job_postings...")
    # Usa SQL diretto per truncate che è più efficiente
    if session.bind.dialect.name == "mysql":
        session.exec(text("TRUNCATE TABLE job_postings"))
    elif session.bind.dialect.name == "postgresql":
        session.exec(text("TRUNCATE TABLE lw.job_postings RESTART IDENTITY"))
    else:
        # SQLite
        session.exec(text("DELETE FROM job_postings"))
    session.commit()
    print("Tabella job_postings troncata con successo.")


def fetch_all_job_postings_pre(session: Session) -> List[JobPostingPre]:
    """Legge tutti i record da job_posting_pre."""
    print("Leggendo record da job_posting_pre...")
    statement = select(JobPostingPre)
    results = session.exec(statement)
    job_postings = list(results.all())
    print(f"Trovati {len(job_postings)} job postings in job_posting_pre.")
    return job_postings


def get_new_job_postings_to_process(session: Session) -> List[JobPostingPre]:
    """
    Identifica i nuovi job postings da processare.
    Restituisce solo i record presenti in job_posting_pre ma non in job_postings.
    """
    print("\n" + "=" * 60)
    print("ANALISI RECORD DA PROCESSARE")
    print("=" * 60)
    
    # 1. Leggi tutti i record da job_posting_pre
    all_pre = fetch_all_job_postings_pre(session)
    
    if not all_pre:
        print("Nessun record trovato in job_posting_pre.")
        return []
    
    # 2. Ottieni tutti i partner_job_id già presenti in job_postings
    print("Verificando quali record sono già stati processati...")
    existing_partner_ids = set()
    existing_postings = session.exec(select(JobPostings.partner_job_id)).all()
    for partner_id in existing_postings:
        if partner_id:
            existing_partner_ids.add(partner_id)
    
    print(f"Trovati {len(existing_partner_ids)} partner_job_id già presenti in job_postings.")
    
    # 3. Filtra solo i nuovi record (non ancora presenti)
    new_job_postings = []
    skipped_count = 0
    
    for job_pre in all_pre:
        if job_pre.partner_job_id not in existing_partner_ids:
            # Nuovo record: da processare
            new_job_postings.append(job_pre)
        else:
            # Già presente: skip
            skipped_count += 1
    
    openai_new = sum(
        1
        for j in new_job_postings
        if should_enrich_with_openai(priority=j.priority, apply_url=j.apply_url)
    )
    copy_new = len(new_job_postings) - openai_new

    print(f"\n📊 Riepilogo:")
    print(f"  - Totali record in job_posting_pre: {len(all_pre)}")
    print(f"  - Record già processati (da saltare): {skipped_count}")
    print(f"  - Nuovi record da inserire in job_postings: {len(new_job_postings)}")
    if new_job_postings:
        print(f"      → con miglioramento OpenAI: {openai_new}")
        print(f"      → copia descrizione senza OpenAI: {copy_new}")

    if len(new_job_postings) == 0:
        print("\n✅ Nessun nuovo record da processare. Tutti i record sono già presenti in job_postings.")
    else:
        print(f"\n🚀 Inserimento di {len(new_job_postings)} nuovi record ({openai_new} via OpenAI).")
    
    print("=" * 60 + "\n")
    
    return new_job_postings


def remove_expired_job_postings(session: Session):
    """
    Rimuove i record scaduti da job_postings.
    Un record è considerato scaduto se il suo partner_job_id non è più presente in job_posting_pre.
    """
    print("\n" + "=" * 60)
    print("RIMOZIONE ANNUNCI SCADUTI")
    print("=" * 60)
    
    # 1. Ottieni tutti i partner_job_id da job_posting_pre
    pre_partner_ids = set()
    pre_records = session.exec(select(JobPostingPre)).all()
    
    # SICUREZZA: Verifica che job_posting_pre non sia vuoto
    if not pre_records:
        print("⚠️  ATTENZIONE: job_posting_pre è vuota!")
        print("   Non rimuoverò nessun record per sicurezza.")
        print("   Assicurati di aver caricato i dati correttamente.")
        print("=" * 60 + "\n")
        return 0
    
    for pre in pre_records:
        if pre.partner_job_id:
            pre_partner_ids.add(pre.partner_job_id)
    
    print(f"Trovati {len(pre_records)} record in job_posting_pre.")
    print(f"Trovati {len(pre_partner_ids)} partner_job_id attivi in job_posting_pre.")
    
    # 2. Trova i record in job_postings che non sono più in job_posting_pre
    all_postings = session.exec(select(JobPostings)).all()
    expired_postings = []
    
    for posting in all_postings:
        # Se il partner_job_id non è più in job_posting_pre, il record è scaduto
        if posting.partner_job_id and posting.partner_job_id not in pre_partner_ids:
            expired_postings.append(posting)
    
    if not expired_postings:
        print("\n✅ Nessun annuncio scaduto da rimuovere.")
        print("=" * 60 + "\n")
        return 0
    
    # 3. Mostra informazioni dettagliate sugli annunci scaduti
    print(f"\n⚠️  Trovati {len(expired_postings)} annunci scaduti da rimuovere.")
    print("\n" + "-" * 100)
    print(f"{'ID':<6} | {'partner_job_id':<15} | {'Position':<40} | {'Company':<20}")
    print("-" * 100)
    
    # Mostra tutti i record scaduti in formato tabella
    for posting in expired_postings:
        position_short = (posting.position[:38] + '..') if posting.position and len(posting.position) > 40 else (posting.position or 'N/A')
        company_short = (posting.company[:18] + '..') if posting.company and len(posting.company) > 20 else (posting.company or 'N/A')
        print(f"{str(posting.id):<6} | {str(posting.partner_job_id):<15} | {position_short:<40} | {company_short:<20}")
    
    print("-" * 100)
    
    # Mostra dettagli completi dei primi 5 record
    if len(expired_postings) > 0:
        print(f"\n📋 Dettagli completi dei primi 5 record scaduti:")
        for i, posting in enumerate(expired_postings[:5], 1):
            print(f"\n  {i}. Record ID: {posting.id}")
            print(f"     partner_job_id: {posting.partner_job_id}")
            print(f"     Position: {posting.position or 'N/A'}")
            print(f"     Company: {posting.company or 'N/A'}")
            print(f"     Location: {posting.location or 'N/A'}")
            print(f"     Created at: {posting.created_at or 'N/A'}")
        
        if len(expired_postings) > 5:
            print(f"\n  ... e altri {len(expired_postings) - 5} record scaduti")
    
    # 4. Rimuovi i record scaduti
    print(f"\n🗑️  Rimuovendo {len(expired_postings)} annunci scaduti da job_postings...")
    
    for posting in expired_postings:
        session.delete(posting)
    
    session.commit()
    
    print(f"✅ Rimossi {len(expired_postings)} annunci scaduti con successo.")
    print("=" * 60 + "\n")
    
    return len(expired_postings)


def improve_job_description_with_openai(job_description: str | None) -> str | None:
    """Migliora una job description usando OpenAI."""
    if not job_description:
        return None
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": "Sei un assistente esperto nella formattazione di annunci di lavoro per LinkedIn. Il tuo compito è migliorare la formattazione mantenendo il testo originale."
                },
                {
                    "role": "user",
                    "content": f"{OPENAI_PROMPT}\n\nJob description originale:\n\n{job_description}"
                }
            ]
        )
        
        improved_description = response.choices[0].message.content.strip()
        return improved_description
    except Exception as e:
        print(f"Errore durante il miglioramento con OpenAI: {e}")
        # In caso di errore, restituisci la descrizione originale
        return job_description


def check_if_already_processed(session: Session, partner_job_id: str | None) -> bool:
    """Verifica se un job posting è già stato processato."""
    if not partner_job_id:
        return False
    statement = select(JobPostings).where(JobPostings.partner_job_id == partner_job_id)
    result = session.exec(statement).first()
    return result is not None


def _job_pre_to_posting_mapping(job_pre: JobPostingPre) -> dict:
    """Dizionario per bulk_insert_mappings: job_description -> description."""
    return {
        "position": job_pre.position,
        "description": job_pre.job_description,
        "company": job_pre.company,
        "employers_name": getattr(job_pre, "employers_name", None),
        "employers_id": getattr(job_pre, "employers_id", None),
        "priority": job_pre.priority,
        "apply_url": job_pre.apply_url,
        "company_id": job_pre.company_id,
        "location": job_pre.location,
        "workplace_types": job_pre.workplace_types,
        "experience_level": job_pre.experience_level,
        "jobtype": job_pre.jobtype,
        "partner_job_id": job_pre.partner_job_id,
        "last_build_date": job_pre.last_build_date,
        "created_at": job_pre.created_at,
        "updated_at": job_pre.updated_at,
    }


def bulk_insert_copy_only_jobs(
    engine,
    jobs: List[JobPostingPre],
    *,
    chunk_size: int = 150,
) -> int:
    """
    Inserisce in job_postings le righe senza OpenAI usando bulk_insert_mappings
    (pochi commit rispetto a un insert per riga).
    """
    if not jobs:
        return 0
    total = 0
    n_chunks = (len(jobs) + chunk_size - 1) // chunk_size
    print(
        f"Inserimento bulk (copia senza OpenAI): {len(jobs)} righe in {n_chunks} chunk da max {chunk_size}..."
    )
    for i in range(0, len(jobs), chunk_size):
        chunk = jobs[i : i + chunk_size]
        chunk_num = i // chunk_size + 1
        mappings = [_job_pre_to_posting_mapping(j) for j in chunk]
        try:
            with Session(engine) as session:
                session.bulk_insert_mappings(JobPostings, mappings)
                session.commit()
            total += len(mappings)
            print(f"  Chunk {chunk_num}/{n_chunks}: inserite {len(mappings)} righe (totale {total}).")
        except Exception as e:
            print(f"  ⚠️  Errore bulk chunk {chunk_num}: {e}")
            for j in chunk:
                try:
                    with Session(engine) as s2:
                        s2.add(
                            JobPostings(
                                position=j.position,
                                description=j.job_description,
                                company=j.company,
                                employers_name=getattr(j, "employers_name", None),
                                employers_id=getattr(j, "employers_id", None),
                                priority=j.priority,
                                apply_url=j.apply_url,
                                company_id=j.company_id,
                                location=j.location,
                                workplace_types=j.workplace_types,
                                experience_level=j.experience_level,
                                jobtype=j.jobtype,
                                partner_job_id=j.partner_job_id,
                                last_build_date=j.last_build_date,
                                created_at=j.created_at,
                                updated_at=j.updated_at,
                            )
                        )
                        s2.commit()
                    total += 1
                except Exception as e2:
                    print(f"  ⚠️  Skip partner_job_id={j.partner_job_id}: {e2}")
    print(f"  Inserite {total} righe (copia bulk + eventuale fallback per riga).")
    return total


def process_openai_jobs_incremental(engine, jobs: List[JobPostingPre], batch_size: int = 20) -> int:
    """Solo annunci che richiedono OpenAI: un record alla volta (latenza API)."""
    if not jobs:
        return 0
    print(f"OpenAI: {len(jobs)} annunci da migliorare (log batch {batch_size})...")
    total_inserted = 0
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(jobs) + batch_size - 1) // batch_size
        print(f"\n  Batch OpenAI {batch_num}/{total_batches} ({len(batch)} job)...")
        for job_pre in batch:
            job_data = {
                "id": job_pre.id,
                "partner_job_id": job_pre.partner_job_id,
                "position": job_pre.position,
                "job_description": job_pre.job_description,
                "company": job_pre.company,
                "employers_name": getattr(job_pre, "employers_name", None),
                "employers_id": getattr(job_pre, "employers_id", None),
                "priority": job_pre.priority,
                "apply_url": job_pre.apply_url,
                "company_id": job_pre.company_id,
                "location": job_pre.location,
                "workplace_types": job_pre.workplace_types,
                "experience_level": job_pre.experience_level,
                "jobtype": job_pre.jobtype,
                "last_build_date": job_pre.last_build_date,
                "created_at": job_pre.created_at,
                "updated_at": job_pre.updated_at,
            }
            try:
                with Session(engine) as session:
                    print(
                        f"  🔄 OpenAI Job ID {job_data['id']} "
                        f"(partner_job_id: {job_data['partner_job_id']})..."
                    )
                    improved_description = improve_job_description_with_openai(
                        job_data["job_description"]
                    )
                    job_posting = JobPostings(
                        position=job_data["position"],
                        description=improved_description,
                        company=job_data["company"],
                        employers_name=job_data.get("employers_name"),
                        employers_id=job_data.get("employers_id"),
                        priority=job_data.get("priority"),
                        apply_url=job_data["apply_url"],
                        company_id=job_data["company_id"],
                        location=job_data["location"],
                        workplace_types=job_data["workplace_types"],
                        experience_level=job_data["experience_level"],
                        jobtype=job_data["jobtype"],
                        partner_job_id=job_data["partner_job_id"],
                        last_build_date=job_data["last_build_date"],
                        created_at=job_data["created_at"],
                        updated_at=job_data["updated_at"],
                    )
                    session.add(job_posting)
                    session.commit()
                    total_inserted += 1
            except Exception as e:
                print(f"  ⚠️  Errore OpenAI Job ID {job_data['id']}: {e}")
                try:
                    with Session(engine) as retry_session:
                        improved_description = improve_job_description_with_openai(
                            job_data["job_description"]
                        )
                        retry_session.add(
                            JobPostings(
                                position=job_data["position"],
                                description=improved_description,
                                company=job_data["company"],
                                employers_name=job_data.get("employers_name"),
                                employers_id=job_data.get("employers_id"),
                                priority=job_data.get("priority"),
                                apply_url=job_data["apply_url"],
                                company_id=job_data["company_id"],
                                location=job_data["location"],
                                workplace_types=job_data["workplace_types"],
                                experience_level=job_data["experience_level"],
                                jobtype=job_data["jobtype"],
                                partner_job_id=job_data["partner_job_id"],
                                last_build_date=job_data["last_build_date"],
                                created_at=job_data["created_at"],
                                updated_at=job_data["updated_at"],
                            )
                        )
                        retry_session.commit()
                        total_inserted += 1
                except Exception as retry_e:
                    print(f"  ⚠️  Retry fallito partner_job_id={job_data['partner_job_id']}: {retry_e}")
    return total_inserted


def process_and_insert_incremental(engine, job_postings: List[JobPostingPre], batch_size: int = 20):
    """
    Inserisce i nuovi job: prima bulk (copia senza OpenAI), poi uno per uno con OpenAI.
    Riceve solo record già filtrati da get_new_job_postings_to_process.
    """
    openai_jobs = [
        j
        for j in job_postings
        if should_enrich_with_openai(priority=j.priority, apply_url=j.apply_url)
    ]
    copy_jobs = [
        j
        for j in job_postings
        if not should_enrich_with_openai(priority=j.priority, apply_url=j.apply_url)
    ]

    print(f"\n{'='*60}")
    print(f"Nuovi da inserire: {len(job_postings)} (copia bulk: {len(copy_jobs)}, OpenAI: {len(openai_jobs)})")
    print(f"{'='*60}")

    n_copy = bulk_insert_copy_only_jobs(engine, copy_jobs, chunk_size=150)
    n_openai = process_openai_jobs_incremental(engine, openai_jobs, batch_size=batch_size)
    total_inserted = n_copy + n_openai

    print(f"\n{'='*60}")
    print("Riepilogo processamento:")
    print(f"  - Inseriti (copia bulk): {n_copy}")
    print(f"  - Inseriti (OpenAI): {n_openai}")
    print(f"  - Totale: {total_inserted}")
    print(f"{'='*60}")

    return total_inserted


def insert_job_postings_batch(session: Session, job_postings: List[JobPostings], batch_size: int = 100):
    """Inserisce i job postings in batch nel database."""
    print(f"Inserendo {len(job_postings)} job postings in batch di {batch_size}...")
    
    for i in range(0, len(job_postings), batch_size):
        batch = job_postings[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(job_postings) + batch_size - 1) // batch_size
        
        print(f"Inserendo batch {batch_num}/{total_batches} ({len(batch)} job postings)...")
        
        session.add_all(batch)
        session.commit()
        
        print(f"Batch {batch_num}/{total_batches} inserito con successo.")
    
    print(f"Tutti i {len(job_postings)} job postings sono stati inseriti con successo.")


def verify_all_processed(engine):
    """Verifica che tutti i partner_job_id di job_posting_pre siano presenti in job_postings."""
    print("\n" + "=" * 60)
    print("VERIFICA FINALE - Controllo partner_job_id")
    print("=" * 60)
    
    with Session(engine) as session:
        # Ottieni tutti i partner_job_id da job_posting_pre (escludendo null)
        pre_partner_ids = set()
        pre_records = session.exec(select(JobPostingPre)).all()
        for pre in pre_records:
            if pre.partner_job_id:
                pre_partner_ids.add(pre.partner_job_id)
        
        # Ottieni tutti i partner_job_id da job_postings (escludendo null)
        postings_partner_ids = set()
        postings_records = session.exec(select(JobPostings)).all()
        for posting in postings_records:
            if posting.partner_job_id:
                postings_partner_ids.add(posting.partner_job_id)
        
        # Trova i partner_job_id mancanti
        missing_partner_ids = pre_partner_ids - postings_partner_ids
        
        # Statistiche
        print(f"\n📊 Statistiche:")
        print(f"  - Totali record in job_posting_pre: {len(pre_records)}")
        print(f"  - Totali record in job_postings: {len(postings_records)}")
        print(f"  - Partner_job_id unici in job_posting_pre: {len(pre_partner_ids)}")
        print(f"  - Partner_job_id unici in job_postings: {len(postings_partner_ids)}")
        print(f"  - Partner_job_id mancanti: {len(missing_partner_ids)}")
        
        if missing_partner_ids:
            print(f"\n⚠️  ATTENZIONE: {len(missing_partner_ids)} record non sono stati processati!")
            print(f"   Partner_job_id mancanti (primi 10):")
            for i, partner_id in enumerate(list(missing_partner_ids)[:10], 1):
                print(f"     {i}. {partner_id}")
            if len(missing_partner_ids) > 10:
                print(f"     ... e altri {len(missing_partner_ids) - 10}")
            return False
        else:
            print(f"\n✅ VERIFICA COMPLETATA: Tutti i partner_job_id sono presenti in job_postings!")
            return True


def main():
    """Funzione principale."""
    print("=" * 60)
    print("Script di miglioramento job descriptions")
    print("=" * 60)
    
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL non trovata nel file .env")

    try:
        # Crea engine e sessione
        engine = create_database_engine()
        
        with Session(engine) as session:
            # 1. Rimuovi gli annunci scaduti (presenti in job_postings ma non in job_posting_pre)
            expired_count = remove_expired_job_postings(session)
            
            # 2. Identifica i nuovi record da processare
            # (solo quelli presenti in job_posting_pre ma non in job_postings)
            new_job_postings = get_new_job_postings_to_process(session)
            new_records_count = len(new_job_postings)
            
            if not new_job_postings:
                print("Nessun nuovo record da processare.")
                # Esegui comunque la verifica finale
                all_processed = verify_all_processed(engine)
                if all_processed:
                    print("\n✅ Tutti i record sono già stati processati correttamente.")
                
                # Mostra riepilogo finale
                print("\n" + "=" * 60)
                print("RIEPILOGO FINALE")
                print("=" * 60)
                print(f"  📊 Record scaduti eliminati: {expired_count}")
                print(f"  📊 Nuovi record trovati: {new_records_count}")
                print(f"  📊 Nuovi record processati: 0")
                print("=" * 60)
                return

            needs_openai = any(
                should_enrich_with_openai(priority=j.priority, apply_url=j.apply_url)
                for j in new_job_postings
            )
            if needs_openai and not (OPENAI_API_KEY and str(OPENAI_API_KEY).strip()):
                raise ValueError(
                    "OPENAI_API_KEY non trovata nel file .env "
                    "(necessaria: almeno un nuovo annuncio richiede il miglioramento via OpenAI)."
                )

            # 3. Processa e inserisci solo i nuovi record
            # Passa engine invece di session per creare nuove sessioni per ogni batch
            processed_count = process_and_insert_incremental(engine, new_job_postings, batch_size=20)
        
        # 4. Verifica finale che tutti i partner_job_id siano stati processati
        all_processed = verify_all_processed(engine)
        
        # 5. Mostra riepilogo finale
        print("\n" + "=" * 60)
        print("RIEPILOGO FINALE")
        print("=" * 60)
        print(f"  📊 Record scaduti eliminati: {expired_count}")
        print(f"  📊 Nuovi record trovati: {new_records_count}")
        print(f"  📊 Nuovi record processati: {processed_count}")
        print("=" * 60)
        
        if all_processed:
            print("\n✅ Script completato con successo! Tutti i record sono stati processati.")
        else:
            print("\n⚠️  Script completato, ma alcuni record non sono stati processati.")
            print("   Riavvia lo script per processare i record mancanti.")
        print("=" * 60)
        
    except Exception as e:
        print(f"Errore durante l'esecuzione dello script: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

