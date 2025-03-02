import queue
import time
import uuid
from threading import Lock

from collections import deque
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


class InMemoryRateLimitStore(RateLimitStoreService):
    __metaclass__ = SingletonMeta
    rate_limit_store: dict[str, UserLimitState] = {}
    rate_limit_config: dict[str, dict[str, str]] = {}
    lock_dict: dict[str, Lock] = {}
    queue_hash: dict[str, deque] = {}
    queue_lock_dict = dict[str, Lock] = {}

    @classmethod
    def fetch_queue_lock(cls, key):
        return cls.queue_lock_dict.setdefault(key, Lock())

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



    @classmethod
    def append_request_log(cls, key, time_unit, allowed_limit) -> [bool, int, int]:
        with cls.fetch_queue_lock(key):
            current_time = time.time()
            client_queue = cls.queue_hash.setdefault(key, deque())
            while client_queue and client_queue[0]  + time_unit < current_time:
                client_queue.popleft()
            reset_after = (client_queue[0] + time_unit) - current_time
            if len(client_queue) >= allowed_limit:
                return False, len(client_queue), reset_after
            client_queue.append(current_time)
        return True, len(client_queue), reset_after


class RedisRateLimitStore(RateLimitStoreService):
    redis_client = redis.Redis()
    add_to_sorted_set_lua_script = """
                local key = KEYS[1]
                local current_time = tonumber(ARGV[1])
                local time_unit = tonumber(ARGV[2])
                local allowed_count = tonumber(ARGV[3])
                local unique_member = ARGV[4]
                local lower_range = current_time - time_unit
                redis.call("ZREMRANGEBYSCORE", key, "-inf", lower_range - 1)
                local count = redis.call("ZCOUNT", key, lower_range, current_time)
                local is_rate_limited = 0
                local remaining_count = math.max(allowed_count - count, 0)
                local oldest_request_time = current_time
                local oldest_request = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
                if #oldest_request > 0 then
                    oldest_request_time = tonumber(oldest_request[2])
                end

                if remaining_count > 0
                then
                    redis.call("ZADD", key, current_time, unique_member)
                    redis.call("EXPIRE", key, time_unit)
                else
                    is_rate_limited = 1
                end
                return {is_rate_limited, remaining_count, oldest_request_time}
            """
    add_to_set = redis_client.register_script(add_to_sorted_set_lua_script)

    @classmethod
    def increment_key(cls, key, ttl):
        if cls.redis_client.setnx(key, 0):
            cls.redis_client.expire(key, ttl)
        current_count = cls.redis_client.incr(key)
        remaining_ttl = cls.redis_client.ttl(key)
        return current_count, remaining_ttl


    @classmethod
    def add_request_log(cls, key, ttl, allowed_count, use_registered_script=True):
        keys = [key]
        args = [int(time.time()), ttl, allowed_count, str(uuid.uuid4())]
        if use_registered_script:
            result_tuple = cls.add_to_set(keys, args)
        else:
            result_tuple = cls.redis_client.eval(cls.add_to_sorted_set_lua_script,len(keys), *keys, *args)
        return result_tuple


