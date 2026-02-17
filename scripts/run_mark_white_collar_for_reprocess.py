#!/usr/bin/env python3
"""
Esegue l'UPDATE che segna per riprocessamento solo i record con collar_type = 'white'.
Usa le stesse credenziali di enrichment/.env (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD).

Dopo aver lanciato questo script, lancia il pipeline:
  python -m enrichment --batch-size 200 --mode incremental
"""

import sys
from pathlib import Path

# Add project root for imports
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text

from enrichment.db import get_engine


def main():
    engine = get_engine()
    with engine.connect() as conn:
        # Quanti white collar ci sono
        result = conn.execute(text("SELECT COUNT(*) FROM job_enrichment WHERE collar_type = 'white'"))
        count = result.scalar() or 0
        print(f"Righe con collar_type = 'white': {count}")

        if count == 0:
            print("Nessuna riga da segnare. Esco.")
            return

        # Segna per riprocessamento (sector_method = '' -> needs_repair)
        conn.execute(
            text("UPDATE job_enrichment SET sector_method = '' WHERE collar_type = 'white'")
        )
        conn.commit()
        print(f"Fatto: {count} righe segnate per riprocessamento (sector_method impostato a vuoto).")
        print("Ora lancia: python -m enrichment --batch-size 200 --mode incremental")


if __name__ == "__main__":
    main()
