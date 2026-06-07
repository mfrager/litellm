import sys
import logging
from pathlib import Path
from typing import Optional
from fastapi import Request
from litellm.proxy.proxy_server import UserAPIKeyAuth, DualCache
from litellm.integrations.custom_logger import CustomLogger

# Add project root so "dojo" package can be imported (same as in dojo tests)
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from dojo.router.handlers import pre_call_hook, post_call_hook, failure_call_hook

logging.basicConfig(level=logging.WARNING, format="%(levelname)s:\t%(message)s")

class DojoRouterHandler(CustomLogger):
    async def async_pre_call_hook(self, user_api_key_dict: UserAPIKeyAuth, cache: DualCache, data: dict, call_type: str, request: Optional[Request]):
        await pre_call_hook(user_api_key_dict, cache, data, call_type, request) # type: ignore[reportCallIssue]

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        #logging.warning("kwargs: " + pprint.pformat(kwargs))
        #logging.warning("response_obj: " + pprint.pformat(response_obj))
        await post_call_hook(kwargs, response_obj, start_time, end_time)

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        await failure_call_hook(kwargs, response_obj, start_time, end_time)

    #async def async_post_call_success_hook(self, data: dict, user_api_key_dict: UserAPIKeyAuth, response):
    #    pass

    #async def async_post_call_failure_hook(self, request_data: dict, original_exception: Exception, user_api_key_dict: UserAPIKeyAuth, traceback_str: Optional[str] = None):
    #    logging.warning(f"------ Begin Post Call Failure Hook ------")

proxy_handler_instance = DojoRouterHandler()

