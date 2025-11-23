#!/usr/bin/env python3
"""
Script per monitorare il progresso del processamento dei job postings.
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv
from sqlmodel import Session, select, create_engine

# Aggiungi il path del progetto per gli import
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from api.wrapping.models import JobPostingPre, JobPostings

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


def monitor_progress():
    """Monitora il progresso del processamento."""
    engine = create_database_engine()
    
    print("=" * 60)
    print("MONITOR PROGRESSO - Job Descriptions Processing")
    print("=" * 60)
    print("Premi Ctrl+C per uscire\n")
    
    last_count = 0
    
    try:
        while True:
            with Session(engine) as session:
                # Conta record in job_posting_pre (totali da processare)
                total_to_process = len(session.exec(select(JobPostingPre)).all())
                
                # Conta record in job_postings (già processati)
                processed_count = len(session.exec(select(JobPostings)).all())
                
                # Calcola percentuale
                if total_to_process > 0:
                    percentage = (processed_count / total_to_process) * 100
                else:
                    percentage = 0
                
                # Calcola nuovi record processati
                new_records = processed_count - last_count
                
                # Mostra progresso
                print(f"\r📊 Progresso: {processed_count}/{total_to_process} ({percentage:.1f}%)", end="")
                
                if new_records > 0:
                    print(f" | +{new_records} nuovi record", end="")
                
                # Se completato
                if processed_count >= total_to_process and total_to_process > 0:
                    print("\n\n✅ COMPLETATO! Tutti i record sono stati processati.")
                    break
                
                last_count = processed_count
            
            time.sleep(5)  # Aggiorna ogni 5 secondi
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Monitoraggio interrotto.")
        print(f"📊 Stato finale: {processed_count}/{total_to_process} record processati ({percentage:.1f}%)")


if __name__ == "__main__":
    monitor_progress()

