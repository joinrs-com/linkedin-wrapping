# LinkedIn Wrapping Service

FastAPI service that provides job posting XML feeds for partner platforms.

## Features

- GET `/wrapping/jooble/it`, `/it5`, `/es`, `/us/1`…`/us/5`, `/uk`, `/fr`, `/de`, `/eu`, `/americas`, `/asia`, `/row` – Jooble, 15 feed; artefatto gzip in MySQL; **no CPC**; `<countryCode>`
- GET `/wrapping/talent/…` / `/adzuna/…` — stessi 15 path di Jooble (Adzuna con **`<cpc>`**)
- GET `/wrapping/jooble/abroad` — **ritirato, HTTP 410** (usa i feed geografici)
- GET `/wrapping/whatjobs` / `hirematic` / `jobrapido` – invariati
- Database migrations (`lw`), Helm, CI/CD, pytest

## Sponsorship feed XML

**15 feed** (explode città + country; tutte priority/product; blacklist `1179402`), description **intere**, gzip in MySQL `feed_xml_artifact` (split così ogni artifact resta sotto `max_allowed_packet`). Nessun alias root: usare `/it` e `/it5`.

| Feed | Contenuto | Path (es. Jooble) |
| --- | --- | --- |
| `it` | ITA priority 1–4 | `/jooble/it` |
| `it5` | ITA priority 5 | `/jooble/it5` |
| `es` | ESP | `/jooble/es` |
| `usa_1`…`usa_5` | USA shard | `/jooble/us/1`…`/5` |
| `uk` / `fr` / `de` | GBR / FRA / DEU | `/jooble/uk` … |
| `eu` | resto Europa + PRT + BEL | `/jooble/eu` |
| `americas` | CAN + BRA + LATAM | `/jooble/americas` |
| `asia` | Asia principale | `/jooble/asia` |
| `row` | resto mondo | `/jooble/row` |

Colonna `bucket` = feed key. Stesso schema per Talent e Adzuna.

Dopo ogni scrittura artifact: **verify-after-write** (`LENGTH(payload)` + gunzip CRC). `Content-Length` usa la lunghezza reale del blob MySQL. Opzionale: `FEED_XML_S3_BUCKET` / `feedXmlStorage.bucket` per salvare i gzip fuori da MySQL. La pipeline fa anche purge dei job solo in `job_postings_archived_1`.

Vincoli: Jooble/Talent **senza** `<cpc>`; Adzuna **con** CPC. Smoke: `bash scripts/smoke_feed_endpoints.sh`. Health: `python scripts/check_feed_endpoints.py` (HTTP + integrity DB se `DATABASE_URL` è settata).

## Setup

### Prerequisites

- Python 3.11+
- MySQL or PostgreSQL database
- Docker (optional)

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set environment variables:
```bash
export DATABASE_URL="mysql://user:password@host:port/database"
```

3. Run migrations:
```bash
cd api/wrapping
alembic upgrade head
```

### Running the Service

```bash
uvicorn main:app --host 0.0.0.0 --port 3000
```

Or using Docker:
```bash
docker build -t linkedin-wrapping-service .
docker run -p 3000:3000 -e DATABASE_URL="your-db-url" linkedin-wrapping-service
```

## Strumenti mantenuti

- `scripts/run_job_feed_pipeline.py`: sincronizzazione incrementale e generazione feed XML gzip.
- `scripts/refresh_descriptions_and_artifacts.py`: aggiornamento description dalla sorgente, normalizzazione HTML e rigenerazione artifact, senza OpenAI.
- `scripts/watch_job_feed_progress.py`: monitoraggio conteggi e ultimo run.
- `scripts/check_feed_endpoints.py`, `scripts/smoke_feed_endpoints.sh`: controlli feed.
- `scripts/count_feed_buckets.py`, `scripts/count_explode_feeds.py`: conteggi diagnostici.
- `scripts/trigger_job_feed_k8s.sh`: avvio manuale della pipeline nel cluster.

Il modulo di classificazione blue/white collar `enrichment` e la vecchia pipeline di riscrittura OpenAI sono stati rimossi. Le migrazioni Alembic e i modelli delle tabelle storiche restano per compatibilità con i database esistenti; la pulizia del codice non elimina tabelle o dati. I campi storici OpenAI nei report rimangono a zero.

## API Endpoints

### GET /wrapping/jooble/it

Feed Jooble Italy P1–4 (Talent: `/wrapping/talent/it`, Adzuna: `/wrapping/adzuna/it`). In produzione l’XML gzip arriva da `lw.feed_xml_artifact`. Aggiornata da `scripts/run_job_feed_pipeline.py` (6:00 e 15:00 Europe/Rome).

Una riga per città: `partnerJobId` = `{job_posting_id}-{ord}`. `apply_url` canonico senza query.

