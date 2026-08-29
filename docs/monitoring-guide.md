# 监控指南

## 概述

ICU Alert System 使用 Prometheus + Grafana 进行监控和告警。

## 架构

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   ICU Backend   │────▶│   Prometheus    │────▶│     Grafana     │
│   /metrics      │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌─────────────────┐
                        │   Alertmanager  │
                        └─────────────────┘
```

## 启动监控

```bash
# 启动监控服务
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# 访问 Grafana
# URL: http://localhost:3000
# 用户名: admin
# 密码: admin

# 访问 Prometheus
# URL: http://localhost:9090
```

## 指标说明

### HTTP 请求指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `http_requests_total` | Counter | HTTP 请求总数 |
| `http_request_duration_seconds` | Histogram | 请求延迟 |

### 数据库指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `db_queries_total` | Counter | 数据库查询总数 |
| `db_query_duration_seconds` | Histogram | 查询延迟 |

### 缓存指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `cache_hits_total` | Counter | 缓存命中总数 |
| `cache_misses_total` | Counter | 缓存未命中总数 |

### 业务指标

| 指标名称 | 类型 | 说明 |
|---------|------|------|
| `diseases_total` | Gauge | 病种总数 |
| `users_total` | Gauge | 用户总数 |
| `alerts_total` | Gauge | 告警总数 |

## 告警规则

### 高错误率告警

```yaml
groups:
  - name: icu-alert
    rules:
      - alert: HighErrorRate
        expr: rate(errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "高错误率告警"
          description: "错误率超过 10%"
```

### 高延迟告警

```yaml
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "高延迟告警"
          description: "P95 延迟超过 1 秒"
```

### 数据库连接告警

```yaml
      - alert: DatabaseDown
        expr: up{job="mongodb"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "数据库连接失败"
          description: "MongoDB 连接断开"
```

## Grafana 仪表板

### 导入仪表板

1. 登录 Grafana
2. 点击 "+" -> "Import"
3. 上传 `monitoring/grafana/dashboards/icu-alert.json`
4. 选择 Prometheus 数据源

### 仪表板面板

1. **HTTP Requests per Second**: 每秒请求数
2. **Request Latency**: 请求延迟 (P50, P95)
3. **Error Rate**: 错误率
4. **Database Queries**: 数据库查询
5. **Cache Hit Rate**: 缓存命中率
6. **Active Connections**: 活跃连接数
7. **Total Diseases**: 病种总数
8. **Total Alerts**: 告警总数

## 日志监控

### 日志级别

- DEBUG: 调试信息
- INFO: 一般信息
- WARNING: 警告信息
- ERROR: 错误信息
- CRITICAL: 严重错误

### 日志收集

```bash
# 查看后端日志
docker-compose logs -f backend

# 查看错误日志
docker-compose logs -f backend | grep ERROR
```

## 性能监控

### 关键指标

1. **响应时间**: P50 < 200ms, P95 < 500ms
2. **错误率**: < 1%
3. **可用性**: > 99.9%
4. **吞吐量**: 根据业务需求调整

### 性能优化建议

1. **缓存优化**
   - 热点数据缓存
   - 合理设置过期时间
   - 监控缓存命中率

2. **数据库优化**
   - 添加索引
   - 优化查询
   - 连接池配置

3. **代码优化**
   - 异步处理
   - 批量操作
   - 减少 N+1 查询

## 故障排查

### 常见问题

1. **服务不可用**
   - 检查容器状态: `docker-compose ps`
   - 查看日志: `docker-compose logs -f`
   - 检查资源使用: `docker stats`

2. **高延迟**
   - 检查数据库连接
   - 检查缓存状态
   - 分析慢查询

3. **内存溢出**
   - 检查内存使用
   - 分析内存泄漏
   - 调整容器限制

### 告警处理

1. **收到告警**
   - 确认告警级别
   - 检查相关服务
   - 分析根本原因

2. **处理流程**
   - 评估影响范围
   - 执行修复操作
   - 验证修复结果
   - 记录处理过程

## 最佳实践

1. **监控覆盖**
   - 覆盖所有关键服务
   - 监控业务指标
   - 设置合理阈值

2. **告警管理**
   - 避免告警疲劳
   - 设置告警升级
   - 定期审查规则

3. **数据保留**
   - 设置合理的保留期
   - 定期清理旧数据
   - 备份重要数据
