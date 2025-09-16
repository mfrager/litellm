import os
import sys
import pprint
import inspect
import logging
import litellm
import traceback
from pathlib import Path
from decimal import Decimal
from typing import Optional
from fastapi import Request, HTTPException
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.proxy_server import DualCache
from litellm.integrations.custom_logger import CustomLogger

dojo_path = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(dojo_path))

from models.router_model import Token, Workspace, User
from .accounts import LedgerManager

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")

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
            session.close()
            raise HTTPException(status_code=401, detail="Unauthorized")
        
        request.state.dojo_token = token
        request.state.dojo_db_session = session
        #logging.warning(f"user_api_key_auth: {token}")
        return UserAPIKeyAuth(
            api_key=api_key,
        )

async def pre_call_hook(user_api_key_dict: UserAPIKeyAuth, cache: DualCache, data: dict, call_type: str, request: Optional[Request]):
    session = request.state.dojo_db_session
    token = request.state.dojo_token
    
    # Get workspace information
    stmt = select(Workspace).where(Workspace.id == token.workspace_id)
    result = await session.execute(stmt)
    workspace = result.scalar_one_or_none()
    
    # Initialize ledger manager with session
    ledger_manager = LedgerManager(session)
    
    # Check workspace balance (assumes account exists)
    has_sufficient_balance, current_balance, error_msg = await ledger_manager.check_workspace_balance(workspace)
    
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

    #logging.warning(f"pre_call_hook data: {pprint.pformat(data)}")

    # Clear token and workspace information from request state
    request.state.dojo_token = None
    request.state.dojo_workspace = None
    
    # Close session connection
    await session.close()

async def post_call_hook(kwargs, response_obj, start_time, end_time):
    #logging.warning(f"post_call_hook kwargs: {pprint.pformat(kwargs)}")
    workspace_id = kwargs.get("litellm_params").get("metadata").get("user_api_key_org_id")
    provider = kwargs.get("custom_llm_provider")
    provider_model = kwargs.get("model")
    model_requested = kwargs.get("litellm_params").get("proxy_server_request").get("body").get("model")
    response_cost = Decimal(litellm.completion_cost(completion_response=response_obj)).quantize(Decimal('0.0000000001'))

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
        logging.warning(f"Success - workspace:{workspace_id} model:{model_requested} cost:{response_cost} balance:{new_balance} tokens:{response_obj.usage.total_tokens} (in: {response_obj.usage.prompt_tokens}, out: {response_obj.usage.completion_tokens}, cached: {response_obj.usage.prompt_tokens_details.cached_tokens})")
