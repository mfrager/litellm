import asyncio
import os
import sys
import logging
import litellm
from ulid import ULID
from pathlib import Path
from decimal import Decimal
from typing import List, Tuple
from urllib.parse import urlparse
from fastapi import Request, HTTPException
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.proxy_server import DualCache
#from litellm.integrations.custom_logger import CustomLogger

dojo_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(dojo_path))

from dojo.models.router_model import Token, Workspace, User, Model, RequestLog
from dojo.models.functions import generate_ulid
from .accounts import LedgerManager
from .llm_provider import LLMProviderClient

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")

# Default cost when model is not in LiteLLM's model_prices_and_context_window.json
DEFAULT_UNMAPPED_MODEL_COST = Decimal("0.0001")
MAX_FALLBACK_SEQUENCE_LENGTH = 5


def _build_fallback_sequence(model: str, fallbacks: List[str]) -> List[str]:
    return ([model] + list(fallbacks))[:MAX_FALLBACK_SEQUENCE_LENGTH]


def _base_url_to_provider_url(base_url: str) -> str:
    """Adapt base_url (may include path e.g. /v1) to provider API root (scheme + netloc only)."""
    if not base_url:
        return ""
    p = urlparse(base_url)
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else base_url.rstrip("/")


async def _resolve_auto_model(
    session: AsyncSession, model_spec: str
) -> Tuple[str, List[str]]:
    """
    Resolve "auto", "auto/<group>", or "auto/<group>/<tag>" to (primary_model, fallbacks).

    Reads from the ``router_model`` table. Group and tag both support "all"
    (or being omitted) to mean no filter on that dimension.

    Results are ordered by highest priority first, then by model_id ascending
    for stable tie-breaking.

    Plain ``"auto"`` returns the row(s) where ``is_default=True``.  If there
    are none, it falls back to all active rows.
    """
    if not model_spec.startswith("auto"):
        return (model_spec, [])

    parts = model_spec.split("/")  # ["auto"] / ["auto", group] / ["auto", group, tag]
    group = parts[1] if len(parts) > 1 else None
    tag = parts[2] if len(parts) > 2 else None

    is_local_group = group and (group == "local" or group.startswith("local_"))

    stmt = (
        select(Model.model_id)
        .where(Model.is_active == True)  # noqa: E712
        .order_by(Model.priority.desc(), Model.model_id.asc())
    )

    if model_spec == "auto":
        # Prefer default model (limit 1); fall through to all active if none are flagged
        default_stmt = stmt.where(Model.is_default == True).limit(1)  # noqa: E712
        result = await session.execute(default_stmt)
        model_ids = [row[0] for row in result.all()]
        if not model_ids:
            result = await session.execute(stmt)
            model_ids = [row[0] for row in result.all()]
    else:
        if group and group != "all":
            stmt = stmt.where(Model.model_group == group)
        if tag and tag != "all":
            stmt = stmt.where(Model.model_tag == tag)

        if is_local_group:
            # Select model_id and base_url so we can call model list API and filter by loaded
            stmt_local = (
                select(Model.model_id, Model.base_url)
                .where(Model.is_active == True)  # noqa: E712
                .order_by(Model.priority.desc(), Model.model_id.asc())
            )
            if group and group != "all":
                stmt_local = stmt_local.where(Model.model_group == group)
            if tag and tag != "all":
                stmt_local = stmt_local.where(Model.model_tag == tag)
            result = await session.execute(stmt_local)
            rows = result.all()
            # Per base_url, get loaded model keys (trimmed) from provider API; keep only loaded
            cache_by_base: dict[str, set[str]] = {}
            filtered_ids: List[str] = []
            for model_id, base_url in rows:
                base_url_val = str(base_url) if base_url is not None else None
                provider_url = _base_url_to_provider_url(base_url_val or "")
                if not provider_url:
                    continue
                if provider_url not in cache_by_base:
                    try:
                        client = LLMProviderClient(base_url=provider_url)
                        models = await asyncio.to_thread(
                            client.list_models, type_filter="llm"
                        )
                        loaded_trimmed = {
                            m.key.split("/")[-1] for m in models if m.is_loaded
                        }
                        cache_by_base[provider_url] = loaded_trimmed
                    except Exception:
                        cache_by_base[provider_url] = set()
                suffix = model_id.split("/", 1)[1] if "/" in model_id else model_id
                if suffix in cache_by_base[provider_url]:
                    filtered_ids.append(model_id)
            model_ids = filtered_ids
        else:
            result = await session.execute(stmt)
            model_ids = [row[0] for row in result.all()]

    if not model_ids:
        raise HTTPException(
            status_code=400,
            detail=f"No active models match '{model_spec}'",
        )

    primary = model_ids[0]
    fallbacks = model_ids[1:]
    return (primary, fallbacks)

