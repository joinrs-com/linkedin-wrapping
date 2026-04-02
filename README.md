# LinkedIn Wrapping Service

FastAPI service that provides job posting data for LinkedIn wrapping via XML API.

## Features

- GET `/wrapping` – XML per LinkedIn (apply URLs con `utm_source=linkedin`)
- GET `/wrapping/jooble` – XML per Jooble; stessi dati di LinkedIn, `apply_url` con `utm_source=jooble` (stesso link base salvato in `job_postings`)
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

Restituisce lo stesso formato XML per **Jooble**. L’`apply_url` è quello salvato in `job_postings` (es. `https://www.joinrs.com/it/jobs/{id}/?utm_source=linkedin&...`) con il parametro `utm_source` impostato a **`jooble`**; non serve tabella di mapping.

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

Se in passato avevi creato la tabella `job_jooble_mapping`, la migrazione Alembic `0007_drop_job_jooble_mapping` la rimuove: esegui `alembic upgrade head`. In alternativa puoi eliminarla manualmente dal database.

## Deployment

### Helm Chart

Deploy using Helm:
```bash
helm install linkedin-wrapping ./helm-chart \
  -f ./helm-chart/environments/stage/values.yaml
```

### Environment Variables

- `DATABASE_URL`: Database connection string (required)


