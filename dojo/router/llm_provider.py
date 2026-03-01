"""
LLM Provider Client

Provides functions to list, get, suggest, and load models from a local
LM Studio-compatible provider via its REST API.
"""

import os
import logging
from typing import Any, Dict, List, Optional

import requests

__all__ = [
    "LLMProviderClient",
    "ProviderModel",
    "LoadedInstance",
    "LoadResult",
    "list_models",
    "get_model",
    "suggest_model",
    "load_model",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes (plain Python – no external deps beyond stdlib)
# ---------------------------------------------------------------------------

class LoadedInstance:
    """A currently-loaded instance of a model."""

    def __init__(self, id: str, config: Dict[str, Any]) -> None:
        self.id = id
        self.config = config  # e.g. {"context_length": 8192}

    def __repr__(self) -> str:
        return f"LoadedInstance(id={self.id!r}, config={self.config})"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LoadedInstance":
        return cls(id=d.get("id", ""), config=d.get("config", {}))


class ProviderModel:
    """Metadata for a single model returned by the provider."""

    def __init__(
        self,
        *,
        type: str,
        key: str,
        display_name: str,
        publisher: str = "",
        architecture: Optional[str] = None,
        quantization: Optional[Dict[str, Any]] = None,
        size_bytes: int = 0,
        params_string: Optional[str] = None,
        loaded_instances: Optional[List[LoadedInstance]] = None,
        max_context_length: int = 0,
        format: Optional[str] = None,
        capabilities: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        variants: Optional[List[str]] = None,
        selected_variant: Optional[str] = None,
    ) -> None:
        self.type = type
        self.key = key
        self.display_name = display_name
        self.publisher = publisher
        self.architecture = architecture
        self.quantization = quantization or {}
        self.size_bytes = size_bytes
        self.params_string = params_string
        self.loaded_instances: List[LoadedInstance] = loaded_instances or []
        self.max_context_length = max_context_length
        self.format = format
        self.capabilities = capabilities or {}
        self.description = description
        self.variants = variants or []
        self.selected_variant = selected_variant

    @property
    def is_loaded(self) -> bool:
        """True when at least one instance of this model is currently loaded."""
        return bool(self.loaded_instances)

    @property
    def is_llm(self) -> bool:
        return self.type == "llm"

    @property
    def supports_tool_use(self) -> bool:
        return bool(self.capabilities.get("trained_for_tool_use", False))

    @property
    def bits_per_weight(self) -> Optional[int]:
        return self.quantization.get("bits_per_weight") if self.quantization else None

    def __repr__(self) -> str:
        loaded = " [loaded]" if self.is_loaded else ""
        return (
            f"ProviderModel(key={self.key!r}, display={self.display_name!r},"
            f" params={self.params_string!r}{loaded})"
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ProviderModel":
        raw_instances = d.get("loaded_instances") or []
        instances = [LoadedInstance.from_dict(i) for i in raw_instances]
        return cls(
            type=d.get("type", ""),
            key=d.get("key", ""),
            display_name=d.get("display_name", ""),
            publisher=d.get("publisher", ""),
            architecture=d.get("architecture"),
            quantization=d.get("quantization"),
            size_bytes=d.get("size_bytes", 0),
            params_string=d.get("params_string"),
            loaded_instances=instances,
            max_context_length=d.get("max_context_length", 0),
            format=d.get("format"),
            capabilities=d.get("capabilities"),
            description=d.get("description"),
            variants=d.get("variants"),
            selected_variant=d.get("selected_variant"),
        )


class LoadResult:
    """Result returned after requesting a model load."""

    def __init__(
        self,
        *,
        type: str,
        instance_id: str,
        load_time_seconds: float,
        status: str,
    ) -> None:
        self.type = type
        self.instance_id = instance_id
        self.load_time_seconds = load_time_seconds
        self.status = status

    def __repr__(self) -> str:
        return (
            f"LoadResult(instance_id={self.instance_id!r},"
            f" status={self.status!r}, load_time={self.load_time_seconds:.2f}s)"
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LoadResult":
        return cls(
            type=d.get("type", ""),
            instance_id=d.get("instance_id", ""),
            load_time_seconds=float(d.get("load_time_seconds", 0.0)),
            status=d.get("status", ""),
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class LLMProviderClient:
    """
    Thin HTTP client for a local LM Studio-compatible provider.

    The base URL is read from the environment variable ``LLM_PROVIDER_URL``
    (default: ``http://localhost:8000``).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = (
            (base_url or os.environ.get("LLM_PROVIDER_URL", "http://localhost:8000"))
            .rstrip("/")
        )
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _get(self, path: str) -> Any:
        url = f"{self.base_url}{path}"
        response = self._session.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        response = self._session.post(url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_models(self, *, type_filter: Optional[str] = None) -> List[ProviderModel]:
        """
        Return all models available on the provider.

        Args:
            type_filter: Optional ``"llm"`` or ``"embedding"`` to narrow results.

        Returns:
            List of :class:`ProviderModel` objects.
        """
        data = self._get("/api/v1/models")
        models = [ProviderModel.from_dict(m) for m in data.get("models", [])]
        if type_filter:
            models = [m for m in models if m.type == type_filter]
        return models

    def get_model(self, key: str) -> Optional[ProviderModel]:
        """
        Return the :class:`ProviderModel` whose ``key`` matches *key*, or
        ``None`` if no such model exists on the provider.

        Args:
            key: The model key as returned by the provider (e.g.
                 ``"lfm2.5-1.2b-instruct-mlx"``).
        """
        models = self.list_models()
        for m in models:
            if m.key == key:
                return m
        return None

    def suggest_model(
        self,
        *,
        prefer_loaded: bool = True,
        max_size_gb: Optional[float] = None,
        min_context_length: Optional[int] = None,
        requires_tool_use: bool = False,
        type_filter: str = "llm",
    ) -> Optional[ProviderModel]:
        """
        Suggest the best available model according to the given criteria.

        Selection priority:
        1. Loaded models are preferred when *prefer_loaded* is ``True``.
        2. Larger context windows are preferred.
        3. Models that support tool use are preferred when required.

        Args:
            prefer_loaded:       Prefer models that are already loaded.
            max_size_gb:         Skip models whose ``size_bytes`` exceeds this many GB.
            min_context_length:  Skip models whose ``max_context_length`` is below this.
            requires_tool_use:   Only return models that advertise tool-use support.
            type_filter:         ``"llm"`` (default) or ``"embedding"``.

        Returns:
            The best matching :class:`ProviderModel`, or ``None`` if none qualifies.
        """
        candidates = self.list_models(type_filter=type_filter)

        # Apply hard filters
        if max_size_gb is not None:
            max_bytes = int(max_size_gb * 1_073_741_824)
            candidates = [m for m in candidates if m.size_bytes <= max_bytes]

        if min_context_length is not None:
            candidates = [
                m for m in candidates if m.max_context_length >= min_context_length
            ]

        if requires_tool_use:
            candidates = [m for m in candidates if m.supports_tool_use]

        if not candidates:
            return None

        def _score(m: ProviderModel) -> tuple:
            loaded_score = 1 if (prefer_loaded and m.is_loaded) else 0
            tool_score = 1 if m.supports_tool_use else 0
            return (loaded_score, tool_score, m.max_context_length)

        candidates.sort(key=_score, reverse=True)
        return candidates[0]

    def load_model(
        self,
        key: str,
        *,
        context_length: Optional[int] = None,
        load_if_needed: bool = True,
    ) -> LoadResult:
        """
        Load a model instance on the provider.

        If *load_if_needed* is ``False`` and the model is already loaded,
        this method still calls the provider's load endpoint (idempotent for
        most providers).

        Args:
            key:              The model key (e.g. ``"lfm2.5-1.2b-instruct-mlx"``).
            context_length:   Optional context length to configure for the instance.
            load_if_needed:   If ``True`` (default) and the model is already loaded,
                              skip the API call and return a synthetic result.

        Returns:
            :class:`LoadResult` describing the outcome.
        """
        if load_if_needed:
            model = self.get_model(key)
            if model and model.is_loaded:
                instance_id = model.loaded_instances[0].id
                logger.info("Model %r is already loaded as %r", key, instance_id)
                return LoadResult(
                    type=model.type,
                    instance_id=instance_id,
                    load_time_seconds=0.0,
                    status="already_loaded",
                )

        payload: Dict[str, Any] = {"model": key}
        if context_length is not None:
            payload["context_length"] = context_length

        logger.info("Loading model %r with context_length=%s …", key, context_length)
        data = self._post("/api/v1/models/load", payload)
        return LoadResult.from_dict(data)

    def ensure_model_loaded(
        self,
        key: str,
        *,
        context_length: Optional[int] = None,
    ) -> LoadResult:
        """
        Convenience wrapper: load *key* only when it is not already running.

        Returns a :class:`LoadResult` in both cases.
        """
        return self.load_model(key, context_length=context_length, load_if_needed=True)


# ---------------------------------------------------------------------------
# Module-level convenience functions (use a default client instance)
# ---------------------------------------------------------------------------

def _default_client() -> LLMProviderClient:
    return LLMProviderClient()


def list_models(*, type_filter: Optional[str] = None) -> List[ProviderModel]:
    """List all models from the default provider. See :meth:`LLMProviderClient.list_models`."""
    return _default_client().list_models(type_filter=type_filter)


def get_model(key: str) -> Optional[ProviderModel]:
    """Look up a single model by key. See :meth:`LLMProviderClient.get_model`."""
    return _default_client().get_model(key)


def suggest_model(
    *,
    prefer_loaded: bool = True,
    max_size_gb: Optional[float] = None,
    min_context_length: Optional[int] = None,
    requires_tool_use: bool = False,
    type_filter: str = "llm",
) -> Optional[ProviderModel]:
    """Suggest the best available model. See :meth:`LLMProviderClient.suggest_model`."""
    return _default_client().suggest_model(
        prefer_loaded=prefer_loaded,
        max_size_gb=max_size_gb,
        min_context_length=min_context_length,
        requires_tool_use=requires_tool_use,
        type_filter=type_filter,
    )


def load_model(
    key: str,
    *,
    context_length: Optional[int] = None,
    load_if_needed: bool = True,
) -> LoadResult:
    """Load a model on the default provider. See :meth:`LLMProviderClient.load_model`."""
    return _default_client().load_model(
        key, context_length=context_length, load_if_needed=load_if_needed
    )
