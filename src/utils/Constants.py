class Constants:
    pass


class HeaderConstants:
    X_RATELIMIT_REMAINING = "X-RateLimit-Remaining"
    X_RATELIMIT_LIMIT = "X-RateLimit-Limit"
    X_RATELIMIT_RESET = "X-RateLimit-Reset"
    RETRY_AFTER = "Retry-After"


#            response.headers["X-RateLimit-Remaining"] = str(rate_limit_response.remaining)
#             response.headers["X-RateLimit-Limit"] = str(rate_limit_response.limit)
#             response.headers["X-RateLimit-Reset"] = str(rate_limit_response.reset_after)
#             response.headers["Retry-After"] = str(rate_limit_response.reset_after)