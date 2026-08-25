# AI Job Application Tracker

A hackathon-ready MVP for tracking job applications, generating contextual drafts, and preparing scheduled follow-ups.

## Core capabilities
- Application dashboard and pipeline: Applied → Interview → Offer / Reject
- Job/application fields matching the challenge requirements
- Draft generation for cover letters and follow-up emails
- Job ID based data linking
- Evaluator sample-data import
- REST API with validation and persistent state in the demo runtime
- Cloud Run-ready container
- GCP architecture designed for Identity Platform, Firestore, Vertex AI Gemini, Pub/Sub and Cloud Scheduler

## Architecture

```text
User
  ↓
Cloud Run (web app + API)
  ├── Identity Platform → authentication
  ├── Firestore → applications, drafts, status transitions
  ├── Vertex AI Gemini → contextual cover letters / follow-ups
  ├── Pub/Sub → asynchronous ingestion and generation jobs
  └── Cloud Scheduler → scheduled nudge workflow
```

The included MVP runs without cloud credentials so evaluators can immediately inspect the product. The `/api/generate` endpoint currently uses a deterministic fallback; it is intentionally isolated so it can be replaced by a Vertex AI Gemini call without changing the UI contract.

## Challenge dataset

The importer accepts postings shaped as:
`<id>, <from>, <to>, <type>, <description>`

The application model also supports associated documents through `jobId`, with document types such as `cover_letter` and `follow_up_email`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:8080`.

## Deploy

The included Dockerfile is compatible with Cloud Run. For production, replace the in-memory repository with Firestore and connect Vertex AI Gemini using a service account with least-privilege IAM.

## Security

Production deployment should use Identity Platform for authentication, Firestore security rules/IAM for tenant isolation, Secret Manager for secrets, HTTPS by default, and Cloud Logging/Monitoring for observability.

## Roadmap

1. Firestore repository layer
2. Identity Platform authentication
3. Vertex AI Gemini generation with retrieved job/draft context
4. Pub/Sub bulk ingestion
5. Cloud Scheduler follow-up nudges
6. Draft history and status-transition audit log
7. Production deployment and monitoring
