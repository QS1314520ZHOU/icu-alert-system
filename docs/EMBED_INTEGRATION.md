# SmartCare 嵌入集成指南

本文档说明如何将 SmartCare (ICU Alert System) 通过 iframe 嵌入到宿主重症系统中。

## 1. 架构概览

```
宿主重症系统
  └─ iframe (src=".../embed.html?page=patient&id=xxx")
       └─ embed.html (桥接页，处理 postMessage 握手)
            └─ iframe (内层 SPA，加载 Vue 路由)
```

- **embed.html**：桥接层，负责与宿主系统通过 `postMessage` 握手，获取用户身份和患者信息
- **内层 iframe**：SmartCare Vue SPA，根据 `page` 参数加载对应路由

## 2. embed.html 参数说明

### 2.1 URL 参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `page` | 否 | 页面别名，默认 `patients`，见下方路由映射表 |
| `path` | 否 | 直接指定路由路径，优先级高于 `page`（如 `?path=/patient/123`） |
| `tab` | 否 | 透传给内层 SPA 的 tab 参数 |
| `hours` | 否 | 透传给内层 SPA 的时间范围参数 |

### 2.2 路由映射表（page → path）

| page 值 | 路由路径 | 需要患者 |
|---------|---------|---------|
| `patients` | `/patients` | 否 |
| `patient` | `/patient/:id` | 是 |
| `bedside` | `/bedside/:id` | 是 |
| `bigscreen` | `/bigscreen` | 否 |
| `clinical` | `/clinical-workflow` | 否 |
| `rounding` | `/rounding-sheet` | 否 |
| `respiratory` | `/respiratory-dashboard` | 否 |
| `nutrition` | `/nutrition-support` | 否 |
| `analytics` | `/analytics` | 否 |
| `ai-consult` | `/ai-consult` | 否 |
| `mdt` | `/mdt` | 否 |
| `handover` | `/handover` | 否 |
| `research` | `/research-workbench` | 否 |
| `academic` | `/academic-research` | 否 |
| `trials` | `/clinical-trials` | 否 |
| `doctor-home` | `/doctor-home` | 否 |
| `nurse-home` | `/nurse-home` | 否 |
| `admin-config` | `/admin/runtime-config` | 否 |
| `scanner-health` | `/admin/scanner-health` | 否 |
| `mobile` | `/m` | 否 |

## 3. CONFIG 配置字段

在 `embed.html` 顶部的 `CONFIG` 对象中配置（现场直接修改，无需重新 build）：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `allowedHostOrigins` | string[] | `['http://192.168.5.154', 'http://192.168.5.154:8080']` | 允许的宿主来源白名单，留空数组 + `requireOriginWhitelist=true` 会拒绝全部消息 |
| `hideChrome` | boolean | `true` | 隐藏 SmartCare 自带顶部导航（嵌入时用宿主菜单） |
| `hideFloater` | boolean | `false` | 是否隐藏 AI 悬浮球 |
| `injectToken` | boolean | `true` | 把宿主 token 加到内层请求的 Authorization 头 |
| `handshakeRetryMs` | number | `400` | Ready 重发间隔（毫秒） |
| `handshakeMaxTry` | number | `20` | 最大握手尝试次数 |
| `requireOriginWhitelist` | boolean | `true` | 白名单为空时是否拒绝全部宿主消息（true=安全默认，false=仅联调试用） |
| `allowNameBedFallback` | boolean | `false` | 是否允许仅凭姓名+床号自动跳转（false=需人工确认） |
| `standaloneAfterMs` | number | `4000` | 超时未收到消息时，无患者也先把页面渲染出来（实际生效值不会早于握手窗口结束） |

## 4. 现场部署配置

### 4.1 embed.html（前端 — 现场手改，无需重新 build）

```javascript
// 文件：frontend/public/embed.html（或部署后的 static/embed.html）
var CONFIG = {
  allowedHostOrigins: [
    'http://宿主IP',           // ← 改成实际宿主地址
    'http://宿主IP:端口'       // ← 如有非标准端口
  ],
  // ...其他配置按需调整
};
```

### 4.2 后端环境变量（SMARTCARE_EMBED_FRAME_ANCESTORS）

在 `.env`、`docker-compose.yml` 或系统环境变量中设置：

```bash
# 多个来源用逗号分隔；留空则不输出 CSP 头（内网联调默认放行）
SMARTCARE_EMBED_FRAME_ANCESTORS=http://192.168.5.154:8080,http://192.168.5.154
```

**未配置时的行为**：不输出 `Content-Security-Policy` 头，iframe 嵌入不受 CSP 限制。

**配置后的行为**：输出 `Content-Security-Policy: frame-ancestors 'self' http://192.168.5.154:8080 http://192.168.5.154;`

> ⚠️ 必须保留 `'self'`，因为内层 iframe 的父级正是同源的 embed.html，去掉会阻断自身嵌套。

> ⚠️ **重启生效**：读取发生在请求期（`os.environ.get()`），但 `.env` 文件只在进程启动时由 `dotenv` 载入 `os.environ`。因此修改 `.env` 或 `docker-compose.yml` 的环境变量后**必须重启后端进程**才生效；区别于 embed.html 的 `CONFIG`——后者是纯静态文件，可热改、刷新即生效。

## 5. 宿主 iframe 地址示例

```html
<!-- 嵌入患者列表页 -->
<iframe src="https://your-smartcare-domain/embed.html?page=patients"
        style="width:100%;height:100%;border:0"></iframe>

<!-- 嵌入指定患者详情页 -->
<iframe src="https://your-smartcare-domain/embed.html?page=patient&id=xxx"
        style="width:100%;height:100%;border:0"></iframe>

<!-- 直接指定路由 -->
<iframe src="https://your-smartcare-domain/embed.html?path=/patient/123?tab=vitals"
        style="width:100%;height:100%;border:0"></iframe>
```

