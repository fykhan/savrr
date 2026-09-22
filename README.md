# savrr

Personal finance app: Supabase (Postgres + Auth) → FastAPI → React Native.

## Sub-project 1: data layer

Schema, RLS, signup trigger and seed categories live in `supabase/migrations/`
and are applied to the hosted `savrr-dev` project with the Supabase CLI. There
is no local Docker stack, and `supabase test db` (which needs Docker to run
`pg_prove`) doesn't work in this environment — `scripts/pgtap.py` runs the
same `supabase/tests/*.sql` files directly over a `psycopg` connection
instead.

```sh
export PATH="$HOME/.supabase/bin:$PATH"
cp .env.example .env            # fill in keys + db password (never commit)
set -a; source .env; set +a

supabase link --project-ref myafgbejcqvitbosfcag
supabase db push --linked       # apply migrations

python3 -m venv .venv && .venv/bin/pip install "psycopg[binary]"
.venv/bin/python scripts/pgtap.py   # pgTAP: tenancy, cascades, constraints
```

Design: `docs/superpowers/specs/2026-09-21-data-layer-design.md`
Plan: `docs/superpowers/plans/2026-09-21-data-layer.md`
