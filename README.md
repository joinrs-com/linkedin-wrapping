# LinkedIn Wrapping Service

FastAPI service that provides job posting data for LinkedIn wrapping via XML API.

## Features

- GET `/wrapping` – XML per LinkedIn (apply URLs con `utm_source=linkedin`)
- GET `/wrapping/jooble` – XML per Jooble; apply URL da tabella di mapping `job_jooble_mapping` (jo_ais_id) se presente, altrimenti `apply_url` con `utm_source=jooble`
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

Restituisce lo stesso formato XML per **Jooble**. L’apply URL è:
- se esiste una riga in `job_jooble_mapping` per quel `partner_job_id`:  
  `https://www.joinrs.ai/it/jobs/{jo_ais_id}/?utm_source=jooble&utm_medium=job-offer-ats&utm_campaign={jo_ais_id}-scraped`
- altrimenti: `apply_url` del job con `utm_source=jooble`.

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

### GET /health

Health check endpoint.

### GET /

Root endpoint with service information.

## Testing

Run unit tests:
```bash
pytest tests/ -v
```

Test HTTP endpoints using `test_wrapping.http` file.

## Database Schema

The service uses the `lw` schema for job postings:

- `job_postings` table:
  - `id` (BigInteger, Primary Key)
  - `position` (String)
  - `created_at` (Timestamp)
  - `updated_at` (Timestamp)

### Tabella `job_jooble_mapping` (Jooble)

Mapping `partner_job_id` → `jo_ais_id` per costruire l’apply URL Jooble (`https://www.joinrs.ai/it/jobs/{jo_ais_id}/?...`).

**Colonne:**

| Colonna           | Tipo      | Obbligatorio | Descrizione |
|-------------------|-----------|--------------|-------------|
| `id`              | BIGINT PK | Sì           | Chiave primaria auto-increment |
| `partner_job_id`  | VARCHAR(255) | Sì        | Stesso valore di `job_postings.partner_job_id` (chiave di collegamento) |
| `jo_ais_id`       | VARCHAR(255) | Sì        | ID usato nell’URL Jooble (es. 58298) |
| `created_at`      | TIMESTAMP | No           | Default CURRENT_TIMESTAMP |

**Indice unico:** `partner_job_id` (una riga per job).

**Creazione tabella:** usare la migrazione Alembic `0006_job_jooble_mapping` (`alembic upgrade head`) oppure lo script SQL `scripts/create_job_jooble_mapping_table.sql` (MySQL senza schema).

**Popolamento:** inserire una riga per ogni annuncio che deve apparire su Jooble con l’URL joinrs.ai.

Esempio:

```sql
INSERT INTO job_jooble_mapping (partner_job_id, jo_ais_id) VALUES
('12345', '58298'),
('12346', '58299');
```

- `partner_job_id`: valore presente in `job_postings.partner_job_id` (stesso della tua fonte/query).
- `jo_ais_id`: ID che vuoi nell’URL (es. da joinrs o da altro sistema). L’URL generato sarà `https://www.joinrs.ai/it/jobs/58298/?utm_source=jooble&utm_medium=job-offer-ats&utm_campaign=58298-scraped`.

Puoi popolare a mano (INSERT o import CSV) o con uno script che legge dalla fonte dove hai già la coppia (partner_job_id, jo_ais_id).

## Deployment

### Helm Chart

Deploy using Helm:
```bash
helm install linkedin-wrapping ./helm-chart \
  -f ./helm-chart/environments/stage/values.yaml
```

### Environment Variables

- `DATABASE_URL`: Database connection string (required)


