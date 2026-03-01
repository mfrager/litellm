#!/usr/bin/env python3
"""
Populate the router_model table from litellm_config.yaml and/or the LLM provider API.

Run from project root or dojo/scripts:
  python -m dojo.scripts.populate_models [options]
  python dojo/scripts.populate_models.py [options]

Loads .env from the project root (if present). Reads DATABASE_ASYNC_URL (or DATABASE_URL)
for the database connection.

Use --provider "<prefix>,<base_url>,<provider_url>" (repeatable). base_url is the
URL written into the generated config (api_base for completions; may include path, e.g. /v1).
provider_url is the model-list API base (for LLMProviderClient; host:port only, no path).
Merging is applied per combo in order.

Uses:
  - dojo.router.proxy_config.ProxyConfigManager to read/generate litellm_config.yaml
  - dojo.router.llm_provider.LLMProviderClient to list models from each provider URL
  - dojo.models.router_model.Model for DB writes
"""

from __future__ import annotations

import os
import re
import sys
import argparse
from pathlib import Path
from urllib.parse import urlparse

# Project root on sys.path so dojo is importable
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

# Load .env from project root so DATABASE_ASYNC_URL etc. are available
load_dotenv(str(_PROJECT_ROOT / ".env"))

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from dojo.models.router_model import Model
from dojo.router.llm_provider import LLMProviderClient, ProviderModel
from dojo.router.proxy_config import ProxyConfigManager, _normalize_api_key


def _sync_database_url() -> str:
    """Return sync database URL from env (DATABASE_ASYNC_URL or DATABASE_URL)."""
    url = os.environ.get("DATABASE_ASYNC_URL") or os.environ.get("DATABASE_URL", "")
    if not url:
        raise ValueError(
            "Set DATABASE_ASYNC_URL or DATABASE_URL to run populate_models"
        )
    # Convert async driver to sync for script
    if "mysql+aiomysql://" in url:
        url = url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
    elif "postgresql+asyncpg://" in url:
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    return url


# Model IDs starting with these stems are always local (lmstudio, lmstudio_z, ollama, etc.)
_LOCAL_PROVIDER_STEMS = ("lmstudio", "ollama")


def _is_local_provider_model_id(model_id: str) -> bool:
    """True if model_id is under a local provider prefix (e.g. lmstudio/, lmstudio_z/, ollama/)."""
    return any(model_id.startswith(stem) for stem in _LOCAL_PROVIDER_STEMS)


def _local_group_from_model_id(model_id: str) -> str:
    """
    Return model_group for a local provider model_id: 'local' or 'local_<suffix>'.
    E.g. 'lmstudio/foo' -> 'local'; 'lmstudio_z/foo' -> 'local_z'. Uses first path segment.
    """
    segment = model_id.split("/")[0] if "/" in model_id else model_id
    if "_" in segment:
        return "local_" + segment.split("_", 1)[1]
    return "local"


def _local_group_from_prefix(prefix: str) -> str:
    """Return model_group from prefix (e.g. 'lmstudio_z/' -> 'local_z')."""
    stem = prefix.rstrip("/")
    return _local_group_from_model_id(stem + "/x")


def _infer_group(api_base: str | None, provider_base: str = "") -> str:
    """Infer model_group: local if api_base points at provider/localhost, else remote."""
    if not api_base:
        return "remote"
    base = (api_base or "").rstrip("/").lower()
    if not base:
        return "remote"
    if provider_base:
        provider = provider_base.rstrip("/").lower()
        if provider in base:
            return "local"
    if "localhost" in base or "127.0.0.1" in base or "host.docker.internal" in base:
        return "local"
    return "remote"


def _parse_provider_spec(spec: str) -> tuple[str, str, str]:
    """
    Parse a provider spec into (prefix, provider_url, base_url).
    Spec format: "<prefix>,<base_url>,<provider_url>" with 1, 2, or 3 parts.
    base_url may include a path (e.g. .../v1); provider_url is host:port only (no path).
    - 3 parts: prefix, base_url (for model_list api_base), provider_url (for LLMProviderClient).
    - 2 parts: prefix, base_url; provider_url = base_url with any path stripped for API use.
    - 1 part: prefix; base_url and provider_url from LLM_PROVIDER_URL or http://localhost:8000.
    Prefix is normalized to end with / (e.g. lmstudio -> lmstudio/).
    """
    default_url = os.environ.get("LLM_PROVIDER_URL", "http://localhost:8000").rstrip("/")
    parts = [p.strip() for p in spec.split(",", 2)]
    if len(parts) == 3:
        prefix = parts[0]
        base_url = parts[1]  # may include path, do not strip
        provider_url = parts[2].rstrip("/")  # host:port only
    elif len(parts) == 2:
        prefix, base_url = parts[0], parts[1]
        p = urlparse(base_url)
        provider_url = f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else base_url.rstrip("/")
    else:
        prefix = parts[0] if parts else "lmstudio/"
        base_url = provider_url = default_url
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix, provider_url, base_url


