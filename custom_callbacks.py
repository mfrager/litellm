import os
import sys
import inspect
import logging
import litellm
import traceback
from pathlib import Path
from typing import Optional
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from litellm.proxy.proxy_server import UserAPIKeyAuth, DualCache
from litellm.integrations.custom_logger import CustomLogger

dojo_path = Path(__file__).resolve().parent / "dojo"
sys.path.insert(0, str(dojo_path))

from ledger.sql_ledger import SQLLedgerAPI
from router.handlers import pre_call_hook

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")

class DojoRouterHandler(CustomLogger):

    #def log_pre_api_call(self, model, messages, kwargs):
    #    logging.warning(f"Request - model:{model}")

    #def log_post_api_call(self, kwargs, response_obj, start_time, end_time):
    #    print("Post-API Call")

    #def log_stream_event(self, kwargs, response_obj, start_time, end_time):
    #    print("On Stream")

    #def log_success_event(self, kwargs, response_obj, start_time, end_time):
    #    print("On Success!")

    async def async_pre_call_hook(self, user_api_key_dict: UserAPIKeyAuth, cache: DualCache, data: dict, call_type: str, request: Optional[Request]):
        await pre_call_hook(user_api_key_dict, cache, data, call_type, request)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        #logging.warning(f"Success - response:{response_obj}")
        response_cost = litellm.completion_cost(completion_response=response_obj)
        logging.warning(f"Success - model:{response_obj.model} cost:{response_cost:.10f} tokens:{response_obj.usage.total_tokens} (in: {response_obj.usage.prompt_tokens}, out: {response_obj.usage.completion_tokens}, cached: {response_obj.usage.prompt_tokens_details.cached_tokens})")
        #print(f"Cost: {response_cost}")
        #assert response_cost > 0.0
        return

    #async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
    #    try:
    #        print("On Async Failure !")
    #    except Exception as e:
    #        print(f"Exception: {e}")

proxy_handler_instance = DojoRouterHandler()

