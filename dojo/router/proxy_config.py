"""
Proxy config management for LiteLLM proxy (litellm_config.yaml).

Uses a base YAML file for structure and non-prefix model_list entries.
Prefix model_list entries (e.g. "lmstudio/") are rebuilt from the database
and/or the model list API. Final config = base + rebuilt prefix entries.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["ProxyConfigManager", "QuotedStr"]

# Optional YAML; fail at runtime if not installed when load/write is used
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


def _project_root() -> Path:
    """Resolve project root (directory containing litellm_config.yaml or dojo)."""
    for start in (Path(__file__).resolve(), Path.cwd()):
        root = start
        for _ in range(10):
            if (root / "litellm_config.yaml").exists() or (root / "dojo").is_dir():
                return root
            parent = root.parent
            if parent == root:
                break
            root = parent
    return Path.cwd()


class QuotedStr(str):
    """String that is emitted with double quotes in YAML (e.g. for api_key)."""

    pass


def _quoted_str_representer(dumper: Any, data: QuotedStr) -> Any:
    return dumper.represent_scalar("tag:yaml.org,2002:str", str(data), style='"')


def _normalize_api_key(value: Optional[str]) -> Optional[str]:
    """Remove surrounding double quotes so we never store them in DB; YAML output adds them via QuotedStr."""
    if value is None:
        return None
    s = value.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s if s else None


class ProxyConfigManager:
    """
    Manages LiteLLM proxy config from a base YAML and DB/API-built model list.

    - Base YAML: contains litellm_settings, general_settings, and model_list
      with entries that do NOT use the configured prefix (e.g. gemini/, cerebras/).
    - Prefix entries (e.g. "lmstudio/"): rebuilt from the Model table and/or
      the model list API; each has model_name, litellm_params (model, api_base, api_key).
    - api_key in output is always emitted as a quoted YAML string.
    """

    def __init__(
        self,
        base_config_path: Optional[Path] = None,
        output_config_path: Optional[Path] = None,
    ) -> None:
        root = _project_root()
        self.base_config_path = Path(base_config_path) if base_config_path else root / "litellm_config_base.yaml"
        self.output_config_path = Path(output_config_path) if output_config_path else root / "litellm_config.yaml"

    def load_base(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Load the base YAML config (model_list here may include only non-prefix entries,
        or the file may be the full config; we filter by prefix when building final).
        """
        if yaml is None:
            raise RuntimeError("PyYAML is required; install with: pip install pyyaml")
        p = Path(path) if path else self.base_config_path
        if not p.exists():
            return {
                "model_list": [],
                "litellm_settings": {},
                "general_settings": {},
            }
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {
            "model_list": data.get("model_list", []),
            "litellm_settings": data.get("litellm_settings", {}),
            "general_settings": data.get("general_settings", {}),
            **{k: v for k, v in data.items() if k not in ("model_list", "litellm_settings", "general_settings")},
        }

    def load(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """Load config from a single file (backward compat). Prefer load_base + build_final_config."""
        p = Path(path) if path else self.output_config_path
        return self.load_base(p)

    def get_model_list(self, path: Optional[Path] = None) -> List[Dict[str, Any]]:
        """Return model_list from base or given path."""
        return self.load_base(path).get("model_list", [])

    def get_base_model_list_excluding_prefix(
        self,
        base_data: Optional[Dict[str, Any]] = None,
        prefix: str = "lmstudio/",
    ) -> List[Dict[str, Any]]:
        """Return model_list entries whose model_name does NOT start with prefix."""
        data = base_data if base_data is not None else self.load_base()
        return [
            m for m in data.get("model_list", [])
            if not (m.get("model_name") or "").startswith(prefix)
        ]

    @staticmethod
    def _model_list_entry_for_prefix_row(
        model_id: str,
        base_url: Optional[str],
        backend_model: Optional[str],
        api_key: Optional[str],
        drop_params: bool,
        prefix: str,
    ) -> Dict[str, Any]:
        """Build one model_list entry from a DB row (prefix entry). api_key emitted quoted."""
        params: Dict[str, Any] = {
            "model": backend_model or model_id,
        }
        if base_url:
            params["api_base"] = base_url
        if drop_params:
            params["drop_params"] = True
        # Emit api_key with quotes in YAML; value from DB must not include the quote characters
        raw = _normalize_api_key(api_key) if api_key else "none"
        params["api_key"] = QuotedStr(raw)
        return {
            "model_name": model_id,
            "litellm_params": params,
        }

    def build_final_model_list(
        self,
        prefix: str,
        base_model_list: Optional[List[Dict[str, Any]]] = None,
        db_models: Optional[Sequence[Any]] = None,
        api_models: Optional[Sequence[Any]] = None,
        default_base_url: Optional[str] = None,
        default_api_key: str = "none",
    ) -> List[Dict[str, Any]]:
        """
        Build the final model_list: base entries (no prefix) + prefix entries from DB and/or API.

        db_models: iterable of objects with model_id, base_url, backend_model, api_key
          (e.g. Model ORM rows or dicts with those keys).
        api_models: iterable of provider model objects with .key (and optionally .max_context_length);
          used to add prefix entries that are in the API list but not in DB (with defaults).
        """
        result: List[Dict[str, Any]] = list(base_model_list or [])
        seen_prefix_ids: set[str] = set()

        def add_entry(
            model_id: str,
            base_url: Optional[str],
            backend_model: Optional[str],
            api_key: Optional[str],
            drop_params: bool = False,
        ) -> None:
            if model_id in seen_prefix_ids:
                return
            seen_prefix_ids.add(model_id)
            result.append(
                self._model_list_entry_for_prefix_row(
                    model_id,
                    base_url or default_base_url,
                    backend_model,
                    api_key or default_api_key,
                    drop_params,
                    prefix,
                )
            )

        # Add from DB first (so DB backs prefix entries)
        if db_models:
            for row in db_models:
                if getattr(row, "model_id", None) and (getattr(row, "model_id", "") or "").startswith(prefix):
                    add_entry(
                        getattr(row, "model_id"),
                        getattr(row, "base_url", None),
                        getattr(row, "backend_model", None),
                        getattr(row, "api_key", None),
                        bool(getattr(row, "drop_params", False)),
                    )

        # Optionally add from API any prefix key not yet added; trim key for model_id, use original for backend_model
        if api_models and default_base_url:
            p = prefix.rstrip("/")
            for pm in api_models:
                key = getattr(pm, "key", None) or ""
                if not key:
                    continue
                trimmed = key.split("/")[-1] if "/" in key else key
                model_id = key if key.startswith(prefix) else f"{p}/{trimmed}"
                if not model_id.startswith(prefix):
                    continue
                if model_id in seen_prefix_ids:
                    continue
                backend_model = key if key.startswith("openai/") else f"openai/{key}"
                add_entry(model_id, default_base_url, backend_model, default_api_key, False)

        return result

    def build_final_config(
        self,
        output_path: Optional[Path] = None,
        base_path: Optional[Path] = None,
        prefix: str = "lmstudio/",
        db_models: Optional[Sequence[Any]] = None,
        api_models: Optional[Sequence[Any]] = None,
        default_base_url: Optional[str] = None,
        default_api_key: str = "none",
    ) -> Path:
        """
        Write the final litellm_config.yaml: base YAML with model_list replaced by
        base (non-prefix) entries + prefix entries rebuilt from db_models and/or api_models.
        """
        if yaml is None:
            raise RuntimeError("PyYAML is required; install with: pip install pyyaml")
        yaml.add_representer(QuotedStr, _quoted_str_representer)
        out = Path(output_path) if output_path else self.output_config_path
        base_data = self.load_base(base_path or self.base_config_path)
        base_model_list = self.get_base_model_list_excluding_prefix(base_data, prefix=prefix)
        final_model_list = self.build_final_model_list(
            prefix=prefix,
            base_model_list=base_model_list,
            db_models=db_models,
            api_models=api_models,
            default_base_url=default_base_url,
            default_api_key=default_api_key,
        )
        payload = {
            **{k: v for k, v in base_data.items() if k != "model_list"},
            "model_list": final_model_list,
        }
        with open(out, "w", encoding="utf-8") as f:
            yaml.dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return out

    def write_config_with_model_list(
        self,
        output_path: Optional[Path] = None,
        base_data: Optional[Dict[str, Any]] = None,
        model_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Path:
        """
        Write config YAML from base_data with the given model_list (e.g. built from
        multiple provider combos). Registers QuotedStr for api_key quoting.
        """
        if yaml is None:
            raise RuntimeError("PyYAML is required; install with: pip install pyyaml")
        yaml.add_representer(QuotedStr, _quoted_str_representer)
        out = Path(output_path) if output_path else self.output_config_path
        data = base_data if base_data is not None else self.load_base()
        final_list = model_list if model_list is not None else data.get("model_list", [])
        payload = {
            **{k: v for k, v in data.items() if k != "model_list"},
            "model_list": final_list,
        }
        with open(out, "w", encoding="utf-8") as f:
            yaml.dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return out

    def generate_from_template(
        self,
        template_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
        model_list_override: Optional[List[Dict[str, Any]]] = None,
        litellm_settings_override: Optional[Dict[str, Any]] = None,
        general_settings_override: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """
        Generate config file from a template (legacy). Prefer build_final_config for
        base + DB/API-driven model list.
        """
        if yaml is None:
            raise RuntimeError("PyYAML is required; install with: pip install pyyaml")
        out = Path(output_path) if output_path else self.output_config_path
        loaded = self.load_base(self.base_config_path) if self.base_config_path.exists() else self.load_base()
        model_list = model_list_override if model_list_override is not None else loaded.get("model_list", [])
        litellm_settings = litellm_settings_override if litellm_settings_override is not None else loaded.get("litellm_settings", {})
        general_settings = general_settings_override if general_settings_override is not None else loaded.get("general_settings", {})

        if template_path and Path(template_path).exists():
            with open(template_path, "r", encoding="utf-8") as f:
                content = f.read()
            content = content.replace("{{ model_list }}", yaml.dump(model_list, default_flow_style=False, allow_unicode=True, sort_keys=False))
            content = content.replace("{{ litellm_settings }}", yaml.dump(litellm_settings, default_flow_style=False, allow_unicode=True, sort_keys=False))
            content = content.replace("{{ general_settings }}", yaml.dump(general_settings, default_flow_style=False, allow_unicode=True, sort_keys=False))
            out.write_text(content, encoding="utf-8")
        else:
            payload = {
                "model_list": model_list,
                "litellm_settings": litellm_settings,
                "general_settings": general_settings,
            }
            with open(out, "w", encoding="utf-8") as f:
                yaml.dump(payload, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return out
