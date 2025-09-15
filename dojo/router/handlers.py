import os
import sys
import pprint
import inspect
import logging
import litellm
import traceback
from pathlib import Path
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
    
    # Get user information
    stmt = select(User).where(User.id == workspace.owner_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    
    # Initialize ledger manager with session
    ledger_manager = LedgerManager(session)
    
    # Check user balance (assumes account exists)
    has_sufficient_balance, current_balance, error_msg = await ledger_manager.check_user_balance(user, workspace)
    
    if not has_sufficient_balance:
        raise HTTPException(
            status_code=402, 
            detail=f"Insufficient balance: {error_msg}"
        )
    
    # Log successful balance check
    logging.warning(f"Balance check passed for user {user.email}: ${current_balance:.10f}")
    
    # Store ledger manager in request state for potential use in post-call hook
    request.state.ledger_manager = ledger_manager