## 6. 通信协议

### 6.1 握手流程

1. embed.html 加载后，向 `parent` 发送 `{ type: 'SmartCareReady' }` 消息
2. 宿主收到后，回传 `{ type: 'SmartCare', account: {...}, patient: {...}, token: '...' }`
3. embed.html 收到后，通过 `GET /api/patients/resolve` 将宿主患者信息解析为 SmartCare 的 Mongo `patient._id`，然后加载内层 SPA。当 `match_type=name_bed` 时需人工确认，不会自动跳转。

### 6.2 宿主消息格式

```json
{
  "type": "SmartCare",
  "account": {
    "user_id": "工号",
    "userName": "姓名",
    "role": "医生|护士|护士长|主任",
    "dept": "科室名",
    "dept_code": "科室编码"
  },
  "patient": {
    "mrn": "住院号",
    "hisPid": "HIS患者ID",
    "name": "患者姓名",
    "showBed": "床位号",
    "dept": "科室名",
    "deptCode": "科室编码"
  },
  "token": "可选的鉴权token"
}
```

## 7. 验收自检

### 7.1 CSP 头检查

```bash
# 未配置 SMARTCARE_EMBED_FRAME_ANCESTORS 时：应无 CSP 头
curl -sI http://127.0.0.1:8000/embed.html | grep -iE 'cache-control|content-security'
# 预期输出（无 content-security）：
# cache-control: no-cache, no-store, must-revalidate

# 配置后重启：应出现真实宿主域且不含尖括号
curl -sI http://127.0.0.1:8000/embed.html | grep -iE 'cache-control|content-security'
# 预期输出：
# cache-control: no-cache, no-store, must-revalidate
# content-security-policy: frame-ancestors 'self' http://192.168.5.154:8080 http://192.168.5.154;
```

### 7.2 Service Worker precache 检查

1. 打开 DevTools → Application → Cache Storage → workbox-precache
2. 确认列表中**没有** `embed.html`
3. 若存在，说明 `globIgnores` 未生效，需检查 `vite.config.ts` 的 workbox 配置

### 7.3 Service Worker 缓存验证

1. 打开 DevTools → Application → Service Workers
2. 点击 Unregister
3. 刷新页面，确认 embed.html 正常加载（而非白屏或旧版本）
4. 修改 `CONFIG.hideChrome` 后刷新，确认改动生效（而非被 SW 缓存的旧版本覆盖）

## 8. 故障对照表

| 症状 | 真实原因 | 排查方法 |
|------|---------|---------|
| 宿主里空白，iframe 内 Console 有 `Refused to frame` | CSP `frame-ancestors` 拦截 | 检查 `SMARTCARE_EMBED_FRAME_ANCESTORS` 是否包含宿主 origin；先看 iframe 内部 console，而非宿主主页面 |
| 改了 `CONFIG` 刷新无变化 | Service Worker 缓存了旧版 embed.html | 检查 DevTools → Application → Cache Storage，确认 `globIgnores: ['embed.html']` 已生效；Unregister SW 后重试 |
| 打开 embed.html 显示的却是主页 | catch-all 路由顺序错误或 `navigateFallbackDenylist` 缺失 | 确认 main.py 中「先判断文件存在再 fallback index.html」的顺序；确认 workbox 配置了 `navigateFallbackDenylist` |
| 新版部署后首次打开 embed.html 显示主页 | 旧 Service Worker 的 `navigateFallback` 尚未交接 | 硬刷新一次（Ctrl+Shift+R）即可；`registerSW({ immediate: true })` + 60s 更新周期会在之后自动收敛 |
| 点了菜单却总跳到总览 | `account.role` 未映射成 `doctor/nurse/head_nurse/director`，被 `router.beforeEach` 的 `meta.roles` 守卫重定向 | 检查宿主发送的 role 值是否在 `embed.html` 的 `ROLE_MAP` 中；确认映射后的角色与路由 meta.roles 匹配 |
| 一直停在"正在与重症系统握手…" | 宿主未监听 message 事件 / origin 不匹配 / 宿主未回复 SmartCare 消息 | 检查宿主代码是否有 `window.addEventListener('message', ...)`；检查 `CONFIG.allowedHostOrigins` 是否包含宿主实际 origin |
| 嵌入后顶部导航没隐藏 | `CONFIG.hideChrome` 为 false 或 CSS 选择器失效 | 确认 `CONFIG.hideChrome` 为 `true`；检查 `.hdr` 类名是否仍存在 |
| 一直提示未匹配到患者，但患者确实在科 | 宿主未传 mrn/hisPid，或 dept_code 收窄过头 | 直接 curl `/api/patients/resolve?mrn=xxx` 看返回，确认后端能匹配到 |
| Console 报已拒绝全部宿主消息 | `allowedHostOrigins` 为空且 `requireOriginWhitelist=true` | 在 CONFIG 中填入宿主真实 origin，或联调时设 `requireOriginWhitelist: false` |

## 9. 安全注意事项

1. 空数组在 `requireOriginWhitelist=true` 时会直接拒绝全部消息；生产环境必须填入真实宿主 origin
2. **token** 仅保存在内存中，不会持久化到 localStorage
3. 建议在生产环境启用 HTTPS
4. CSP 的 `frame-ancestors` 指令仅允许指定来源嵌入
5. embed.html 设置了 `Cache-Control: no-cache`，确保现场修改后刷新即可生效
