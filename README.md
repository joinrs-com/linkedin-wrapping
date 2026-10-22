# LinkedIn Wrapping Service

FastAPI service that provides job posting XML feeds for partner platforms.

## Features

- GET `/wrapping/jooble` – XML Jooble da artefatto gzip (fallback live da `jooble_job_feed`; ITA+ESP)
- GET `/wrapping/talent` – come Jooble, description Talent precomputata; artefatto gzip
- GET `/wrapping/jooble/abroad` – XML Jooble abroad (set enterprise + tutti ESP); artefatto gzip
- GET `/wrapping/whatjobs` – XML WhatJobs da `whatjobs_job_feed` (annunci Italia)
- GET `/wrapping/hirematic` – XML Appcast Hirematic da `hirematic_job_feed`
- GET `/wrapping/adzuna` – XML Adzuna da artefatto gzip (ITA+ESP, CPC da priority)
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
| **Jooble** `/wrapping/jooble` | ITA **o** ESP | 1–5 | product `pro`/`one`/`pro_unlimited` (o NULL); blacklist `1179402`; **una riga per città ITA/ESP**; `jooble_job_feed`; XML da `feed_xml_artifact` |
| **Talent** `/wrapping/talent` | come Jooble | come Jooble | stessa tabella; `description_talent` precomputata; XML da artefatto gzip |
| **WhatJobs** `/wrapping/whatjobs` | solo ITA | 1–5 | stessi product/exclude di Jooble; `region` tipo Città, Italy; `whatjobs_job_feed` |
| **Hirematic** `/wrapping/hirematic` | IT + ES (prima location ITA/ESP) | 1–3 (+ whitelist) | product `one`/`pro`; whitelist employer `2434743`, `829928` (Renfe); CPC null; `hirematic_job_feed` |
| **Jooble abroad** `/wrapping/jooble/abroad` | (A) non Italia-only + (B) tutti ESP | A: 1–4 / P5 ESP; B: 1–5 | UNION set enterprise attuale + ESP pieno (NULL product ammesso in B); artefatto gzip |
| **Adzuna** `/wrapping/adzuna` | ITA **o** ESP | 1–5 | CPC invariato; **una riga per città**; country `IT`/`ES`; artefatto gzip |
| **Job Rapido** `/wrapping/jobrapido` | solo ITA | 1–5 | stessi CPC di Adzuna; schema XML ufficiale; una riga per job (prima location); `jobrapido_job_feed` |

**Volume** (ordine di grandezza post ITA+ESP + artefatti):

| Endpoint | Righe tipiche | Serving |
| --- | ---: | --- |
| Jooble / Talent / Adzuna | ~78–80k | gzip da `lw.feed_xml_artifact` (pipeline); fallback live se assente |
| Jooble abroad | ~30k | idem |
| WhatJobs / Job Rapido | ~42k | live (senza artefatto) |
| Hirematic | ~1k | live |

La pipeline, dopo il sync delle tabelle, genera XML → gzip → UPSERT in `feed_xml_artifact` (`jooble`, `talent`, `adzuna`, `jooble_abroad`). Gli endpoint streamano il blob con `Content-Encoding: gzip`.

**Description (feed ITA/ESP):** employer Joinrs (`327107`, `829928`, `829944`, `829946`, `829948`, `829951`, `848251`, `2006564`, `4004682`) → solo body. Altri → intro IT (ITA) o EN (ESP/abroad) + body. Nessun tag sponsorship. URL `https://www.joinrs.com/jobs/{job_posting_id}` (senza `-n`).

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

Feed Jooble **principale** (e Talent.com su `/wrapping/talent`). Contenuto ITA+ESP da `lw.jooble_job_feed`; in produzione l’XML gzip arriva da `lw.feed_xml_artifact`. Aggiornata da `scripts/run_job_feed_pipeline.py` (6:00 e 15:00 Europe/Rome).

Una riga per città ITA/ESP: `partnerJobId` = `{job_posting_id}-{ord}`. `apply_url` canonico senza query. Dopo `alembic upgrade head` (fino a `0022`) anche tabella `feed_xml_artifact`.

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

Feed Jooble **abroad**: unione di (A) regole enterprise non Italia-only (product pro/one/unlimited, combo con ITA) e (B) **tutti** gli annunci ESP con filtri Italia (NULL product ammesso → Adecco Spain). XML da artefatto gzip. Intro EN per non-Joinrs; tag `<countries>` incluso.

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


