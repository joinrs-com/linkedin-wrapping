# LinkedIn Wrapping Service

FastAPI service that provides job posting data for LinkedIn wrapping via XML API.

## Features

- GET `/wrapping` – XML per LinkedIn (apply URLs con `utm_source=linkedin`)
- GET `/wrapping/jooble` – XML Jooble/Talent da `jooble_job_feed` (annunci Italia, pipeline automatica)
- GET `/wrapping/talent` – stesso XML di Jooble, dati da `jooble_job_feed`
- GET `/wrapping/jooble/abroad` – XML Jooble separato per annunci enterprise all'estero (`jooble_abroad_job_feed`, refresh manuale)
- GET `/wrapping/whatjobs` – XML WhatJobs da `whatjobs_job_feed` (annunci Italia, refresh manuale, no OpenAI)
- Database migrations using Alembic with `lw` schema
- Helm chart for Kubernetes deployment
- CI/CD with GitHub Actions
- Unit tests using pytest

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

## API Endpoints

### GET /wrapping

Returns XML with job postings for **LinkedIn** wrapping. Apply URLs are rewritten with `utm_source=linkedin`.

### GET /wrapping/jooble

Feed Jooble **principale** (e Talent.com su `/wrapping/talent`). Legge da `lw.jooble_job_feed` (annunci Italia). Aggiornata automaticamente da `scripts/run_job_feed_pipeline.py` (6:00 e 15:00 Europe/Rome via CronJob K8s).

L'`apply_url` è il link canonico del job senza query (es. `https://www.joinrs.com/jobs/{id}`).

**Test manuale pipeline:**

```bash
# .env: DATABASE_URL (lw), JOB_FEED_SOURCE_DATABASE_URL (production), OPENAI_API_KEY
python scripts/run_job_feed_pipeline.py
```

**Response:**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<source>
  <lastBuildDate> Mon, 08 Jan 2024 11:34:23 GMT </lastBuildDate>
  <job>
    <partnerJobId><![CDATA[1]]></partnerJobId>
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

Feed Jooble **separato** per annunci enterprise con location non solo in Italia. Legge da `lw.jooble_abroad_job_feed` (refresh manuale giornaliero, come Hirematic).

Stesso schema XML di `/wrapping/jooble`, con in più `<priority>`, `<employers_id>` e `<countries>`. La description è pre-formattata in SQL (non passa da OpenAI).

**Refresh manuale:**

```bash
# 1. Svuota tabella
mysql ... < scripts/sql/jooble_abroad_job_feed_truncate.sql

# 2. Esegui SELECT ed importa in lw.jooble_abroad_job_feed
# scripts/sql/jooble_abroad_job_feed_select.sql
```

Dopo `alembic upgrade head` la tabella viene creata automaticamente.

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

### GET /

Root endpoint with service information.

## Job feed pipeline (automatica)

`scripts/run_job_feed_pipeline.py` sincronizza in modo **incrementale** (INSERT solo nuovi, DELETE solo scaduti, mai TRUNCATE):

1. OpenAI su job **nuovi** priority 1–3 con location Italia → `job_description_enriched`
2. Sync `job_postings`, `jooble_job_feed`, `whatjobs_job_feed`, `hirematic_job_feed`

**Variabili `.env`:**

- `DATABASE_URL` — joinrs-intelligence / `lw` (destinazione)
- `JOB_FEED_SOURCE_DATABASE_URL` — mysql-production01 / `job_postings` (sorgente)
- `OPENAI_API_KEY` — richiesta solo se ci sono nuovi job da arricchire

**CronJob K8s:** 6:00 e 15:00 Europe/Rome (`helm-chart`, `jobFeedPipeline.enabled: true`).

Report ultimo run:

```sql
SELECT * FROM job_feed_pipeline_run ORDER BY id DESC LIMIT 1;
```

Dopo il deploy, esegui le migrazioni `0012` e `0013`:

```bash
cd api/wrapping && alembic upgrade head
```

**Recovery dopo errore OpenAI** (es. `401 invalid_api_key` durante il primo run): correggi `OPENAI_API_KEY`, poi svuota la tabella enriched prima di rilanciare, altrimenti i job già inseriti con description grezza non verranno riprocessati:

```sql
TRUNCATE TABLE job_description_enriched;
```

### GET /health

Health check endpoint.

## Testing

Root endpoint with service information.

## Testing

I test automatici vivono solo in [`tests/`](tests/). La root del repo contiene [`pytest.ini`](pytest.ini) con `testpaths = tests`, così `pytest` non raccoglie file sotto `scripts/` anche se il nome assomiglia a un test.

Esegui la suite da root:

```bash
python3 -m pytest
```

Equivalente esplicito:

```bash
python3 -m pytest tests/ -v
```

**Demo manuale OpenAI** (non è un test pytest; richiede `.env` con DB e chiave): `python3 scripts/demo_improve_job_descriptions.py`

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
- `OPENAI_API_KEY`: OpenAI key (pipeline enrichment)


