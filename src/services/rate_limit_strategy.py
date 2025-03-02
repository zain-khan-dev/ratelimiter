from src.services.granularity import GranularityFactory, RateLimitResponse

from abc import ABC, abstractmethod
import time

class RateLimitStrategy(ABC):
    def __init__(self, granularity_level, time_unit, allowed_count, rate_limit_store):
        self.granularity = GranularityFactory.get_granularity_config(granularity_level, time_unit)
        self.rate_limit_store = rate_limit_store
        self.allowed_count = allowed_count


    @abstractmethod
    def validate_rate_limit(self, api_path, user_attribute):
        pass


class FixedWindowRateLimitStrategy:
    def __init__(self, granularity_level, time_unit, allowed_count, rate_limit_store):
        self.granularity = GranularityFactory.get_granularity_config(granularity_level, time_unit)
        self.rate_limit_store = rate_limit_store
        self.allowed_count = allowed_count

    def validate_rate_limit(self, api_path, user_attribute):
        """
            Implement rate limit on the basis of minute
        :return:
        """
        # TODO: check for time unit and how we are comparing
        # we might be using different values for different operations
        key = self.granularity.get_key(api_path, user_attribute)
        current_count, reset_after = self.rate_limit_store.user_based_increment_key(key, self.granularity.time_unit)
        if current_count > self.allowed_count:
            return RateLimitResponse(True, 0, self.allowed_count, reset_after)
        return RateLimitResponse(False, self.allowed_count - current_count, self.allowed_count,
                                 reset_after)

class SlidingWindowLogRateLimitStrategy(RateLimitStrategy):
    """
        For in memory uses queue based approach
        for redis uses sorted set
    """
    def validate_rate_limit(self, api_path, user_attribute) -> RateLimitResponse:
        key = self.granularity.get_key(api_path, user_attribute)
        is_successful, current_count, reset_after = self.rate_limit_store.append_request_log(key)
        if not is_successful:
            return RateLimitResponse(True, 0, self.allowed_count, reset_after)
        return RateLimitResponse(False, self.allowed_count - current_count, self.allowed_count, reset_after)


class SlidingWindowCounterRateLimitStrategy(RateLimitStrategy):
    def validate_rate_limit(self, api_path, user_attribute) -> RateLimitResponse:

        current_time = int(time.time())
        previous_window = self.granularity.get_window_start(current_time)
        current_window = self.granularity.get_window_end(current_time)
        previous_key = self.granularity.get_key(api_path, user_attribute, previous_window)
        current_key = self.granularity.get_key(api_path, user_attribute, current_window)
        previous_count = min(self.allowed_count, self.rate_limit_store.get_counter(previous_key))
        current_count= min(self.allowed_count, self.rate_limit_store.increment_counter_key(current_key))
        reset_after = current_window
        corrected_count = round((current_window - current_time)/60 * previous_count) + current_count
        if corrected_count > self.allowed_count:
            return RateLimitResponse(True, 0, self.allowed_count, reset_after)
        return RateLimitResponse(False, self.allowed_count - corrected_count, self.allowed_count, reset_after)


class TokenBucketRateLimitStrategy:
    pass


class LeakyBucketRateLimitStrategy:
    pass