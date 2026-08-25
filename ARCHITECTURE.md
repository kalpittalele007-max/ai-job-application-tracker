# Architecture Notes

## Request flow
1. Authenticated user creates or imports an application.
2. Cloud Run validates the request.
3. Firestore stores the normalized application and draft metadata.
4. Generation requests retrieve job details and historical drafts.
5. Vertex AI Gemini receives structured context and returns a draft.
6. Draft is stored against the same `jobId`.
7. Cloud Scheduler periodically invokes a nudge endpoint.
8. Pub/Sub handles bulk imports and asynchronous generation.

## Data model

Application:
- id
- userId
- company
- role
- applicationDate
- jobType
- description
- status
- createdAt
- updatedAt

Draft:
- id
- jobId
- type: cover_letter | follow_up_email
- contents
- status: draft | sent
- createdAt

This separation allows the evaluator dataset to remain compatible with the challenge while supporting multiple users and document histories in production.
