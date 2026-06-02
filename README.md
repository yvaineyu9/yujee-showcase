# Yujee — AI Memoir Magazine Maker

Turn a pile of phone photos into a beautiful, print-ready memoir magazine in
minutes. An AI reads your photos, writes your story, and lays out every page.

**▶ Live product: https://yujeeai.com**

Built for the UCWS Singapore Hackathon 2026 · Tracks: Application, Agent

---

## What it does

Upload your trip photos and Yujee does the whole job:

1. **Reads every photo** — scene, people, mood, orientation.
2. **Writes the story** — groups photos into titled chapters in a warm editorial voice.
3. **Lays out a magazine** — across 21 hand-designed templates, with real typographic constraints.
4. **Edit by chatting** — "make chapter 2 shorter, warmer" and the text rewrites live.
5. **Export** — a print-ready PDF you can bind.

One engine already powers travel albums, baby's-first-year books, graduation
yearbooks, pet diaries, and family-history reprints.

## Architecture

A stateless three-stage AI pipeline:

```
Browser ──► Web (Next.js) ──► Agent (FastAPI)
                │                  vision → writing → composing
                ▼
          Postgres + R2
```

- **Vision** — multi-image understanding (Volcano doubao) in a single call.
- **Writing** — editorial concept: title, subtitle, visual style (DeepSeek).
- **Composing** — photos → pages across the 21-template registry, with strict
  schema validation and a one-shot self-repair on rule violations.

**Privacy by design:** original photos never touch the server. They are
compressed in-browser, and the final PDF is generated client-side. The agent is
stateless — it holds no user data.

Full design: [`docs/architecture.md`](docs/architecture.md) ·
[`docs/agent/design.md`](docs/agent/design.md) ·
[`docs/agent/contract.md`](docs/agent/contract.md)

## Tech stack

Next.js 15 · React 19 · TypeScript · Drizzle ORM · Neon Postgres · better-auth ·
Python 3.12 · FastAPI · Volcano doubao vision · DeepSeek · Cloudflare R2 ·
Vercel · Fly.io · @react-pdf/renderer · Zod

## About this repository

This is a **showcase repository**. The production system is live at
yujeeai.com. To protect commercial IP:

- The **web frontend source** and **production configuration** are not included.
- The **proprietary AI prompts and model orchestration** are withheld — see
  [`apps/agent/src/services/PROPRIETARY.md`](apps/agent/src/services/PROPRIETARY.md).

What you **can** read and run here:

- `docs/` — the full system architecture, agent pipeline design, API contract,
  data model, and engineering conventions.
- `packages/contracts/` — the cross-service Zod schemas and TypeScript types
  (the single source of truth for the Web ↔ Agent protocol).
- `apps/agent/` — the FastAPI agent **skeleton**: routes, schemas, settings,
  structured logging with PII redaction, the deterministic business-rule
  validator, mock implementations, and tests. It runs end to end in mock mode:

```bash
cd apps/agent
pip install -r requirements.txt
AGENT_PIPELINE_MODE=mock AGENT_SHARED_SECRET=dev pytest
```

No secrets, API keys, or production credentials are included in this repository.
