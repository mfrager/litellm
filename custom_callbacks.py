import os
import sys
import inspect
import traceback

import litellm
from litellm.integrations.custom_logger import CustomLogger

class BNRouterHandler(CustomLogger):
    def __init__(self):
        blue_color_code = "\033[94m"
        reset_color_code = "\033[0m"
        print(f"{blue_color_code}Initialized LiteLLM custom logger")
        try:
            print("Logger Initialized with following methods:")
            methods = [
                method
                for method in dir(self)
                if inspect.ismethod(getattr(self, method))
            ]

            for method in methods:
                print(f" - {method}")
            print(f"{reset_color_code}")
        except Exception:
            pass

    def log_pre_api_call(self, model, messages, kwargs):
        print("Pre-API Call")

    def log_post_api_call(self, kwargs, response_obj, start_time, end_time):
        print("Post-API Call")

    def log_stream_event(self, kwargs, response_obj, start_time, end_time):
        print("On Stream")

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        print("On Success!")

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        print("On Async Success!")
        response_cost = litellm.completion_cost(completion_response=response_obj)
        print(f"Cost: {response_cost}")
        #assert response_cost > 0.0
        return

    async def async_log_failure_event(self, kwargs, response_obj, start_time, end_time):
        try:
            print("On Async Failure !")
        except Exception as e:
            print(f"Exception: {e}")

proxy_handler_instance = BNRouterHandler()