def _trim_model_key(key: str) -> str:
    """Trim extra path segments for model_id; e.g. 'qwen/qwen3-14b' -> 'qwen3-14b'."""
    return key.split("/")[-1] if "/" in key else key


def _backend_model_from_api_key(key: str) -> str:
    """For API-retrieved models: use key as backend_model, with 'openai/' prefix if not present."""
    return key if key.startswith("openai/") else f"openai/{key}"


def _infer_tag(model_id: str, params_string: str | None) -> str:
    """Infer model_tag: code, large, or small."""
    combined = f"{model_id} {params_string or ''}".lower()
    if "code" in combined or "loco" in combined:
        return "code"
    if re.search(r"\d+\.?\d*b", combined) or "14b" in combined or "8b" in combined or "large" in combined:
        # Heuristic: 14B/8B -> large
        if re.search(r"1[4-9]b|[\d]{2,}b", combined):
            return "large"
    return "small"


def _build_models_from_config_only(config_models: list[dict]) -> list[dict]:
    """
    Build list of dicts from config model_list only (no provider API).
    Uses api_base for group inference (local if localhost etc).
    """
    seen = set()
    rows: list[dict] = []
    for entry in config_models:
        model_name = entry.get("model_name") or ""
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        params = entry.get("litellm_params") or {}
        api_base = params.get("api_base") or ""
        if isinstance(api_base, str) and api_base.startswith("os.environ/"):
            api_base = ""
        if _is_local_provider_model_id(model_name):
            group, tag = _local_group_from_model_id(model_name), "small"
        else:
            group = _infer_group(api_base, "")
            tag = "large" if group == "remote" else ("small" if group.startswith("local") else _infer_tag(model_name, None))
        backend_model = params.get("model") or None
        api_key_val = params.get("api_key")
        api_key_str = _normalize_api_key(str(api_key_val)) if api_key_val is not None else None
        drop_params = bool(params.get("drop_params", False))
        rows.append({
            "model_id": model_name,
            "model_group": group,
            "model_tag": tag,
            "default_context_length": 8192,
            "is_default": False,
            "priority": 1,
            "base_url": api_base or None,
            "backend_model": backend_model,
            "api_key": api_key_str,
            "drop_params": drop_params,
        })
    return rows


def _add_provider_models(
    rows: list[dict],
    prefix: str,
    provider_models: list[ProviderModel],
    base_url: str,
) -> None:
    """
    Append provider-only model rows with the given prefix and base_url.
    base_url is the URL used in the generated config (api_base for completions; may include path).
    Mutates rows in place.
    """
    seen = {r["model_id"] for r in rows}
    p = prefix.rstrip("/")
    for pm in provider_models:
        if not pm.is_llm:
            continue
        trimmed = _trim_model_key(pm.key)
        model_id = f"{p}/{trimmed}"
        if model_id in seen:
            continue
        seen.add(model_id)
        rows.append({
            "model_id": model_id,
            "model_group": _local_group_from_prefix(prefix),
            "model_tag": "small",
            "default_context_length": 8192,
            "is_default": False,
            "priority": 1,
            "base_url": base_url or None,
            "backend_model": _backend_model_from_api_key(pm.key),
            "api_key": "none",
            "drop_params": False,
        })