async def auth_hook(request: Request, api_key: str) -> UserAPIKeyAuth: 
    dburl = os.environ['DATABASE_ASYNC_URL']
    async_engine = create_async_engine(dburl)
    async_session = async_sessionmaker(async_engine, expire_on_commit=False)
    
    async with async_session() as session:
        # Look up Token object based on api_key matching the "token" column using ORM
        stmt = select(Token).where(Token.token == api_key)
        result = await session.execute(stmt)
        token = result.scalar_one_or_none()

        if token is None:
            await session.close()
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        request.state.dojo_token = token
        request.state.dojo_db_session = session
        #logging.warning(f"user_api_key_auth: {token}")
        return UserAPIKeyAuth(
            api_key=api_key,
        )

async def pre_call_hook(user_api_key_dict: UserAPIKeyAuth, cache: DualCache, data: dict, call_type: str, request: Request):
    session = request.state.dojo_db_session
    token = request.state.dojo_token
    
    # Get workspace information
    stmt = select(Workspace).where(Workspace.id == token.workspace_id)
    result = await session.execute(stmt)
    workspace = result.scalar_one_or_none()
    
    # Initialize ledger manager with session
    ledger_manager = LedgerManager(session)
    
    # Check workspace balance (assumes account exists)
    has_sufficient_balance, _current_balance, error_msg = await ledger_manager.check_workspace_balance(workspace)
    
    if not has_sufficient_balance:
        raise HTTPException(
            status_code=402, 
            detail=f"Insufficient balance: {error_msg}"
        )
    
    # Log successful balance check
    #logging.warning(f"Balance check passed for workspace {workspace.id}: ${current_balance:.10f}")

    # Store workspace
    user_api_key_dict.org_id = workspace.id
    data.setdefault("metadata", {})
    data["metadata"]["user_api_key_org_id"] = workspace.id
    data["metadata"]["dojo_request_id"] = generate_ulid()

    # Dynamic auto: "auto", "auto/<group>", or "auto/<group>/<tag>"
    if data["model"] == "auto" or (isinstance(data["model"], str) and data["model"].startswith("auto/")):
        primary, fallbacks = await _resolve_auto_model(session, data["model"])
        #logging.warning(f"Resolved: {data['model']} > {primary} fallbacks: {', '.join(fallbacks)}")
        data["model"] = primary
        data["fallbacks"] = fallbacks

    model = data.get("model")
    fallbacks = data.get("fallbacks") or []
    if model:
        sequence = _build_fallback_sequence(model, fallbacks)
        data["model"] = sequence[0]
        data["fallbacks"] = sequence[1:]
        data.setdefault("metadata", {})
        data["metadata"]["dojo_fallback_sequence"] = sequence

    # Clear token and workspace information from request state
    request.state.dojo_token = None
    request.state.dojo_workspace = None
    
    # Close session connection
    await session.close()


def _extract_workspace_id(kwargs) -> bytes | None:
    metadata = kwargs.get("litellm_params", {}).get("metadata") or {}
    return metadata.get("user_api_key_org_id")


def _extract_error_details(kwargs) -> dict | None:
    exception = kwargs.get("exception")
    if exception is not None:
        details = {
            "type": type(exception).__name__,
            "message": str(exception),
        }
        status_code = getattr(exception, "status_code", None)
        if status_code is not None:
            details["status_code"] = status_code
        return details

    standard = kwargs.get("standard_logging_object")
    if isinstance(standard, dict):
        error_str = standard.get("error_str")
        if error_str:
            return {"message": error_str}

    return None


def _extract_request_id(kwargs) -> bytes | None:
    metadata = kwargs.get("litellm_params", {}).get("metadata") or {}
    return metadata.get("dojo_request_id")


def _extract_internal_model_name(kwargs) -> str | None:
    """Resolve the internal model_id used in dojo_fallback_sequence."""
    metadata = kwargs.get("litellm_params", {}).get("metadata") or {}
    model_group = metadata.get("model_group")
    if isinstance(model_group, str) and model_group:
        return model_group

    standard = kwargs.get("standard_logging_object")
    if isinstance(standard, dict):
        standard_model_group = standard.get("model_group")
        if isinstance(standard_model_group, str) and standard_model_group:
            return standard_model_group

    sequence = metadata.get("dojo_fallback_sequence") or []
    external_model = kwargs.get("model")
    if isinstance(external_model, str) and external_model in sequence:
        return external_model

    return external_model if isinstance(external_model, str) else None


def _extract_fallback_sequence(kwargs) -> list[str] | None:
    metadata = kwargs.get("litellm_params", {}).get("metadata") or {}
    sequence = metadata.get("dojo_fallback_sequence")
    if sequence:
        return list(sequence)[:MAX_FALLBACK_SEQUENCE_LENGTH]

    body = (
        kwargs.get("litellm_params", {})
        .get("proxy_server_request", {})
        .get("body", {})
    )
    model = kwargs.get("model") or body.get("model")
    fallbacks = body.get("fallbacks") or kwargs.get("fallbacks") or []
    if model:
        return _build_fallback_sequence(model, fallbacks)
    return None


