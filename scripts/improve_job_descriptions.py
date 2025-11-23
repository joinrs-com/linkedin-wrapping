#!/usr/bin/env python3
"""
Script per migliorare le job descriptions usando OpenAI e copiarle da job_posting_pre a job_postings.
"""

import os
import sys
from pathlib import Path
from typing import List
from dotenv import load_dotenv
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session, select

# Aggiungi il path del progetto per gli import
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.wrapping.models import JobPostings, JobPostingPre

# Carica variabili d'ambiente
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

# Configurazione (caricate all'import, verificate in main())
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# Prompt OpenAI
OPENAI_PROMPT = """Il tuo compito è:

modificare il summary dell'annuncio ovvero la prima parte della job description in questo modo:

(Il riassunto dell'opportunità da parte della Joinrs AI: Canonical è alla ricerca di numerosi Junior Software Support Engineer da assumere a tempo pieno con laurea in ingegneria o discipline STEM. I candidati risolveranno problemi complessi, svilupperanno correzioni di bug e collaboreranno con team globali. I benefit includono lavoro da remoto o presso uno degli uffici, bonus annuale, budget per la formazione, ferie e opportunità di viaggio.)

- fai risaltare la posizione e la laurea richiesta;

- breve descrizione del ruolo;

- benefit e RAL se sono presenti nell'annuncio;

- utilizza sempre la terza persona nel summary

- mantieni la lingua originale dell'annuncio

lascia intatto tutto il resto ovvero:

- introduzione: <p><strong>Questa posizione è in ', e.name, '</strong><br><br></p>', 

- conclusione: '<br><br><em>Il processo di selezione sarà interamente gestito da ',

- locations: <br><br><em>Questa opportunità è disponibile su ',

Per description invece:

- togli tutti i link o collegamenti esterni

- non modificare il testo originale dell'annuncio

- mantieni la lingua originale dell'annuncio

- dividi il testo in paragrafi senzati e inserisci gli elenchi puntati nel testo dove necessari per migliorare la leggibilità

restituisci la job description in HTML e utilizza questi tag html che sono i soli supportati: 

<b>, <strong> Bold/Strong

<u> Underline

<i> italic

<br> Line Break

<p> Paragraph

<ul> Unordered List

<li> Ordered List 

<em> Emphasized text(italics)"""


def create_database_engine():
    """Crea l'engine del database con configurazione appropriata."""
    engine = create_engine(
        DATABASE_URL,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False,
        connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
    )
    
    # Gestione schema per MySQL
    if engine.dialect.name == "mysql":
        engine = engine.execution_options(schema_translate_map={
            "lw": None,
        })
    
    return engine


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
    print(f"Trovati {len(job_postings)} job postings da processare.")
    return job_postings


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


