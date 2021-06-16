import os
import redis as redis_cache
import json

redis = redis_cache.Redis(
    host=os.environ.get('REDIS_HOST', 'localhost'),
    port=int(os.environ.get('REDIS_PORT', 6379)),
    db=int(os.environ.get('REDIS_DB', 0)))
redis.set_response_callback('HGET', json.loads)