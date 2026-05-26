"""
Redis 缓存连接模块

提供异步 Redis 连接池和设备状态缓存辅助函数。
设备最新状态以 JSON 形式缓存在 Redis 中，降低 PostgreSQL 高频读写压力。
"""

import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

STATUS_CACHE_KEY_PREFIX = "device:latest_status"
EXCEED_COUNT_KEY_PREFIX = "device:exceed_count"

_pool: Optional[redis.ConnectionPool] = None
_client: Optional[redis.Redis] = None


def _build_key(device_id: str) -> str:
    """构造设备状态缓存键"""
    return f"{STATUS_CACHE_KEY_PREFIX}:{device_id}"


def _build_exceed_key(device_id: str, metric_name: str) -> str:
    """构造指标超出计数缓存键"""
    return f"{EXCEED_COUNT_KEY_PREFIX}:{device_id}:{metric_name}"


def get_redis_client() -> redis.Redis:
    """
    获取 Redis 异步客户端 (单例)

    首次调用时创建连接池和客户端，后续调用复用同一实例。

    Returns:
        redis.Redis: Redis 异步客户端实例
    """
    global _pool, _client
    if _client is None:
        _pool = redis.ConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            decode_responses=True,
        )
        _client = redis.Redis(connection_pool=_pool)
    return _client


async def cache_device_status(
    device_id: str,
    status_data: Dict[str, Any],
    reported_at: str,
    status_id: Optional[int] = None,
    has_alert: bool = False,
) -> bool:
    """
    将设备最新状态写入 Redis 缓存

    使用 Redis String 存储 JSON 序列化后的状态快照，
    缓存键为 device:latest_status:{device_id}，过期时间由配置决定。

    Args:
        device_id: 设备ID
        status_data: 状态数据字典
        reported_at: 上报时间 (ISO 格式字符串)
        status_id: 状态记录 ID (可选)
        has_alert: 是否包含报警

    Returns:
        bool: 是否写入成功
    """
    try:
        client = get_redis_client()
        key = _build_key(device_id)
        payload = json.dumps({
            "device_id": device_id,
            "status_data": status_data,
            "reported_at": reported_at,
            "status_id": status_id,
            "has_alert": has_alert,
        }, ensure_ascii=False)
        await client.setex(key, settings.REDIS_STATUS_CACHE_TTL, payload)
        return True
    except redis.RedisError as e:
        logger.warning("Failed to cache device status for %s: %s", device_id, e)
        return False


async def get_cached_device_status(device_id: str) -> Optional[Dict[str, Any]]:
    """
    从 Redis 缓存读取设备最新状态

    Args:
        device_id: 设备ID

    Returns:
        Optional[Dict]: 缓存的状态数据，未命中返回 None
    """
    try:
        client = get_redis_client()
        key = _build_key(device_id)
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except redis.RedisError as e:
        logger.warning("Failed to get cached device status for %s: %s", device_id, e)
        return None


async def invalidate_device_status_cache(device_id: str) -> bool:
    """
    使设备状态缓存失效

    Args:
        device_id: 设备ID

    Returns:
        bool: 是否删除成功
    """
    try:
        client = get_redis_client()
        key = _build_key(device_id)
        await client.delete(key)
        return True
    except redis.RedisError as e:
        logger.warning("Failed to invalidate cache for %s: %s", device_id, e)
        return False


async def increment_exceed_count(device_id: str, metric_name: str, ttl: Optional[int] = None) -> int:
    """
    递增指标超出阈值的连续计数

    如果键不存在，初始化为1；如果已存在，递增1。
    每次递增时刷新TTL，保证计数窗口内的连续上报有效。

    Args:
        device_id: 设备ID
        metric_name: 指标名称
        ttl: 防抖窗口TTL (秒)，默认使用配置中的值

    Returns:
        int: 当前连续超出次数
    """
    if ttl is None:
        ttl = settings.REDIS_DEBOUNCE_WINDOW_TTL
    try:
        client = get_redis_client()
        key = _build_exceed_key(device_id, metric_name)
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = await pipe.execute()
        return int(results[0])
    except redis.RedisError as e:
        logger.warning("Failed to increment exceed count for %s/%s: %s", device_id, metric_name, e)
        return 1


async def reset_exceed_count(device_id: str, metric_name: str) -> bool:
    """
    重置指标超出阈值的连续计数

    当指标恢复到正常范围时调用，清除之前的累计计数。

    Args:
        device_id: 设备ID
        metric_name: 指标名称

    Returns:
        bool: 是否重置成功
    """
    try:
        client = get_redis_client()
        key = _build_exceed_key(device_id, metric_name)
        await client.delete(key)
        return True
    except redis.RedisError as e:
        logger.warning("Failed to reset exceed count for %s/%s: %s", device_id, metric_name, e)
        return False


async def get_exceed_count(device_id: str, metric_name: str) -> int:
    """
    获取当前指标超出阈值的连续计数

    Args:
        device_id: 设备ID
        metric_name: 指标名称

    Returns:
        int: 当前连续超出次数，未命中返回0
    """
    try:
        client = get_redis_client()
        key = _build_exceed_key(device_id, metric_name)
        raw = await client.get(key)
        if raw is None:
            return 0
        return int(raw)
    except redis.RedisError as e:
        logger.warning("Failed to get exceed count for %s/%s: %s", device_id, metric_name, e)
        return 0


async def close_redis_connection() -> None:
    """关闭 Redis 连接池"""
    global _pool, _client
    if _client is not None:
        try:
            await _client.close()
        except redis.RedisError as e:
            logger.warning("Error closing Redis client: %s", e)
        _client = None
    if _pool is not None:
        try:
            await _pool.disconnect()
        except redis.RedisError as e:
            logger.warning("Error disconnecting Redis pool: %s", e)
        _pool = None