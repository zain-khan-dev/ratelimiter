import time
from threading import Lock

import redis


class RateLimitConfigValue:

    def __init__(self):
        self.start_time = time.time()
        self.current_count = 0



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



from abc import ABC, abstractmethod


class RateLimitStoreService(ABC):

    @abstractmethod
    def increment_key(self, key, ttl):
        pass


class InMemoryRateLimitStore(RateLimitStoreService, metaclass=SingletonMeta):
    rate_limit_store: dict[str, UserLimitState] = {}
    rate_limit_config: dict[str, dict[str, str]] = {}
    lock_dict: dict[str, Lock] = {}

    @classmethod
    def fetch_lock(cls, key):
        return cls.lock_dict.setdefault(key, Lock())

    @classmethod
    def increment_key(cls, key, expire_after):
        with cls.fetch_lock(key):
            current_user_limits = cls.rate_limit_store.setdefault(key, UserLimitState())
            if current_user_limits.start_time + expire_after < time.time():
                current_user_limits.count = 0
                current_user_limits.start_time = time.time()
            current_user_limits.count += 1
            return current_user_limits.count, current_user_limits.start_time + expire_after


class RedisRateLimitStore(RateLimitStoreService):
    redis_client = redis.Redis()

    @classmethod
    def increment_key(cls, key, ttl):
        if not cls.redis_client.exists(key):
            cls.redis_client.setex(key, ttl, 0)
        current_count = cls.redis_client.incr(key)
        remaining_ttl = cls.redis_client.ttl(key)
        if remaining_ttl == -1:
            cls.redis_client.expire(key, ttl)
            remaining_ttl = ttl
        return current_count, remaining_ttl



