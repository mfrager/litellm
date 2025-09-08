import os
import sys
import inspect
import logging
import traceback

import litellm
from litellm.proxy.proxy_server import UserAPIKeyAuth, DualCache
from litellm.integrations.custom_logger import CustomLogger

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")

class BNRouterHandler(CustomLogger):
    #def __init__(self):
    #    pass
        #blue_color_code = "\033[94m"
        #reset_color_code = "\033[0m"
        #print(f"{blue_color_code}Initialized LiteLLM custom logger")
        #try:
        #    print("Logger Initialized with following methods:")
        #    methods = [
        #        method
        #        for method in dir(self)
        #        if inspect.ismethod(getattr(self, method))
        #    ]
        #    for method in methods:
        #        print(f" - {method}")
        #    print(f"{reset_color_code}")
        #except Exception:
        #    pass

    #def log_pre_api_call(self, model, messages, kwargs):
    #    pass
        #logging.warning(f"Request - model:{model}")

    #def log_post_api_call(self, kwargs, response_obj, start_time, end_time):
    #    pass
        #print("Post-API Call")

    #def log_stream_event(self, kwargs, response_obj, start_time, end_time):
    #    pass
        #print("On Stream")

    #def log_success_event(self, kwargs, response_obj, start_time, end_time):
    #    pass
        #print("On Success!")

    async def async_pre_call_hook(self, user_api_key_dict: UserAPIKeyAuth, cache: DualCache, data: dict, call_type: str):
        dynamic_routing = False
        if dynamic_routing:
            model = data['model']
            messages = data['messages']
        #logging.warning(f"Pre-Call Hook - model:{data['model']}")
        #logging.warning(f"Pre-Call Hook - call_type:{call_type} data:{data}")

        # Test MySQL

        dburl = "mysql+aiomysql://router_admin:jdRwGiNo8bMRQzK79b7M0TJO@host.docker.internal:3306/dojo_router"
        async_engine = create_async_engine(dburl)
        async with async_engine.connect() as conn:
            query = await conn.execute(text("SELECT * FROM router_workspace"))
            result = query.fetchall()
            print(f"Result: {result}")
            

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        #logging.warning(f"Success - response:{response_obj}")
        response_cost = litellm.completion_cost(completion_response=response_obj)
        logging.warning(f"Success - model:{response_obj.model} cost:{response_cost:.10f} tokens:{response_obj.usage.total_tokens} (in: {response_obj.usage.prompt_tokens}, out: {response_obj.usage.completion_tokens}, cached: {response_obj.usage.prompt_tokens_details.cached_tokens})")
        #print(f"Cost: {response_cost}")
        #assert response_cost > 0.0
        return

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        try:
            print("On Async Failure !")
        except Exception as e:
            print(f"Exception: {e}")

proxy_handler_instance = BNRouterHandler()
