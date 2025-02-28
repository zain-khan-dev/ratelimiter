import threading
import time
from abc import ABC, abstractmethod
from enum import Enum
from threading import Lock


class SingletonMeta(type):

    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            new_instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = new_instance
        return cls._instances[cls]



class UserLimitState:
    def __init__(self):
        self.count = 0
        self.start_time = time.time()


class GranularityFactory():
    @staticmethod
    def get_granularity_config(granularity, time_unit, allowed_count):
        if granularity == GranularityLevel.HOURLY:
            return HourWiseGranularity(time_unit, allowed_count)
        elif granularity == GranularityLevel.MINUTELY:
            return MinuteWiseGranularityConfig(time_unit, allowed_count)
        elif granularity == GranularityLevel.DAILY:
            return DayWiseGranularity(time_unit, allowed_count)
        else:
            raise Exception("Granularity not found, please configure properly")


class BaseGranularity(ABC):
    time_unit: int
    allowed_count: int

    def __init__(self, time_unit, allowed_count):
        self.time_unit = time_unit
        self.allowed_count = allowed_count


    @abstractmethod
    def validate_rate_limit(self, api_path, user_attribute):
        pass


class RateLimitConfigValue:

    def __init__(self):
        self.start_time = time.time()
        self.current_count = 0


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

    @staticmethod
    def get_key(api_path, user_attribute):
        return '_'.join([api_path, user_attribute, GranularityLevel.MINUTELY.value])


    def validate_rate_limit(self, api_path, user_attribute):
        """
            Implement rate limit on the basis of minute
        :return:
        """
        key = self.get_key(api_path, user_attribute)
        rate_limit_store_service = RateLimitStoreService()
        with rate_limit_store_service.fetch_lock(key):
            current_rate_limit_value: RateLimitConfigValue = rate_limit_store_service.get_key(key)
            current_time_diff = time.time() - current_rate_limit_value.start_time
            reset_after = current_rate_limit_value.start_time + self.time_unit*60
            if current_time_diff > self.time_unit*60:
                current_rate_limit_value.start_time = time.time()
                current_rate_limit_value.current_count = 0
            else:
                if current_rate_limit_value.current_count + 1 > self.allowed_count:
                    print(" Id with ", threading.get_ident(), " Rate limited")
                    return RateLimitResponse(
                        True, 0, self.allowed_count, reset_after)
            current_rate_limit_value.current_count += 1
            remaining = self.allowed_count - current_rate_limit_value.current_count
            rate_limit_store_service.update_key(key, current_rate_limit_value)
            return RateLimitResponse(False, remaining, self.allowed_count, reset_after)


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


class RateLimitStoreService(metaclass=SingletonMeta):
    rate_limit_store: dict[str, UserLimitState] = {}
    rate_limit_config: dict[str, dict[str, str]] = {}
    lock_dict: dict[str, Lock] = {}

    @classmethod
    def get_key(cls, key):
        return cls.rate_limit_store.get(key, RateLimitConfigValue())

    @classmethod
    def update_key(cls, key, config):
        cls.rate_limit_store[key] = config

    @classmethod
    def fetch_lock(cls, key):
        return cls.lock_dict.setdefault(key, Lock())

# We will support three granulaity layers
# per minute, per hour, per day
# We can save the minute, hour, day as suffix
