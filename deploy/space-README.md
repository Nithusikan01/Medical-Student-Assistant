---
title: Medical Student Assistant API
emoji: 🩺
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
---

# Medical Student Assistant — API

FastAPI backend for a retrieval-augmented study assistant. Students ask
questions that are answered only from a shared library of PDFs an
administrator curates.

This Space holds **deployed** code. It is generated from the
`Medical-Student-Assistant` repository by CI — edit the source there, not
here, or the next deploy will overwrite your changes.

## What runs here

- Retrieval over Pinecone, fusing dense and BM25 results, then reranked.
- Embedding and reranking run on Pinecone hosted inference, so this image
  carries no model weights and starts in seconds.
- Answers are generated with Google Gemini.
- Users, conversations, and the document registry live in Postgres.

The browser talks to this API through the frontend's origin, so the
authentication cookie stays first-party.

## Required secrets

Set these under Settings → Repository secrets:

| Secret | Purpose |
| --- | --- |
| `DATABASE_URL` | Postgres connection string (`postgresql+psycopg://…`) |
| `PINECONE_API_KEY` | Vector store and hosted inference |
| `PINECONE_INDEX_NAME` | Index to use — must be 1024 dimensions, cosine |
| `GEMINI_API_KEY` | Answer generation |
| `SECRET_KEY` | Signs access tokens |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Seeds the first administrator on boot |
| `CORS_ORIGINS` | The frontend origin |
| `COOKIE_SECURE` | `true` — the refresh cookie must be HTTPS-only |
| `ALLOW_OPEN_REGISTRATION` | `false` — registration requires an invite code |

Database migrations are applied by CI before this Space is updated, so the
schema is already current when the container starts.
