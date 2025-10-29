I want to build a new FastAPI service:
linkedin-wrapping

* generates all the endpoints
* create the alembic migrations, use DATABASE_URL env to configure the db and create a schema called authdb 
* create a helm-chart dir for helm deployment copying from ../pandora/job-postings-services 
* create a github action for CI
* create an http file for simple testing
* create a suite of unit tests that can run without db

1) Services (granular, single-purpose)
	1.	Linked Wrapping 

	•	using a db query returns the job postings available to be published to linkedin via wrapping

⸻


3) linkedin wrapping, return an xml that will contain data for the linkeind wrapping

	•	GET /wrapping
body: <postings>
  <job 
  "id"=<job posting id1> 
  "position"= <job posting position> 
  />
  <job 
  "id"=<job posting id 2> 
  "position"= <job posting position> 
  />
</postings>


