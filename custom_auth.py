import os
import sys
import pprint
import inspect
import logging
import litellm
import traceback
from pathlib import Path
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from litellm.proxy._types import UserAPIKeyAuth

dojo_path = Path(__file__).resolve().parent / "dojo"
sys.path.insert(0, str(dojo_path))

from models.router_model import Token
from ledger.sql_ledger import SQLLedgerAPI
from router.handlers import auth_hook

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")

async def user_api_key_auth(request: Request, api_key: str) -> UserAPIKeyAuth: 
    return await auth_hook(request, api_key)

