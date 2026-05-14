# Chronos 轨迹预测展示

## 接口契约

前端启动后按需读取只读配置：

- `GET /api/runtime/public-config/trajectory`
- 返回字段：`enabled`、`horizon_hours`、`default_codes`
- 服务端缓存 5 分钟，只暴露非敏感配置。

患者详情趋势页首次激活时请求预测：

- `GET /api/patients/{patient_id}/vitals/forecast`
- 参数：`codes=HR,MAP,SpO2,RR,Temp`，`horizon_hours=1..12`
- 响应使用 `series[code].forecast[].{time|timestamp, mean, lower, upper}`，顶层 `source` 为 `chronos` 或 `heuristic`。

患者总览不请求 forecast，不渲染预测 sparkline，避免拖慢列表首屏。

## 前端状态机

`useVitalForecast` 管理五态：

- `idle`：未进入趋势页或配置关闭。
- `loading`：首次预测请求中。
- `ready`：已有可展示预测数据。
- `refreshing`：已有旧数据，后台刷新中。
- `error`：接口失败且一次静默重试后仍不可用。

历史趋势先渲染，预测请求异步叠加。接口失败只显示灰色状态 chip，不弹全局错误，不影响历史曲线。

## 缓存与并发

缓存 key：

`patientId + trendWindow + horizon + codes_sorted + historyLastTs`

策略：

- TTL 30 秒。
- Pinia/组合式模块内 Map 缓存，最多 20 条，超出按插入顺序淘汰。
- 患者切换、趋势窗口切换、卸载时 abort 旧请求。
- 回写前同时校验 AbortController 与单调递增请求序号，避免快速切换患者后的数据串扰。

## 展示语义

历史曲线为实线，预测曲线为同色系虚线。预测首点使用历史末点时间形成视觉衔接；MAP 历史口径为 `ibp_map ?? nibp_map`，tooltip 标注“IBP/NIBP 合并”。

质量正常时显示 80% 置信区间淡色填充；`quality.level=low` 或历史数据不足时只显示均值虚线，并在状态 chip 标注“数据不足”。

状态 chip：

- `chronos`：绿色，显示 `Chronos · {horizon}h预测 · {HH:mm} 生成`。
- `heuristic`：黄色，显示 `线性外推 · {horizon}h预测 · 模型未加载`。
- `error`：灰色，显示 `预测暂不可用`。
- `enabled=false`：不显示 chip，不发请求。

## 降级语义

后端 fallback reason：

- `model_not_loaded`：Chronos 模型未加载。
- `insufficient_history`：历史数据不足。
- `model_inference_error`：模型推理失败。

前端 popover 直接展示降级原因，用于床旁排障和运维定位。

## 可观测性

前端通过 `icu-forecast-event` 派发事件，事件名前缀 `forecast.`：

- `request`
- `success`
- `fallback_used`
- `error`
- `cache_hit`
- `aborted_by_patient_switch`
- `invalid_horizon`

事件附带 patientId、horizon、latency_ms、source、quality_level 等字段。生产环境可由现有埋点桥接监听该浏览器事件后上报。