**Test manuale pipeline:**

```bash
# .env: DATABASE_URL (lw), JOB_FEED_SOURCE_DATABASE_URL (production)
python scripts/run_job_feed_pipeline.py
```

**Response:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<source>
  <lastBuildDate> Mon, 08 Jan 2024 11:34:23 GMT </lastBuildDate>
  <job>
    <partnerJobId><![CDATA[1-1]]></partnerJobId>
    <company><![CDATA[Example, Inc.]]></company>
    <title><![CDATA[Software Engineer]]></title>
    <description><![CDATA[<strong>Awesome role</strong>]]></description>
    <applyUrl><![CDATA[https://example.com/jobs/1]]></applyUrl>
    <companyId><![CDATA[12345]]></companyId>
    <location><![CDATA[Rome, Italy]]></location>
    <workplaceTypes><![CDATA[On-site]]></workplaceTypes>
    <experienceLevel><![CDATA[Internship]]></experienceLevel>
    <jobtype><![CDATA[Full Time]]></jobtype>
  </job>
  <!-- more <job> entries -->
```

### GET /wrapping/jooble/abroad

Endpoint ritirato: restituisce **HTTP 410 Gone** con i path dei feed geografici sostitutivi. La tabella `jooble_abroad_job_feed` viene rimossa dalla migrazione `0025_drop_jooble_abroad`; prima di applicarla occorre una copia di sicurezza dei dati. Il downgrade ricrea solo lo schema vuoto.

### GET /wrapping/whatjobs

Feed **WhatJobs** per annunci in Italia (priority 1–5). Legge da `lw.whatjobs_job_feed`, aggiornata dalla pipeline automatica.

Il `link` è il URL canonico del job senza query (es. `https://www.joinrs.com/jobs/{id}`). Formato XML WhatJobs con tag `link`, `name`, `region`, `description`, `company`, ecc. in sezioni CDATA.

**Response:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<jobs>
  <job id="3218063">
    <link><![CDATA[https://www.joinrs.com/jobs/3218063]]></link>
    <name><![CDATA[Software Engineer]]></name>
    <region><![CDATA[Milan - Italy]]></region>
    <description><![CDATA[<p>...</p>]]></description>
    <company><![CDATA[Acme Corp]]></company>
    <pubdate><![CDATA[01.06.2026]]></pubdate>
    <updated><![CDATA[08.06.2026]]></updated>
    <expire><![CDATA[31.07.2026]]></expire>
    <jobtype><![CDATA[full-time]]></jobtype>
  </job>
</jobs>
```

### GET /wrapping/adzuna

Feed **Adzuna** per annunci in Italia (priority 1–5). Legge da `lw.adzuna_job_feed`, aggiornata dalla pipeline automatica.

Una riga per città ITA: `<id>` = `{job_posting_id}-{ord}` (es. `3218063-1`). CPC da priority: `1→0.08`, `2→0.07`, `3→0.03`, `4→0.03`, `5→0`. URL con `utm_source=adzuna` (senza `-n` nel path).

**Response:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<jobs>
  <job>
    <title><![CDATA[Software Engineer]]></title>
    <id><![CDATA[3218063-1]]></id>
    <description><![CDATA[<p>...</p>]]></description>
    <url><![CDATA[https://www.joinrs.com/jobs/3218063?utm_source=adzuna]]></url>
    <location><![CDATA[Milano]]></location>
    <country><![CDATA[IT]]></country>
    <remote><![CDATA[Remote]]></remote>
    <salary><![CDATA[30000 EUR]]></salary>
    <company><![CDATA[Acme Corp]]></company>
    <cpc><![CDATA[0.08]]></cpc>
    <priority><![CDATA[1]]></priority>
  </job>
</jobs>
```

### GET /wrapping/jobrapido

Feed **Job Rapido** per annunci in Italia (priority 1–5). Legge da `lw.jobrapido_job_feed`, aggiornata dalla pipeline automatica.

Schema XML ufficiale (`<source><jobs>`): `title`, `location`, `state`, `country`, `company`, `website`, `publishdate`/`expirydate` (DD/MM/YYYY), `url`, `description`, `reference_id`, più `cpc`/`priority` come Adzuna. Una riga per job (prima location, come Adzuna); URL con `utm_source=jobrapido`.

### GET /

Root endpoint with service information.

## Job feed pipeline (automatica)

`scripts/run_job_feed_pipeline.py` sincronizza in modo **incrementale** (INSERT nuovi, DELETE scaduti, mai TRUNCATE). Jooble/Adzuna usano **two-phase select** (meta senza description, poi body solo per `job_posting_id` nuovi) + HTML normalize. Il refresh delle description esistenti è **off** di default (`--refresh-descriptions` per abilitarlo). La pipeline non usa OpenAI e non richiede chiavi API.

Sync: `jooble_job_feed` (15 bucket), `adzuna_job_feed` (15 bucket), `whatjobs_job_feed`, `hirematic_job_feed`, `jobrapido_job_feed`. Talent condivide i dati Jooble.

```bash
# tutti i feed
python scripts/run_job_feed_pipeline.py
# solo alcuni
python scripts/run_job_feed_pipeline.py --feeds jooble,adzuna
# anche UPDATE description su row già presenti (lento)
python scripts/run_job_feed_pipeline.py --refresh-descriptions
```

**Variabili `.env`:**

- `DATABASE_URL` — joinrs-intelligence / `lw` (destinazione)
- `JOB_FEED_SOURCE_DATABASE_URL` — mysql-production01 / `job_postings` (sorgente)
- `SLACK_WEBHOOK_URL` — (opzionale) Incoming Webhook: report dopo ogni pipeline + alert se endpoint unhealthy
- `FEED_PUBLIC_BASE_URL` — base URL probe HTTP (default `https://lw.joinrs.com`)
- `FEED_STALE_HOURS` — soglia stale su `X-Feed-Generated-At` (default `24`)

**CronJob K8s:** 6:00 e 15:00 Europe/Rome (`helm-chart`, `jobFeedPipeline.enabled: true`). `activeDeadlineSeconds` = 24h. Preferisci il Job in-cluster (VPC → RDS) rispetto al laptop/VPN.

**Slack ops**

1. Dopo ogni run della pipeline: messaggio con `success`/`failed`, duration, sync counts (jooble/adzuna/whatjobs/hirematic/jobrapido) e `job_count` per artifact (15 feed × piattaforma).
2. Cron orario `feedHealthCheck` (`scripts/check_feed_endpoints.py`): curl di tutti i `/wrapping/*` pubblici; Slack **solo su failure** (5xx, XML senza gzip/job, artifact stale). Success silenzioso.

```bash
# Slack → App → Incoming Webhooks → canale aziendale
kubectl -n lw create secret generic slack-webhook \
  --from-literal=url='https://hooks.slack.com/services/XXX/YYY/ZZZ'

# Manuale (laptop):
python scripts/check_feed_endpoints.py --verbose
```

Senza `SLACK_WEBHOOK_URL` / secret, pipeline e health check restano no-op su Slack.

Trigger manuale (richiede `kubectl` + contesto EKS sul namespace `lw`):

```bash
./scripts/trigger_job_feed_k8s.sh lw
kubectl logs -f job/job-feed-manual-YYYYMMDD-HHMMSS -n lw
```

Monitoring conteggi / ultimo run (laptop, VPN + `.env`):

```bash
python scripts/watch_job_feed_progress.py          # ogni 60s
python scripts/watch_job_feed_progress.py --once
```

Report ultimo run:

```sql
SELECT * FROM job_feed_pipeline_run ORDER BY id DESC LIMIT 1;
```

Per aggiornare lo schema alla versione corrente:

```bash
cd api/wrapping && alembic upgrade head
```

### GET /health

Health check endpoint.

## Testing

I test automatici vivono solo in [`tests/`](tests/). La root del repo contiene [`pytest.ini`](pytest.ini) con `testpaths = tests`, così `pytest` non raccoglie file sotto `scripts/` anche se il nome assomiglia a un test.

Esegui la suite da root:

```bash
DATABASE_URL=sqlite:// .venv/bin/python -m pytest
```

Equivalente esplicito:

```bash
DATABASE_URL=sqlite:// .venv/bin/python -m pytest tests/ -v
```

Test HTTP endpoints using `test_wrapping.http` file.

## Database Schema

The service uses the `lw` schema for job postings:

- `job_postings` table:
  - `id` (BigInteger, Primary Key)
  - `position` (String)
  - `created_at` (Timestamp)
  - `updated_at` (Timestamp)

Se in passato avevi creato la tabella `job_jooble_mapping`, la migrazione Alembic `0007_drop_job_jooble_mapping` la rimuove: esegui `alembic upgrade head`. In alternativa puoi eliminarla manualmente dal database.

## Deployment

### Helm Chart

Deploy using Helm:
```bash
helm install linkedin-wrapping ./helm-chart \
  -f ./helm-chart/environments/stage/values.yaml
```

### Environment Variables

- `DATABASE_URL`: Database connection string (required, destinazione lw)
- `JOB_FEED_SOURCE_DATABASE_URL`: MySQL production read (pipeline CronJob)
- `SLACK_WEBHOOK_URL`: Slack Incoming Webhook (pipeline + feed-health CronJobs; optional secret `slack-webhook`)
- `FEED_PUBLIC_BASE_URL`: Public base for feed health probes (default `https://lw.joinrs.com`)
- `FEED_STALE_HOURS`: Max age for artifact `X-Feed-Generated-At` (health Cron)

