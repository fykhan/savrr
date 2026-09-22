"""Run pgTAP test files against the linked Supabase project, no Docker needed.

`supabase test db --linked` shells out to pg_prove inside a container, which
this WSL distro can't run. This does the same job: each file is executed
statement-by-statement on a session-mode connection, TAP lines are printed as
they come back, and the exit code is non-zero if anything failed.

    ./.venv/bin/python scripts/pgtap.py                 # all of supabase/tests/
    ./.venv/bin/python scripts/pgtap.py supabase/tests/tenancy_test.sql
"""
import os
import re
import sys
from pathlib import Path

import psycopg

REF = "myafgbejcqvitbosfcag"
# session pooler (port 5432), not transaction pooler: the tests rely on
# `set local role` and `set_config(..., true)` staying on one backend.
DSN = (
    f"host=aws-0-us-west-2.pooler.supabase.com port=5432 dbname=postgres "
    f"user=postgres.{REF} password={os.environ['SUPABASE_DB_PASSWORD']}"
)


def statements(sql: str):
    """Split on ';' at end of line, but not inside $$ ... $$ bodies."""
    buf, in_dollar = [], False
    for line in sql.splitlines():
        if line.count("$$") % 2:
            in_dollar = not in_dollar
        buf.append(line)
        if not in_dollar and line.rstrip().endswith(";"):
            stmt = "\n".join(buf).strip()
            buf = []
            if stmt and not stmt.startswith("--"):
                yield stmt
    if "".join(buf).strip():
        yield "\n".join(buf)


def run_file(path: Path) -> bool:
    print(f"\n# {path}")
    failed = 0
    with psycopg.connect(DSN, autocommit=True) as conn, conn.cursor() as cur:
        for stmt in statements(path.read_text()):
            try:
                cur.execute(stmt)
            except psycopg.Error as e:
                print(f"not ok - statement raised {e.sqlstate}: {e}\n  {stmt[:200]}")
                failed += 1
                try:
                    cur.execute("rollback")
                except psycopg.Error:
                    pass
                break
            if cur.description:
                for (line,) in cur.fetchall():
                    if line is None:
                        continue
                    print(line)
                    if re.match(r"^not ok\b", line) or line.startswith("# Looks like you failed"):
                        failed += 1
    return failed == 0


def main(argv):
    targets = [Path(a) for a in argv] or [Path("supabase/tests")]
    files = sorted(f for t in targets for f in (t.glob("*_test.sql") if t.is_dir() else [t]))
    results = {f: run_file(f) for f in files}
    print()
    for f, ok in results.items():
        print(f"{'ok  ' if ok else 'FAIL'} {f}")
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main(sys.argv[1:])