def _build_models_from_config_and_provider(
    config_models: list[dict],
    provider_models: list[ProviderModel],
    provider_base: str,
    local_prefix: str = "lmstudio",
) -> list[dict]:
    """
    Build list of dicts suitable for Model table (config + one provider).
    Kept for compatibility; prefer _build_models_from_config_only + _add_provider_models per combo.
    """
    seen = set()
    rows: list[dict] = []
    provider_by_suffix: dict[str, ProviderModel] = {}
    for m in provider_models:
        for part in (m.key, m.key.split("/")[-1], m.key.split("/")[0]):
            if part and part not in provider_by_suffix:
                provider_by_suffix[part] = m

    for entry in config_models:
        model_name = entry.get("model_name") or ""
        if not model_name or model_name in seen:
            continue
        seen.add(model_name)
        params = entry.get("litellm_params") or {}
        api_base = params.get("api_base") or ""
        if isinstance(api_base, str) and api_base.startswith("os.environ/"):
            api_base = ""
        if _is_local_provider_model_id(model_name):
            group, tag = _local_group_from_model_id(model_name), "small"
        else:
            group = _infer_group(api_base, provider_base)
            tag = "large" if group == "remote" else ("small" if group.startswith("local") else _infer_tag(model_name, None))
        default_context_length = 8192
        backend_model = params.get("model") or None
        api_key_val = params.get("api_key")
        # Store without surrounding " so YAML can add them on output
        api_key_str = _normalize_api_key(str(api_key_val)) if api_key_val is not None else None
        drop_params = bool(params.get("drop_params", False))
        rows.append({
            "model_id": model_name,
            "model_group": group,
            "model_tag": tag,
            "default_context_length": default_context_length,
            "is_default": False,
            "priority": 1,
            "base_url": api_base or None,
            "backend_model": backend_model,
            "api_key": api_key_str,
            "drop_params": drop_params,
        })

    # Add provider-only LLM models (not in config) as local/small
    for pm in provider_models:
        if not pm.is_llm:
            continue
        trimmed = _trim_model_key(pm.key)
        candidate_id = f"{local_prefix}/{trimmed}"
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        rows.append({
            "model_id": candidate_id,
            "model_group": _local_group_from_prefix(local_prefix + "/"),
            "model_tag": "small",
            "default_context_length": 8192,
            "is_default": False,
            "priority": 1,
            "base_url": None,
            "backend_model": _backend_model_from_api_key(pm.key),
            "api_key": "none",
            "drop_params": False,
        })

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Populate router_model table from config and/or LLM provider API"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to litellm_config.yaml (default: project root / litellm_config.yaml)",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=None,
        help="Sync database URL (default: from DATABASE_ASYNC_URL / DATABASE_URL)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        action="append",
        default=None,
        metavar="PREFIX,BASE_URL,PROVIDER_URL",
        help=(
            "Provider combo: prefix for model names, base_url for config (may include path), provider URL for model-list API (no path). "
            "Format: <prefix>,<base_url>,<provider_url>. "
            "1–3 parts allowed; omit trailing parts to use defaults. "
            "E.g. --provider 'lmstudio/,http://host.docker.internal:8000/v1,http://localhost:8000'."
        ),
    )
    parser.add_argument(
        "--generate-config",
        action="store_true",
        help="Generate litellm_config.yaml from template (other top-level items) before reading",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=None,
        help="Template path for --generate-config (optional)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written, do not change DB",
    )
    parser.add_argument(
        "--write-config",
        action="store_true",
        help="After DB upsert, write final litellm_config.yaml from base + prefix (lmstudio/) from DB and API",
    )
    parser.add_argument(
        "--base-config",
        type=Path,
        default=None,
        help="Path to base YAML (default: litellm_config_base.yaml); non-prefix model_list + litellm_settings, general_settings",
    )
    args = parser.parse_args()

    # Parse provider specs: "<prefix>,<base_url>,<provider_url>" (1–3 parts), zero or more
    provider_specs: list[tuple[str, str, str]] = []
    if args.provider:
        for spec in args.provider:
            provider_specs.append(_parse_provider_spec(spec))

    # 1) Proxy config: base YAML and optional generate
    base_config_path = args.base_config or _PROJECT_ROOT / "litellm_config_base.yaml"
    output_config_path = args.config or _PROJECT_ROOT / "litellm_config.yaml"
    proxy_config = ProxyConfigManager(base_config_path=base_config_path, output_config_path=output_config_path)
    if args.generate_config:
        proxy_config.generate_from_template(
            template_path=args.template,
            output_path=output_config_path,
        )
        print(f"Generated config at {output_config_path}")
    # Load model_list from base (or full config if base missing) for populating DB
    config_models = proxy_config.get_model_list(base_config_path if base_config_path.exists() else output_config_path)
    print(f"Loaded {len(config_models)} models from config")

    # 2) Build rows from config, then merge each provider combo one by one
    rows = _build_models_from_config_only(config_models)
    provider_models_by_prefix: dict[str, list[ProviderModel]] = {}
    for prefix, provider_url, base_url in provider_specs:
        try:
            client = LLMProviderClient(base_url=provider_url)
            provider_models = client.list_models(type_filter="llm")
            provider_models_by_prefix[prefix] = provider_models
            _add_provider_models(rows, prefix, provider_models, base_url)
            print(f"Loaded {len(provider_models)} LLM models from {provider_url} (prefix {prefix!r}, base_url {base_url})")
        except Exception as e:
            print(f"Provider at {provider_url} not available ({e}); skipping prefix {prefix!r}")
            provider_models_by_prefix[prefix] = []
    print(f"Merged {len(rows)} model rows to upsert")

    if args.dry_run:
        for r in rows:
            print(f"  {r['model_id']} group={r['model_group']} tag={r['model_tag']} ctx={r['default_context_length']}")
        return 0

    # 4) DB upsert
    db_url = args.database_url or _sync_database_url()
    engine = create_engine(db_url, echo=False)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        for r in rows:
            existing = session.execute(
                select(Model).where(Model.model_id == r["model_id"])
            ).scalar_one_or_none()
            if existing:
                # Ensure rows under a local provider prefix get model_group with suffix and tag "small"
                if _is_local_provider_model_id(str(existing.model_id)):
                    group_val = _local_group_from_model_id(str(existing.model_id))
                    existing.model_group = group_val  # type: ignore[assignment]
                    existing.model_tag = "small"  # type: ignore[assignment]
                    print(f"  Set group={group_val}, tag=small (exists) {r['model_id']}")
                else:
                    print(f"  Skipped (exists) {r['model_id']}")
            else:
                session.add(
                    Model(
                        model_id=r["model_id"],  # type: ignore[reportAttributeIssue]
                        model_group=r["model_group"],  # type: ignore[reportAttributeIssue]
                        model_tag=r["model_tag"],  # type: ignore[reportAttributeIssue]
                        default_context_length=r["default_context_length"],  # type: ignore[reportAttributeIssue]
                        is_default=r["is_default"],  # type: ignore[reportAttributeIssue]
                        priority=r["priority"],  # type: ignore[reportAttributeIssue]
                        is_active=True,  # type: ignore[reportAttributeIssue]
                        base_url=r.get("base_url"),  # type: ignore[reportAttributeIssue]
                        backend_model=r.get("backend_model"),  # type: ignore[reportAttributeIssue]
                        api_key=r.get("api_key"),  # type: ignore[reportAttributeIssue]
                        drop_params=r.get("drop_params", False),  # type: ignore[reportAttributeIssue]
                    )
                )
                print(f"  Inserted {r['model_id']}")
        session.commit()

        # 5) Optional: write final litellm_config.yaml from base + all prefix entries (DB + API per combo)
        if args.write_config:
            base_path = base_config_path if base_config_path.exists() else output_config_path
            base_data = proxy_config.load_base(base_path)
            if provider_specs:
                all_prefixes = [p[0] for p in provider_specs]
                base_model_list = [
                    m for m in base_data.get("model_list", [])
                    if not any((m.get("model_name") or "").startswith(prefix) for prefix in all_prefixes)
                ]
                final_model_list = list(base_model_list)
                for prefix, _provider_url, base_url in provider_specs:
                    db_prefix_models = session.execute(
                        select(Model).where(
                            Model.model_id.startswith(prefix),  # type: ignore[arg-type]
                            Model.is_active == True,
                        )
                    ).scalars().all()
                    api_models = provider_models_by_prefix.get(prefix, [])
                    default_base = base_url if base_url.startswith("http") else "http://localhost:8000"
                    entries = proxy_config.build_final_model_list(
                        prefix=prefix,
                        base_model_list=[],
                        db_models=db_prefix_models,
                        api_models=api_models,
                        default_base_url=default_base,
                        default_api_key="none",
                    )
                    final_model_list.extend(entries)
                model_list = final_model_list
            else:
                model_list = base_data.get("model_list", [])
            proxy_config.write_config_with_model_list(
                output_path=output_config_path,
                base_data=base_data,
                model_list=model_list,
            )
            print(f"Wrote final config to {output_config_path}")
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
