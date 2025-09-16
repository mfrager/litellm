import os
import sys
import pprint
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
from router.handlers import pre_call_hook, post_call_hook

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")

class DojoRouterHandler(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict: UserAPIKeyAuth, cache: DualCache, data: dict, call_type: str, request: Optional[Request]):
        await pre_call_hook(user_api_key_dict, cache, data, call_type, request)

    async def async_post_call_success_hook(self, data: dict, user_api_key_dict: UserAPIKeyAuth, response):
        pass
        #await post_call_hook(data, user_api_key_dict, response)

    async def async_post_call_failure_hook(self, request_data: dict, original_exception: Exception, user_api_key_dict: UserAPIKeyAuth, traceback_str: Optional[str] = None):
        logging.warning(f"Post-call Failure")

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        #logging.warning("kwargs: " + pprint.pformat(kwargs))
        #logging.warning("response_obj: " + pprint.pformat(response_obj))
        await post_call_hook(kwargs, response_obj, start_time, end_time)

    #async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
    #    logging.warning(f"Log Failure")
        
        #raise Exception("Introspect")
        #await post_call_hook(kwargs, response_obj, start_time, end_time, request)
        #logging.warning(f"Success - response:{response_obj}")
        #response_cost = litellm.completion_cost(completion_response=response_obj)
        #logging.warning(f"Success - model:{response_obj.model} cost:{response_cost:.10f} tokens:{response_obj.usage.total_tokens} (in: {response_obj.usage.prompt_tokens}, out: {response_obj.usage.completion_tokens}, cached: {response_obj.usage.prompt_tokens_details.cached_tokens})")
        #print(f"Cost: {response_cost}")
        #assert response_cost > 0.0
        #return

proxy_handler_instance = DojoRouterHandler()

