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

from models.router_model import Token, Workspace
from ledger.sql_ledger import SQLLedgerAPI

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")

async def auth_hook(request: Request, api_key: str) -> UserAPIKeyAuth: 
    dburl = os.environ['DATABASE_ASYNC_URL']
    async_engine = create_async_engine(dburl)
    async_session = async_sessionmaker(async_engine, expire_on_commit=False)
    
    async with async_session() as session:
        # Look up Token object based on api_key matching the "token" column using ORM
        from sqlalchemy import select
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
    #dynamic_routing = False
    #if dynamic_routing:
    #    model = data['model']
    #    messages = data['messages']
    #logging.warning(f"Pre-Call Hook - model:{data['model']}")
    #logging.warning(f"Pre-Call Hook - call_type:{call_type} data:{data}")

    session = request.state.dojo_db_session
    token = request.state.dojo_token
    stmt = select(Workspace).where(Workspace.id == token.workspace_id)
    result = await session.execute(stmt)
    workspace = result.scalar_one_or_none()
    await session.close()
    logging.warning(f"async_pre_call_hook: {workspace.ts_created}")

