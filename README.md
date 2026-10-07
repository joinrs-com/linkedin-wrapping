# LinkedIn Wrapping Service

FastAPI service that provides job posting XML feeds for partner platforms.

## Features

- GET `/wrapping/jooble` – XML Jooble da `jooble_job_feed` (annunci Italia, pipeline automatica)
- GET `/wrapping/talent` – stesso XML di Jooble, description HTML sanitizzata per Talent.com
- GET `/wrapping/jooble/abroad` – XML Jooble per annunci enterprise all'estero (`jooble_abroad_job_feed`, pipeline automatica, senza OpenAI)
- GET `/wrapping/whatjobs` – XML WhatJobs da `whatjobs_job_feed` (annunci Italia)
- GET `/wrapping/hirematic` – XML Appcast Hirematic da `hirematic_job_feed`
- GET `/wrapping/adzuna` – XML Adzuna da `adzuna_job_feed` (Italia, CPC da priority)
- GET `/wrapping/jobrapido` – XML Job Rapido da `jobrapido_job_feed` (schema ufficiale, una riga per job come Adzuna, CPC da priority)
- Database migrations using Alembic with `lw` schema
- Helm chart for Kubernetes deployment
- CI/CD with GitHub Actions
- Unit tests using pytest

## Sponsorship feed XML

Matrice degli annunci sponsorizzati per piattaforma (filtri SQL attuali):

| XML | Country | Priority | Note |
| --- | --- | --- | --- |
| **LinkedIn** `/wrapping` | — | — | **Rimosso** (endpoint 404; non più in pipeline). SQL legacy in `job_postings_select.sql` non esposto. |
| **Jooble** `/wrapping/jooble` | solo ITA (`has_ita=1`) | 1–5 | product `pro`/`one`/`pro_unlimited` (o NULL); blacklist employer `1179402`; **una riga per città ITA** (`id`/`partnerJobId` = `job_id-n`); `jooble_job_feed`; pipeline automatica |
| **Talent** `/wrapping/talent` | come Jooble | come Jooble | stessa tabella `jooble_job_feed` (description HTML sanitizzata Talent) |
| **WhatJobs** `/wrapping/whatjobs` | solo ITA | 1–5 | stessi product/exclude di Jooble; `region` tipo Città, Italy; `whatjobs_job_feed` |
| **Hirematic** `/wrapping/hirematic` | IT + ES (prima location ITA/ESP) | 1–3 (+ whitelist) | product `one`/`pro`; whitelist employer `2434743`, `829928` (Renfe); CPC null; `hirematic_job_feed` |
| **Jooble abroad** `/wrapping/jooble/abroad` | non Italia-only | 1–4; P5 solo ESP | combo employer/product/priority con anche job ITA; **una riga per città** (`id`/`partnerJobId` = `job_id-n`); intro EN solo non-Joinrs; `jooble_abroad_job_feed` |
| **Adzuna** `/wrapping/adzuna` | solo ITA | 1–5 | CPC `1→0.08`, `2→0.07`, `3/4→0.03`, `5→0`; **una riga per città ITA** (`id` = `job_id-n`); `adzuna_job_feed` |
| **Job Rapido** `/wrapping/jobrapido` | solo ITA | 1–5 | stessi CPC di Adzuna; schema XML ufficiale; una riga per job (prima location); `jobrapido_job_feed` |

**Description (feed Italia):** employer Joinrs (`327107`, `829928`, `829944`, `829946`, `829948`, `829951`, `848251`, `2006564`, `4004682`) → solo body, senza intro multi-location. Altri employer → intro + body. Nessun tag sponsorship (`[#LI-REMOTE]`, `[#J-MCITY]`, `[#J-ENTERPRISE]`, `[#J-ONE]`, `[#J-MIN]`, `[#J-INTERNAL]`) nelle description (anche abroad: solo rimozione tag). URL applicative restano `https://www.joinrs.com/jobs/{job_posting_id}` (senza `-n`).

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

### GET /wrapping/jooble

Feed Jooble **principale** (e Talent.com su `/wrapping/talent`). Legge da `lw.jooble_job_feed` (annunci Italia). Aggiornata automaticamente da `scripts/run_job_feed_pipeline.py` (6:00 e 15:00 Europe/Rome via CronJob K8s).

Una riga per città ITA: `partnerJobId` = `{job_posting_id}-{ord}` (es. `12345-1`). L'`apply_url` è il link canonico senza query e senza ordinalità (es. `https://www.joinrs.com/jobs/12345`). Include `<salary>` quando disponibile. Dopo `alembic upgrade head` (fino a `0019`) la PK è `VARCHAR` + colonna `job_posting_id`.

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

Feed Jooble **separato** per annunci enterprise con location non solo in Italia. Legge da `lw.jooble_abroad_job_feed`, aggiornata dalla pipeline automatica (stesso CronJob di Jooble/Adzuna).

Priority **1–4** per qualsiasi location non Italia-only; priority **5** solo se c’è una location in Spagna (`ESP`). Una riga per città: `partnerJobId` = `{job_posting_id}-{ord}`; URL applicativa senza `-n`. Intro in inglese solo per employer non-Joinrs; Joinrs = solo body. Stesso schema XML di `/wrapping/jooble`, con in più `<priority>`, `<employers_id>` e `<countries>`. Description pre-formattata in SQL (no OpenAI).

Dopo `alembic upgrade head` (fino a `0020`) la PK è `VARCHAR` + `job_posting_id`.

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

`scripts/run_job_feed_pipeline.py` sincronizza in modo **incrementale** (INSERT solo nuovi, DELETE solo scaduti, mai TRUNCATE). Lo step OpenAI sulle description è **disattivato** (le description restano quelle del SELECT SQL).

Sync: `jooble_job_feed`, `whatjobs_job_feed`, `hirematic_job_feed`, `adzuna_job_feed`, `jobrapido_job_feed`, `jooble_abroad_job_feed`.

**Variabili `.env`:**

- `DATABASE_URL` — joinrs-intelligence / `lw` (destinazione)
- `JOB_FEED_SOURCE_DATABASE_URL` — mysql-production01 / `job_postings` (sorgente)

**CronJob K8s:** 6:00 e 15:00 Europe/Rome (`helm-chart`, `jobFeedPipeline.enabled: true`).

Report ultimo run:

```sql
SELECT * FROM job_feed_pipeline_run ORDER BY id DESC LIMIT 1;
```

Dopo il deploy, esegui le migrazioni fino a `0018`:

```bash
cd api/wrapping && alembic upgrade head
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


