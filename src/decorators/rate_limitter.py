from email.header import Header
from functools import wraps
from http import HTTPStatus

from src.services.RateLimitStoreService import GranularityFactory
from src.utils.Constants import HeaderConstants


def rate_limit(granularity, time_unit, allowed_count):
    def inner_dec(func):
        @wraps(func)
        async def inner(*args, request, response, **kwargs):
            granularity_config = GranularityFactory.get_granularity_config(granularity, time_unit, allowed_count)
            rate_limit_response = granularity_config.validate_rate_limit(request["path"], request.client.host)
            response.headers[HeaderConstants.X_RATELIMIT_REMAINING] = str(rate_limit_response.remaining)
            response.headers[HeaderConstants.X_RATELIMIT_LIMIT] = str(rate_limit_response.limit)
            response.headers[HeaderConstants.X_RATELIMIT_RESET] = str(rate_limit_response.reset_after)
            response.headers[HeaderConstants.RETRY_AFTER] = str(rate_limit_response.reset_after)
            if rate_limit_response.is_rate_limited:
                response.status_code = HTTPStatus.TOO_MANY_REQUESTS
            return await func(*args, request, response, **kwargs)
        return inner
    return inner_dec