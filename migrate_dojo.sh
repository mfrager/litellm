#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

ALEMBIC_INI="dojo/migrations/alembic.ini"
VERSIONS_DIR="dojo/migrations/versions"
CMD="${1:-upgrade}"
shift || true

_count_revisions() {
  local files=()
  shopt -s nullglob
  files=( "$ROOT/$VERSIONS_DIR"/*.py )
  shopt -u nullglob
  echo "${#files[@]}"
}

_repair_orphan_alembic_version() {
  if alembic -c "$ALEMBIC_INI" current >/dev/null 2>&1; then
    return 0
  fi

  echo "Repairing orphaned alembic_version (missing local revision files)..." >&2
  python - <<'PY'
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(".") / ".env")

url = os.environ.get("DATABASE_URL") or os.environ.get("DATABASE_ASYNC_URL", "")
if not url:
    raise SystemExit("Set DATABASE_URL or DATABASE_ASYNC_URL before running migrations")

for async_prefix, sync_prefix in (
    ("mysql+aiomysql", "mysql+pymysql"),
    ("sqlite+aiosqlite", "sqlite"),
):
    if url.startswith(async_prefix):
        url = sync_prefix + url[len(async_prefix):]
        break

engine = create_engine(url)
with engine.begin() as conn:
    conn.execute(text("DELETE FROM alembic_version"))
print("Cleared alembic_version")
PY
}

_bootstrap_revisions_if_needed() {
  if [[ "$(_count_revisions)" -gt 0 ]]; then
    return 0
  fi

  echo "No local migration revisions found; autogenerating baseline..." >&2
  alembic -c "$ALEMBIC_INI" revision --autogenerate -m "baseline"
}

_prepare_upgrade() {
  _bootstrap_revisions_if_needed
  _repair_orphan_alembic_version
}

case "$CMD" in
  upgrade)
    _prepare_upgrade
    exec alembic -c "$ALEMBIC_INI" upgrade "${1:-head}"
    ;;
  revision)
    exec alembic -c "$ALEMBIC_INI" revision --autogenerate "$@"
    ;;
  repair)
    _repair_orphan_alembic_version
    ;;
  bootstrap)
    _bootstrap_revisions_if_needed
    ;;
  *)
    exec alembic -c "$ALEMBIC_INI" "$CMD" "$@"
    ;;
esac
