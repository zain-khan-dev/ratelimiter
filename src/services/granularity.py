import time
from abc import abstractmethod, ABC
from enum import Enum

from src.services.RateLimitStoreService import RateLimitStoreService, RateLimitConfigValue, InMemoryRateLimitStore


class UserLimitState:
    def __init__(self):
        self.count = 0
        self.start_time = time.time()


class GranularityFactory:
    @staticmethod
    def get_granularity_config(granularity, time_unit, allowed_count, rate_limit_store):
        if granularity == GranularityLevel.HOURLY:
            return HourWiseGranularity(time_unit, allowed_count, rate_limit_store)
        elif granularity == GranularityLevel.MINUTELY:
            return MinuteWiseGranularityConfig(time_unit, allowed_count, rate_limit_store)
        elif granularity == GranularityLevel.DAILY:
            return DayWiseGranularity(time_unit, allowed_count, rate_limit_store)
        else:
            raise Exception("Granularity not found, please configure properly")


class BaseGranularity(ABC):
    time_unit: int
    allowed_count: int

    def __init__(self, time_unit, allowed_count, rate_limit_store):
        self.time_unit = time_unit
        self.allowed_count = allowed_count
        self.rate_limit_store = rate_limit_store


    @abstractmethod
    def validate_rate_limit(self, api_path, user_attribute):
        pass



class GranularityLevel(Enum):
    MINUTELY = "minutely"
    DAILY = "daily"
    HOURLY = "hourly"


class RateLimitResponse:
    def __init__(self, is_rate_limited, remaining, limit, reset_after):
        self.is_rate_limited = is_rate_limited
        self.remaining = remaining
        self.limit = limit
        self.reset_after = reset_after

class MinuteWiseGranularityConfig(BaseGranularity):

    @classmethod
    def get_window_start(cls, current_time):
        """
            Current time given in seconds
            Fixed time window
            if time falls between 10:26:33 the start window will be 10:26:00 end window would be 10:27:00
            find the start time for that minute given 10 seconds window
        """
        return (current_time//60) * 60

    @classmethod
    def get_window_end(cls, current_time):
        return (current_time//60 + 1) * 60 # one minute greater


    @staticmethod
    def get_key(api_path, user_attribute, *args):
        return '_'.join([api_path, user_attribute, *args, GranularityLevel.MINUTELY.value])


    def validate_rate_limit(self, api_path, user_attribute):
        """
            Implement rate limit on the basis of minute
        :return:
        """
        # TODO: check for time unit and how we are comparing
        # we might be using different values for different operations
        key = self.get_key(api_path, user_attribute)
        current_count, reset_after = self.rate_limit_store.user_based_increment_key(key, self.time_unit * 60)
        if current_count > self.allowed_count:
            return RateLimitResponse(True, 0, self.allowed_count, reset_after)
        return RateLimitResponse(False, self.allowed_count - current_count, self.allowed_count,
                                 reset_after)


class DayWiseGranularity(BaseGranularity):

    __GRANULARITY_LEVEL__ = "daywise"

    def validate_rate_limit(self, api_path, user_attribute):
        """
            Implement rate limit on the basis of day
        :return:
        """



class HourWiseGranularity(BaseGranularity):

    __GRANULARITY_LEVEL__ = "hourwise"

    def validate_rate_limit(self, api_path, user_attribute):
        """
            Implement rate limit on the basis of hour
        :return:
        """
        pass

