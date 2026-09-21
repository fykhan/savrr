# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commit messages

Keep commits simple and lazy — short, lowercase, casual, no fluff. Never mention Claude, AI, or add
a Co-Authored-By line. Just describe what changed in a few words, like a dev committing to their own
side project. (Convention carried over from the sibling `financial-manager` repo, same author.)

## What this is

Savrr — a personal finance app intended for **real deployment to real users**: balances across
multiple accounts, transaction logging and categorization, automatic/recurring expenses, statements,
savings planning, debt tracking, visualizations, and a voice assistant that can log transactions by
speech.

Target architecture: **Supabase** (Postgres + Auth) → **FastAPI** backend with AI via **OpenRouter**
→ **React Native** client (iOS-primary, Android optional).

## Status as of 2026-09-21

**Pre-implementation.** The repo contains documentation and the Supabase CLI scaffold — no schema,
no backend, no app yet. The design for the first sub-project is approved; planning is next.

## How the work is decomposed

The project is too large for one spec, so it is split into four sub-projects, each getting its own
design → spec → plan → implementation cycle. The order is dependency-driven:

1. **Data layer & Supabase foundation** ← *current*. Schema, RLS, auth, migrations, pgTAP tests.
   Design spec: `docs/superpowers/specs/2026-09-21-data-layer-design.md`
2. **FastAPI backend** — CRUD, recurring/auto-pay catch-up, statements, categorization
3. **AI & voice layer** — OpenRouter, natural-language transaction logging
4. **React Native client** — accounts, transaction log, recurring setup, custom statements, voice UI

Nothing can be built or verified until the schema exists; the client is built last against a stable API.

## Decisions already made (do not relitigate)

Full rationale is in the spec; the short version:

- **True multi-user** — anyone signs up, data isolated per user via Supabase Auth + RLS
- **Native `uuid` primary keys** (`gen_random_uuid()`), not client-generated string ids
- **Email/password auth only** to start; social providers later, no schema change needed
- **Four-table recurring split** (income/expenses/subscriptions/installments), ported from
  financial-manager rather than consolidated into one generalized table
- **One currency per user**, stored on `profiles`; no conversion math anywhere
- **Hybrid categories** — one `categories` table, `user_id is null` = shared system default,
  `user_id = auth.uid()` = user's own addition
- **FastAPI forwards the caller's JWT** so RLS applies to backend queries too; `service_role` is
  reserved solely for the cross-user recurring catch-up job

Eleven tables: `profiles`, `accounts`, `transactions`, `income`, `expenses`, `subscriptions`,
`installments`, `savings`, `budgets`, `debts`, `categories`.

## Relationship to `financial-manager`

The sibling repo at `~/projects/financial-manager` (GradPlan) is a working single-user web app that
already implements most of Savrr's domain logic — FastAPI + SQLModel + Neon Postgres, with a
dependency-free vanilla-JS frontend. **Read its `CLAUDE.md` before writing Savrr's backend**; its
data model is the basis for this schema and its calculation/recurring code is the basis for
sub-project 2.

Savrr differs in being genuinely multi-user, mobile-first, and AI-assisted.

Things to carry over deliberately:

- `public/js/calc.js` — the pure calculation engine (frequency normalization, amortization, net
  worth, statements). Well tested; port rather than rewrite.
- `backend/recurring.py` — the auto-pay catch-up engine. **Port the fixed version.** It derives each
  installment due date from `start_date` by counting elapsed payments rather than walking the stored
  pointer forward, which prevents (a) a "31st of the month" schedule permanently drifting to the 28th
  after February, and (b) a drifted pointer letting a term post one payment more than it should.
- Its testing conventions — pinning env vars before app import so tests can never reach the real
  database.

Things deliberately **not** carried over (see the spec for why): float money columns, hand-written
cascade cleanup duplicated between client and server, vocabulary enforcement that exists only in
Pydantic, and the legacy `goals` table name for savings.

## Conventions

- **Categories are referenced by name (text)**, not by foreign key to `categories.id`. The
  `categories` table is a picklist, not a constraint — this keeps renames from cascading through the
  ledger, and matches financial-manager.
- **Migrations are SQL files in the repo**, applied with the Supabase CLI. Never create tables or
  policies by hand in the Supabase dashboard — dashboard-made objects aren't version-controlled,
  drift from the repo, and won't exist when the prod project is created.
- **RLS stays enabled on every table, always.** A `public` table with RLS off is readable and
  writable by anyone holding the `anon` key, which ships inside the mobile app. If a query returns
  zero rows unexpectedly, the cause is almost always a missing or wrong policy — the fix is a
  migration, never disabling RLS.
- Secrets live in a gitignored `.env`. Never commit or paste the database password, `service_role`
  key, or `anon` key.

## Planned layout

```
supabase/
  config.toml
  migrations/        0001_enums → 0005_seed_categories
  tests/             pgTAP: tenancy, cascades, constraints
docs/superpowers/specs/
```

## Status of setup (2026-09-21)

- Supabase CLI installed at `~/.supabase/bin/supabase` (via the official install script — the npm
  global package is deprecated and doesn't produce a working binary). `~/.bashrc` adds it to PATH;
  in a non-login shell use `export PATH="$HOME/.supabase/bin:$PATH"`.
- Logged in; repo is `supabase init`-ed and `supabase link`-ed to the hosted `savrr-dev` project
  (ref `myafgbejcqvitbosfcag`, us-west-2, Postgres 17). The link lives in `supabase/.temp/`
  (gitignored) — if `supabase db push` complains about no project ref, re-run
  `supabase link --project-ref myafgbejcqvitbosfcag`.
- `.env.example` lists the keys to fill into `.env`; nothing needs them until sub-project 2.
- The data-layer spec was **approved by the author on 2026-09-21**. Next step: turn it into an
  implementation plan (writing-plans skill), then implement.

## Environment notes

- This repo must stay on the Linux filesystem (`~/projects`). It was moved off `/mnt/e` (a 9p/drvfs
  Windows mount) on 2026-09-21 because `chmod` silently no-ops there, permissions are
  unrepresentable, line endings kept converting to CRLF, and I/O is slow. **Do not work from the
  `/mnt/e` copy.**
- Node 20, Python 3.13 available. **Docker is not installed** in this WSL distro — the Supabase
  local stack (`supabase start`) is deliberately not used; the CLI points at the hosted dev project
  via `supabase db push`.
- **iOS builds cannot run on Windows/WSL or in a Linux container** — they need macOS + Xcode. For
  sub-project 4, plan on Expo with EAS cloud builds, or Mac access.
