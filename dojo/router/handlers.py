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

from dojo.models.router_model import Token, Workspace, User, Model
from .accounts import LedgerManager
from .llm_provider import LLMProviderClient

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")


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
    data['metadata']['user_api_key_org_id'] = workspace.id

    # Dynamic auto: "auto", "auto/<group>", or "auto/<group>/<tag>"
    if data["model"] == "auto" or (isinstance(data["model"], str) and data["model"].startswith("auto/")):
        primary, fallbacks = await _resolve_auto_model(session, data["model"])
        logging.warning(f"Resolved: {data['model']} > {primary} fallbacks: {', '.join(fallbacks)}")
        data["model"] = primary
        data["fallbacks"] = fallbacks

    # Clear token and workspace information from request state
    request.state.dojo_token = None
    request.state.dojo_workspace = None
    
    # Close session connection
    await session.close()

# Default cost when model is not in LiteLLM's model_prices_and_context_window.json
DEFAULT_UNMAPPED_MODEL_COST = Decimal("0.0001")

async def post_call_hook(kwargs, response_obj, start_time, end_time):
    #logging.warning(f"post_call_hook kwargs: {pprint.pformat(kwargs)}")
    workspace_id = kwargs.get("litellm_params").get("metadata").get("user_api_key_org_id")
    provider = kwargs.get("custom_llm_provider")
    provider_model = kwargs.get("model")
    model_requested = kwargs.get("litellm_params").get("proxy_server_request").get("body").get("model")
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
        usage = getattr(response_obj, "usage", None)
        total_tokens = getattr(usage, "total_tokens", None) if usage else None
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        details = getattr(usage, "prompt_tokens_details", None) if usage else None
        cached_tokens = getattr(details, "cached_tokens", None) if details else None
        logging.warning(
            "Success - workspace:%s model:%s cost:%s balance:%s tokens:%s (in: %s, out: %s, cached: %s)",
            str(ULID(bytes(workspace_id))), model_requested, response_cost, new_balance,
            total_tokens, prompt_tokens, completion_tokens, cached_tokens,
        )
