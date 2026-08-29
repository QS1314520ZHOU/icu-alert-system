"""Redis 缓存实现。"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

logger = logging.getLogger(__name__)

# 全局 Redis 连接
_redis: Optional[redis.Redis] = None


async def connect(redis_url: str = "redis://localhost:6379"):
    """连接到 Redis。"""
    global _redis

    try:
        _redis = redis.from_url(redis_url, decode_responses=True)
        await _redis.ping()
        logger.info(f"成功连接到 Redis: {redis_url}")
    except Exception as e:
        logger.error(f"连接 Redis 失败: {e}")
        _redis = None


async def disconnect():
    """断开 Redis 连接。"""
    global _redis

    if _redis:
        await _redis.close()
        _redis = None
        logger.info("已断开 Redis 连接")


class RedisCache:
    """Redis 缓存类。"""

    def __init__(self, prefix: str = "icu"):
        self.prefix = prefix

    def _make_key(self, key: str) -> str:
        """生成完整的缓存键。"""
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值。"""
        if not _redis:
            return None

        try:
            value = await _redis.get(self._make_key(key))
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"获取缓存失败: {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        expire: int = 300  # 默认 5 分钟
    ) -> bool:
        """设置缓存值。"""
        if not _redis:
            return False

        try:
            serialized = json.dumps(value, ensure_ascii=False)
            await _redis.set(self._make_key(key), serialized, ex=expire)
            return True
        except Exception as e:
            logger.error(f"设置缓存失败: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """删除缓存。"""
        if not _redis:
            return False

        try:
            await _redis.delete(self._make_key(key))
            return True
        except Exception as e:
            logger.error(f"删除缓存失败: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """检查缓存是否存在。"""
        if not _redis:
            return False

        try:
            return await _redis.exists(self._make_key(key)) > 0
        except Exception as e:
            logger.error(f"检查缓存失败: {e}")
            return False

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """递增计数器。"""
        if not _redis:
            return None

        try:
            return await _redis.incr(self._make_key(key), amount)
        except Exception as e:
            logger.error(f"递增计数器失败: {e}")
            return None

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """批量获取缓存。"""
        if not _redis:
            return {}

        try:
            full_keys = [self._make_key(key) for key in keys]
            values = await _redis.mget(full_keys)
            result = {}
            for key, value in zip(keys, values):
                if value:
                    result[key] = json.loads(value)
            return result
        except Exception as e:
            logger.error(f"批量获取缓存失败: {e}")
            return {}

    async def set_many(
        self,
        mapping: dict[str, Any],
        expire: int = 300
    ) -> bool:
        """批量设置缓存。"""
        if not _redis:
            return False

        try:
            pipe = _redis.pipeline()
            for key, value in mapping.items():
                serialized = json.dumps(value, ensure_ascii=False)
                pipe.set(self._make_key(key), serialized, ex=expire)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"批量设置缓存失败: {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """清除匹配模式的缓存。"""
        if not _redis:
            return 0

        try:
            full_pattern = self._make_key(pattern)
            keys = []
            async for key in _redis.scan_iter(match=full_pattern):
                keys.append(key)

            if keys:
                return await _redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
            return 0


# 全局缓存实例
cache = RedisCache()


def get_cache() -> RedisCache:
    """获取缓存实例。"""
    return cache
