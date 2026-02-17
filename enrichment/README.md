# Job Enrichment Pipeline

Pipeline per arricchire gli annunci in `blue_collar_copy` e scrivere risultati in `job_enrichment` e `job_education_types`. La tabella sorgente **non viene mai modificata** (solo lettura).

## Requisiti

- Python 3.11+
- File **`enrichment/.env`** (dedicato alla pipeline, senza `DATABASE_URL`)
- Tabelle **`job_enrichment`** e **`job_education_types`** nel DB `data` con lo schema atteso (vedi sotto)

### Schema tabelle di output

Se in fase di scrittura vedi `Unknown column 'job_enrichment.normalized_title'`, la tabella non ha lo schema previsto. Crea/aggiorna le tabelle nel database **data** eseguendo:

```bash
mysql -h <DB_HOST> -P <DB_PORT> -u <DB_USER> -p <DB_NAME> < scripts/create_enrichment_tables.sql
```

(usa i valori da `enrichment/.env`). Lo script crea `job_enrichment` e `job_education_types` con tutte le colonne richieste dalla pipeline.

### Ambiti white collar (gpt_questions_groups / gpt_questions)

Se nel DB hai le tabelle **gpt_questions_groups** (macro) e **gpt_questions** (micro), vengono caricate in cache e usate per classificare gli ambiti dei job **white collar**. Il risultato va in `job_enrichment.gpt_group_id`, `gpt_question_id`, `gpt_confidence`, `gpt_method`. Aggiungi queste colonne a `job_enrichment` se non le hai già (vedi script SQL o ALTER TABLE).

## Configurazione

Per evitare conflitti con il `.env` in root (dove c’è `DATABASE_URL` per altri script), la pipeline legge **solo** da **`enrichment/.env`** se esiste, altrimenti dalla root.

1. Copia `enrichment/.env.example` in **`enrichment/.env`**
2. Compila in `enrichment/.env`: `DB_HOST`, `DB_PORT`, **`DB_NAME=data`**, `DB_USER`, `DB_PASSWORD`, `OPENAI_API_KEY`
3. **Non** mettere `DATABASE_URL` in `enrichment/.env` (è usato da altri script e punta a `lw`)

Variabili opzionali: `MAX_LLM_CALLS_PER_RUN` (0 = illimitato, default; imposta es. 5000 per limitare il costo), `PROCESSING_VERSION`, `OPENAI_MODEL`

## Esecuzione

Dalla root del progetto:

```bash
python -m enrichment --batch-size 200 --mode incremental
```

Opzioni:

- `--batch-size`: dimensione batch (default 200)
- `--mode`: `full` | `incremental` | `only_new` — incremental = job senza enrichment, o updated_at cambiato, o needs_repair; **only_new** = solo job in `blue_collar_copy` senza riga in `job_enrichment` (utile dopo inserimenti manuali)
- `--processing-version`: valore scritto in `job_enrichment.processing_version` (default da env o `pipeline_v1`)

## Comportamento

- **Keyset pagination**: nessun `OFFSET`; sempre `WHERE id > last_id ORDER BY id LIMIT batch_size`
- **Tabella sorgente immutabile**: nessuna scrittura su `blue_collar_copy`
- **Scritture solo su**: `job_enrichment`, `job_education_types`
- **Tassonomie**: caricate una volta all'avvio in memoria (cache). Per i job **blue collar** si usano macro_sector_copy / micro_sector_copy (sector_macro_id, sector_micro_id). Per i job **white collar** si usano gpt_questions_groups / gpt_questions (gpt_group_id, gpt_question_id) se le tabelle esistono nel DB
- **LLM**: solo come fallback; opzionale limite `MAX_LLM_CALLS_PER_RUN` (default 0 = nessun limite)
- **Retry**: batch ritentato fino a 3 volte con exponential backoff in caso di errori DB/rete
- **Sessioni corte**: una sessione per batch (apri → processa → commit → chiudi)
- **Idempotenza**: upsert su `job_enrichment`; ri-esecuzione sicura in modalità incremental

## Metriche (log strutturato)

- jobs processate per batch e totali
- tempo per batch
- throughput (jobs/sec)
- fallback LLM count
- error rate
- retry count (batch)

## Sicurezza

- Nessun hardcoding di credenziali
- Config da `enrichment/.env` (o root `.env` se non esiste)
- `enrichment/.env` e `.env` sono in `.gitignore`

## Uscire dal virtualenv

Dopo l’esecuzione resti nel prompt `(.venv)`. Per uscire dal virtualenv:

```bash
deactivate
```
