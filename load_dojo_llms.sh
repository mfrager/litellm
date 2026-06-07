#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [[ -f .venv/bin/activate ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

#PROVIDER_LMSTUDIO="lmstudio/,http://host.docker.internal:8000/v1,http://localhost:8000"
PROVIDER_LMSTUDIO_Z="lmstudio_z/,http://zincbook.local:8000/v1,http://zincbook.local:8000"

python -m dojo.scripts.populate_models \
  --provider "$PROVIDER_LMSTUDIO_Z" \
  --purge-remote-missing-from-config \
  --purge-local-missing-from-provider \
  --write-config

