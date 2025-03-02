import queue
import time
import uuid
from math import floor
from threading import Lock

from collections import deque
import redis
from anyio import current_time
import math

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
    def user_based_increment_key(self, key, ttl):
        pass


class InMemoryRateLimitStore(RateLimitStoreService):
    __metaclass__ = SingletonMeta
    user_rate_limit_store: dict[str, UserLimitState] = {}
    rate_limit_config: dict[str, dict[str, str]] = {}
    lock_dict: dict[str, Lock] = {}
    queue_hash: dict[str, deque] = {}
    queue_lock_dict = dict[str, Lock] = {}
    counter_rate_limit_store: dict[str, int]  = {}
    token_hash: dict = {}


    @classmethod
    def fetch_queue_lock(cls, key):
        return cls.queue_lock_dict.setdefault(key, Lock())

    @classmethod
    def fetch_lock(cls, key):
        return cls.lock_dict.setdefault(key, Lock())

    @classmethod
    def user_based_increment_key(cls, key, expire_after):
        with cls.fetch_lock(key):
            current_user_limits = cls.user_rate_limit_store.setdefault(key, UserLimitState())
            if current_user_limits.start_time + expire_after < time.time():
                current_user_limits.count = 0
                current_user_limits.start_time = time.time()
            current_user_limits.count += 1
            return current_user_limits.count, current_user_limits.start_time + expire_after

    @classmethod
    def increment_counter_key(cls, key):
        with cls.fetch_lock(key):
            cls.counter_rate_limit_store.setdefault(key, 0)
            cls.counter_rate_limit_store[key] += 1
            return cls.counter_rate_limit_store[key]


    @classmethod
    def get_counter(cls, key):
        with cls.fetch_lock(key):
            return cls.counter_rate_limit_store.get(key, 0)


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


    @classmethod
    def refill_tokens(cls, key, refill_rate, allowed_tokens):
        with cls.fetch_lock(key):
            current_time = int(time.time())
            current_tokens, last_refill_time = cls.token_hash.setdefault(key, (allowed_tokens, current_time))
            cls.token_hash[key] = (min(allowed_tokens, current_tokens +
                                       (current_time - last_refill_time) * refill_rate), current_time)

    @classmethod
    def decr_token(cls, key):
        with cls.fetch_lock(key):
            current_token, last_refill_time = cls.token_hash[key]
            if current_token > 0:
                cls.token_hash[key] = (current_token - 1, last_refill_time)
                return False, current_token - 1, 0
            return True, 0, 0


    @classmethod
    def refill_and_decr_token(cls, key, refill_rate, allowed_tokens):
        """
            Get the tokens that were filled last refill time
            refill them again based on the refill rate, current time and last_refill_time
            decrement them by one and return not rate limited if they haven't reached 0
            otherwise just send rate_limited
        """
        with cls.fetch_lock(key):
            current_time = int(time.time())
            previous_tokens, last_refill_time = cls.token_hash.setdefault(key, (allowed_tokens, current_time))
            current_token = (min(allowed_tokens, previous_tokens + (current_time - last_refill_time) * refill_rate))
            if current_token > 0:
                current_token -= 1
            else:
                return True, last_refill_time + 1/refill_rate
            cls.token_hash[key] = (current_token, current_time)
            return False, 0


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

    refill_and_decr_lua_script = """
            local key = KEYS[1]
            local refill_rate = tonumber(ARGV[1])
            local current_time = tonumber(ARGV[2])
            local allowed_tokens = tonumber(ARGV[3])
            local last_tokens = tonumber(redis.call("HGET", key, "tokens")) or allowed_tokens   
            local last_refill_time = tonumber(redis.call("HGET", key, "last_refill_time")) or current_time
            local seconds_elapsed = current_time - last_refill_time
            local current_tokens = math.min(allowed_tokens, last_tokens + math.floor(refill_rate * seconds_elapsed))
            local is_rate_limited = 1
            if current_tokens > 0 then 
            redis.call("HSET", key, "tokens", current_tokens - 1)
            redis.call("HSET", key, "last_refill_time", current_time)
            is_rate_limited = 0
            end
            return {is_rate_limited, current_tokens}
        """

    add_to_set = redis_client.register_script(add_to_sorted_set_lua_script)
    refill_and_decr = redis_client.register_script(refill_and_decr_lua_script)

    @classmethod
    def user_based_increment_key(cls, key, ttl):
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


    @classmethod
    def increment_counter_key(cls, key):
        return cls.redis_client.incr(key)

    @classmethod
    def get_counter(cls, key):
        return cls.redis_client.get(key) or 0


    @classmethod
    def refill_and_decr_token(cls, key, refill_rate, allowed_token):
        """
            Uses lua script to atomically update the bucket according to the tokens that need to be added
            Caps them to allowed_token
            if the total token > 0 then decrement 1 and rate_limited as False
            otherwise set rate_limited to true
        """
        keys = [key]
        args = [refill_rate, int(time.time()), allowed_token]
        return cls.refill_and_decr(keys=keys, args=args)
