# Yujee — AI Memoir Magazine Maker

Right now, thousands of photos are sitting in your phone and your cloud — and
you've never gone back to look at them. Yujee turns that scattered, invisible
data into a magazine made just for you: an AI reads your photos, writes your
story, and lays out every page into something you can print and hold.

**▶ Live product: https://yujeeai.com**

Built for the UCWS Singapore Hackathon 2026 · Tracks: Application, Agent

---

## What it does

Give Yujee your photos and tell it what they meant to you:

1. **Reads every photo** — scene, people, mood, orientation.
2. **Writes the story** — groups photos into titled chapters in a warm editorial voice.
3. **Lays out a magazine** — across 21 hand-designed templates, with real typographic constraints.
4. **Edit by chatting** — "make chapter 2 shorter, warmer" and the text rewrites live.
5. **Export** — a print-ready PDF you can bind into a real book.

You bring the soul — the moments and the feelings. Yujee brings the craft.
No design or writing background required.

## Architecture — an orchestrated AI agent

The core engineering of Yujee is **agent orchestration**: coordinating several
specialized AI models into one reliable, end-to-end flow that turns raw photos
into a finished, print-ready magazine.

```
Browser ──► Web (Next.js) ──► Agent (FastAPI)
                │            vision → writing → composition
                ▼            (orchestrated · schema-validated · self-repairing)
          Postgres + R2
```

The agent runs a stateless multi-stage pipeline:

- **Vision** — multi-image understanding (vision models): scene, people, mood,
  and orientation in a single pass.
- **Writing** — editorial concept and chapter text: title, subtitle, voice (DeepSeek).
- **Composition** — photos → pages across the 21-template registry.

What holds it together is the orchestration layer around those stages: a strict
schema contract between every step, deterministic business-rule validation, and
a one-shot self-repair when a model output violates the rules — so every page is
typographically sound, every time.

**Privacy by design:** original photos never touch the server. They are
compressed in-browser, and the final PDF is generated client-side. The agent is
stateless — it holds no user data.

Full design: [`docs/architecture.md`](docs/architecture.md) ·
[`docs/agent/design.md`](docs/agent/design.md) ·
[`docs/agent/contract.md`](docs/agent/contract.md)

## Tech stack

Next.js 15 · React 19 · TypeScript · Drizzle ORM · Neon Postgres · better-auth ·
Python 3.12 · FastAPI · vision models · DeepSeek · Cloudflare R2 ·
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
