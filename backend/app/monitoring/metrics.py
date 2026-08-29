"""Prometheus 指标收集。"""

from __future__ import annotations

import time
from typing import Optional

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST


# HTTP 请求指标
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

# 数据库查询指标
DB_QUERY_COUNT = Counter(
    "db_queries_total",
    "Total database queries",
    ["collection", "operation"]
)

DB_QUERY_LATENCY = Histogram(
    "db_query_duration_seconds",
    "Database query latency",
    ["collection", "operation"],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5]
)

# 缓存指标
CACHE_HIT_COUNT = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["key_prefix"]
)

CACHE_MISS_COUNT = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["key_prefix"]
)

# 错误指标
ERROR_COUNT = Counter(
    "errors_total",
    "Total errors",
    ["type", "endpoint"]
)

# 活跃连接指标
ACTIVE_CONNECTIONS = Gauge(
    "active_connections",
    "Number of active connections",
    ["type"]
)

# 业务指标
DISEASE_COUNT = Gauge(
    "diseases_total",
    "Total number of diseases",
    ["status"]
)

USER_COUNT = Gauge(
    "users_total",
    "Total number of users",
    ["role"]
)

ALERT_COUNT = Gauge(
    "alerts_total",
    "Total number of alerts",
    ["severity"]
)


class MetricsCollector:
    """指标收集器。"""

    @staticmethod
    def record_request(method: str, endpoint: str, status: int, duration: float):
        """记录 HTTP 请求。"""
        REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status)).inc()
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

    @staticmethod
    def record_db_query(collection: str, operation: str, duration: float):
        """记录数据库查询。"""
        DB_QUERY_COUNT.labels(collection=collection, operation=operation).inc()
        DB_QUERY_LATENCY.labels(collection=collection, operation=operation).observe(duration)

    @staticmethod
    def record_cache_hit(key_prefix: str):
        """记录缓存命中。"""
        CACHE_HIT_COUNT.labels(key_prefix=key_prefix).inc()

    @staticmethod
    def record_cache_miss(key_prefix: str):
        """记录缓存未命中。"""
        CACHE_MISS_COUNT.labels(key_prefix=key_prefix).inc()

    @staticmethod
    def record_error(error_type: str, endpoint: str):
        """记录错误。"""
        ERROR_COUNT.labels(type=error_type, endpoint=endpoint).inc()

    @staticmethod
    def set_active_connections(connection_type: str, count: int):
        """设置活跃连接数。"""
        ACTIVE_CONNECTIONS.labels(type=connection_type).set(count)

    @staticmethod
    def set_disease_count(status: str, count: int):
        """设置病种数量。"""
        DISEASE_COUNT.labels(status=status).set(count)

    @staticmethod
    def set_user_count(role: str, count: int):
        """设置用户数量。"""
        USER_COUNT.labels(role=role).set(count)

    @staticmethod
    def set_alert_count(severity: str, count: int):
        """设置告警数量。"""
        ALERT_COUNT.labels(severity=severity).set(count)

    @staticmethod
    def get_metrics() -> bytes:
        """获取所有指标。"""
        return generate_latest()


# 全局指标收集器实例
metrics_collector = MetricsCollector()


def get_metrics() -> bytes:
    """获取指标数据。"""
    return metrics_collector.get_metrics()


def record_request(method: str, endpoint: str, status: int, duration: float):
    """记录请求。"""
    metrics_collector.record_request(method, endpoint, status, duration)


def record_error(error_type: str, endpoint: str):
    """记录错误。"""
    metrics_collector.record_error(error_type, endpoint)


def record_db_query(collection: str, operation: str, duration: float):
    """记录数据库查询。"""
    metrics_collector.record_db_query(collection, operation, duration)


def record_cache_hit(key_prefix: str):
    """记录缓存命中。"""
    metrics_collector.record_cache_hit(key_prefix)


def record_cache_miss(key_prefix: str):
    """记录缓存未命中。"""
    metrics_collector.record_cache_miss(key_prefix)