def process_and_insert_incremental(engine, job_postings: List[JobPostingPre], batch_size: int = 20):
    """Processa e inserisce i job postings in modo incrementale, saltando quelli già processati."""
    print(f"Processando {len(job_postings)} job postings in batch di {batch_size}...")
    
    total_processed = 0
    total_skipped = 0
    total_inserted = 0
    
    for i in range(0, len(job_postings), batch_size):
        batch = job_postings[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(job_postings) + batch_size - 1) // batch_size
        
        print(f"\nProcessando batch {batch_num}/{total_batches} ({len(batch)} job postings)...")
        
        improved_job_postings = []
        
        # Estrai tutti i dati necessari prima di processare (per evitare problemi con oggetti expired)
        batch_data = []
        for job_pre in batch:
            try:
                # Estrai tutti i dati necessari subito
                batch_data.append({
                    'id': job_pre.id,
                    'partner_job_id': job_pre.partner_job_id,
                    'position': job_pre.position,
                    'job_description': job_pre.job_description,
                    'company': job_pre.company,
                    'apply_url': job_pre.apply_url,
                    'company_id': job_pre.company_id,
                    'location': job_pre.location,
                    'workplace_types': job_pre.workplace_types,
                    'experience_level': job_pre.experience_level,
                    'jobtype': job_pre.jobtype,
                    'last_build_date': job_pre.last_build_date,
                    'created_at': job_pre.created_at,
                    'updated_at': job_pre.updated_at,
                })
            except Exception as e:
                print(f"  ⚠️  Errore nell'estrazione dati per Job ID {job_pre.id}: {e}")
                continue
        
        # Processa ogni job con una nuova sessione per ogni record (per evitare che errori blocchino il batch)
        for job_data in batch_data:
            try:
                # Crea una nuova sessione per ogni record per evitare problemi di connessione
                with Session(engine) as session:
                    # Verifica se già processato
                    try:
                        if check_if_already_processed(session, job_data['partner_job_id']):
                            print(f"  ⏭️  Job ID {job_data['id']} (partner_job_id: {job_data['partner_job_id']}) già processato, skip...")
                            total_skipped += 1
                            continue
                    except Exception as e:
                        print(f"  ⚠️  Errore verificando Job ID {job_data['id']}: {e}")
                        # Se c'è un errore, prova a ricreare la sessione e riprova
                        try:
                            session.rollback()
                            with Session(engine) as retry_session:
                                if check_if_already_processed(retry_session, job_data['partner_job_id']):
                                    print(f"  ⏭️  Job ID {job_data['id']} (partner_job_id: {job_data['partner_job_id']}) già processato, skip...")
                                    total_skipped += 1
                                    continue
                        except:
                            # Se anche il retry fallisce, salta questo record
                            print(f"  ⚠️  Impossibile verificare Job ID {job_data['id']}, skip...")
                            continue
                    
                    # Migliora la job_description
                    print(f"  🔄 Processando Job ID {job_data['id']}...")
                    improved_description = improve_job_description_with_openai(job_data['job_description'])
                    
                    # Crea nuovo JobPostings con tutti i campi copiati
                    job_posting = JobPostings(
                        position=job_data['position'],
                        description=improved_description,
                        company=job_data['company'],
                        apply_url=job_data['apply_url'],
                        company_id=job_data['company_id'],
                        location=job_data['location'],
                        workplace_types=job_data['workplace_types'],
                        experience_level=job_data['experience_level'],
                        jobtype=job_data['jobtype'],
                        partner_job_id=job_data['partner_job_id'],
                        last_build_date=job_data['last_build_date'],
                        created_at=job_data['created_at'],
                        updated_at=job_data['updated_at']
                    )
                    
                    # Inserisci immediatamente il record
                    try:
                        session.add(job_posting)
                        session.commit()
                        improved_job_postings.append(job_posting)
                        total_processed += 1
                        total_inserted += 1
                    except Exception as e:
                        print(f"  ⚠️  Errore inserendo Job ID {job_data['id']}: {e}")
                        session.rollback()
                        # Prova a inserire con una nuova sessione
                        try:
                            with Session(engine) as retry_session:
                                retry_session.add(job_posting)
                                retry_session.commit()
                                improved_job_postings.append(job_posting)
                                total_processed += 1
                                total_inserted += 1
                        except Exception as retry_e:
                            print(f"  ⚠️  Impossibile inserire Job ID {job_data['id']} anche dopo retry: {retry_e}")
                            continue
                    
            except Exception as e:
                print(f"  ⚠️  Errore processando Job ID {job_data['id']}: {e}")
                continue
        
        # Mostra riepilogo del batch
        if improved_job_postings:
            print(f"  ✅ Batch {batch_num}/{total_batches} completato. Inseriti {len(improved_job_postings)} record.")
        else:
            print(f"  ✅ Batch {batch_num}/{total_batches} completato (nessun nuovo record da inserire).")
        
        print(f"  📊 Progresso: {total_processed} processati, {total_skipped} saltati, {total_inserted} inseriti")
    
    print(f"\n{'='*60}")
    print(f"Riepilogo finale:")
    print(f"  - Totali processati: {total_processed}")
    print(f"  - Totali saltati (già presenti): {total_skipped}")
    print(f"  - Totali inseriti: {total_inserted}")
    print(f"{'='*60}")


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
    
    # Verifica configurazione
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY non trovata nel file .env")
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL non trovata nel file .env")
    
    try:
        # Crea engine e sessione
        engine = create_database_engine()
        
        with Session(engine) as session:
            # 1. Verifica quanti record sono già in job_postings
            existing_count = len(session.exec(select(JobPostings)).all())
            if existing_count > 0:
                print(f"Trovati {existing_count} record già processati in job_postings.")
                print("Lo script processerà solo i nuovi record (non ancora presenti).\n")
            else:
                print("Tabella job_postings vuota, processerò tutti i record da job_posting_pre.\n")
            
            # 2. Leggi tutti i record da job_posting_pre
            job_postings_pre = fetch_all_job_postings_pre(session)
            
            if not job_postings_pre:
                print("Nessun job posting trovato in job_posting_pre. Script terminato.")
                return
            
            # 3. Processa e inserisci in modo incrementale (salta quelli già processati)
            # Passa engine invece di session per creare nuove sessioni per ogni batch
            process_and_insert_incremental(engine, job_postings_pre, batch_size=20)
        
        # 4. Verifica finale che tutti i partner_job_id siano stati processati
        all_processed = verify_all_processed(engine)
        
        print("\n" + "=" * 60)
        if all_processed:
            print("✅ Script completato con successo! Tutti i record sono stati processati.")
        else:
            print("⚠️  Script completato, ma alcuni record non sono stati processati.")
            print("   Riavvia lo script per processare i record mancanti.")
        print("=" * 60)
        
    except Exception as e:
        print(f"Errore durante l'esecuzione dello script: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

