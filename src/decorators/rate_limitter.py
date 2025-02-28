from functools import wraps

from starlette.responses import Response

from src.services.RateLimitStoreService import GranularityFactory


def rate_limit(granularity, time_unit, allowed_count):
    def inner_dec(func):
        @wraps(func)
        async def inner(*args, request, **kwargs):
            print(request["path"])
            granularity_config = GranularityFactory.get_granularity_config(granularity, time_unit, allowed_count)
            granularity_config.validate_rate_limit(request["path"], request.client.host)
            response: Response = await func(*args, request, **kwargs)
            response.headers["X-RateLimit-Remaining"] = 1
            response.headers["X-RateLimit-Limit"] = 100
            response.headers["X-RateLimit-Reset"] = 20
            response.headers["Retry-After"] = 100
            return response
        return inner
    return inner_dec