def _usage_field(usage, key: str):
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage.get(key)
    return getattr(usage, key, None)


def _extract_token_metadata(response_obj=None, kwargs=None) -> dict | None:
    usage = getattr(response_obj, "usage", None) if response_obj is not None else None
    if usage is None and kwargs is not None:
        standard = kwargs.get("standard_logging_object")
        if isinstance(standard, dict):
            usage = standard.get("usage")

    if usage is None:
        return None

    metadata = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = _usage_field(usage, key)
        if value is not None:
            metadata[key] = value

    details = _usage_field(usage, "prompt_tokens_details")
    cached_tokens = _usage_field(details, "cached_tokens")
    if cached_tokens is not None:
        metadata["cached_tokens"] = cached_tokens

    return metadata or None


async def _log_request(
    workspace_id: bytes | None,
    request_id: bytes | None,
    model: str | None,
    is_success: bool,
    error_details: dict | None = None,
    fallback_sequence: list[str] | None = None,
    token_metadata: dict | None = None,
) -> None:
    if workspace_id is None or request_id is None or not model:
        return

    dburl = os.environ["DATABASE_ASYNC_URL"]
    async_engine = create_async_engine(dburl)
    async_session = async_sessionmaker(async_engine, expire_on_commit=False)

    async with async_session() as session:
        session.add(
            RequestLog(
                workspace_id=workspace_id,
                request_id=request_id,
                model=model,
                is_success=is_success,
                fallback_sequence=fallback_sequence,
                token_metadata=token_metadata,
                error_details=error_details if not is_success else None,
            )
        )
        await session.commit()
        await session.close()


async def post_call_hook(kwargs, response_obj, start_time, end_time):
    #logging.warning(f"post_call_hook kwargs: {pprint.pformat(kwargs)}")
    workspace_id = _extract_workspace_id(kwargs)
    provider = kwargs.get("custom_llm_provider")
    provider_model = kwargs.get("model")
    internal_model = _extract_internal_model_name(kwargs)
    model_requested = kwargs.get("litellm_params").get("proxy_server_request").get("body").get("model")
    token_metadata = _extract_token_metadata(response_obj=response_obj, kwargs=kwargs)

    await _log_request(
        workspace_id,
        _extract_request_id(kwargs),
        internal_model,
        is_success=True,
        fallback_sequence=_extract_fallback_sequence(kwargs),
        token_metadata=token_metadata,
    )
    try:
        response_cost = Decimal(litellm.completion_cost(completion_response=response_obj)).quantize(Decimal('0.0000000001'))
    except Exception as e:
        # TODO: Expand price list
        #logging.warning(
        #    "Model not in LiteLLM price list, using default cost=0: model=%s provider=%s error=%s",
        #    provider_model or model_requested,
        #    provider,
        #    e,
        #)
        response_cost = DEFAULT_UNMAPPED_MODEL_COST

    dburl = os.environ['DATABASE_ASYNC_URL']
    async_engine = create_async_engine(dburl)
    async_session = async_sessionmaker(async_engine, expire_on_commit=False)
    
    async with async_session() as session:
        ledger_manager = LedgerManager(session)
        
        # Get workspace for the transaction
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        result = await session.execute(stmt)
        workspace = result.scalar_one_or_none()
        
        # Process the purchase transaction
        new_balance = await ledger_manager.process_purchase(workspace, response_cost, provider, provider_model, f"API Usage - {model_requested}")
        await session.commit()
        await session.close()
        new_balance = new_balance.quantize(Decimal('0.0000000001'))
        logging.warning(
            "Success - workspace:%s model:%s cost:%s balance:%s tokens:%s (in: %s, out: %s, cached: %s)",
            str(ULID(bytes(workspace_id))), internal_model or model_requested, response_cost, new_balance,
            token_metadata.get("total_tokens") if token_metadata else None,
            token_metadata.get("prompt_tokens") if token_metadata else None,
            token_metadata.get("completion_tokens") if token_metadata else None,
            token_metadata.get("cached_tokens") if token_metadata else None,
        )


async def failure_call_hook(kwargs, response_obj, start_time, end_time):
    workspace_id = _extract_workspace_id(kwargs)
    internal_model = _extract_internal_model_name(kwargs)
    error_details = _extract_error_details(kwargs)

    await _log_request(
        workspace_id,
        _extract_request_id(kwargs),
        internal_model,
        is_success=False,
        error_details=error_details,
        fallback_sequence=_extract_fallback_sequence(kwargs),
        token_metadata=_extract_token_metadata(response_obj=response_obj, kwargs=kwargs),
    )

    logging.warning(
        "Failure - workspace:%s model:%s error:%s",
        str(ULID(bytes(workspace_id))) if workspace_id else None,
        internal_model,
        error_details,
    )
