#!/usr/bin/env python3
"""
Script per rimuovere i duplicati dalla tabella job_postings.
Mantiene solo il record più recente per ogni partner_job_id.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from sqlmodel import Session, select, create_engine, func
from collections import defaultdict

# Aggiungi il path del progetto per gli import
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.wrapping.models import JobPostings

# Carica variabili d'ambiente
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL non trovata nel file .env")


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


def find_and_remove_duplicates():
    """Trova e rimuove i duplicati dalla tabella job_postings."""
    engine = create_database_engine()
    
    print("=" * 60)
    print("RIMOZIONE DUPLICATI - job_postings")
    print("=" * 60)
    
    with Session(engine) as session:
        # Leggi tutti i record
        all_postings = session.exec(select(JobPostings)).all()
        
        # Raggruppa per partner_job_id
        grouped = defaultdict(list)
        for posting in all_postings:
            if posting.partner_job_id:
                grouped[posting.partner_job_id].append(posting)
            else:
                # Record senza partner_job_id li teniamo tutti (non possiamo deduplicare)
                grouped[None].append(posting)
        
        # Trova duplicati
        duplicates_to_remove = []
        kept_count = 0
        
        for partner_id, postings_list in grouped.items():
            if partner_id is None:
                # Mantieni tutti i record senza partner_job_id
                kept_count += len(postings_list)
                continue
            
            if len(postings_list) > 1:
                # Ci sono duplicati, mantieni il più recente (basato su updated_at o id)
                # Ordina per updated_at (più recente prima) o id (più grande = più recente)
                postings_list.sort(key=lambda x: (x.updated_at or x.created_at or x.id or 0), reverse=True)
                
                # Mantieni il primo (più recente)
                kept = postings_list[0]
                kept_count += 1
                
                # Aggiungi gli altri alla lista da rimuovere
                for posting in postings_list[1:]:
                    duplicates_to_remove.append(posting)
            else:
                # Nessun duplicato, mantieni
                kept_count += 1
        
        print(f"\n📊 Analisi:")
        print(f"  - Totali record in job_postings: {len(all_postings)}")
        print(f"  - Record da mantenere: {kept_count}")
        print(f"  - Record duplicati da rimuovere: {len(duplicates_to_remove)}")
        
        if not duplicates_to_remove:
            print("\n✅ Nessun duplicato trovato!")
            return
        
        # Mostra alcuni esempi
        print(f"\n📋 Esempi di duplicati da rimuovere (primi 5):")
        for i, posting in enumerate(duplicates_to_remove[:5], 1):
            print(f"  {i}. ID: {posting.id}, partner_job_id: {posting.partner_job_id}, updated_at: {posting.updated_at}")
        
        # Conferma e rimuovi
        print(f"\n🗑️  Rimuovendo {len(duplicates_to_remove)} record duplicati...")
        
        for posting in duplicates_to_remove:
            session.delete(posting)
        
        session.commit()
        
        print(f"✅ Rimossi {len(duplicates_to_remove)} record duplicati con successo!")
        
        # Verifica finale
        remaining_count = len(session.exec(select(JobPostings)).all())
        print(f"\n📊 Verifica finale:")
        print(f"  - Record rimanenti in job_postings: {remaining_count}")
        print(f"  - Record attesi: {kept_count}")
        
        if remaining_count == kept_count:
            print("✅ Verifica completata: i numeri corrispondono!")
        else:
            print(f"⚠️  Attenzione: discrepanza nei numeri (differenza: {remaining_count - kept_count})")


if __name__ == "__main__":
    try:
        find_and_remove_duplicates()
        print("\n" + "=" * 60)
        print("Script completato!")
        print("=" * 60)
    except Exception as e:
        print(f"Errore durante l'esecuzione: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

