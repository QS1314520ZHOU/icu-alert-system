# ICU Alert System — 全站重设计规范（DESIGN.md）

> 本轮改版的唯一视觉依据。所有页面改造必须符合本规范；
> 与本规范冲突的旧样式一律以本规范为准。

## 0. 改版边界

- **保留不动**：`BedSideScreen.vue`（床旁大屏）。
- **其余 88 个视图全部重设计**，包括 `BigScreen.vue`（指挥大屏可强化数据感，但必须遵守本规范色板）。
- **不改**：路由、权限、API 调用、业务逻辑、测试预期。纯视觉/结构层改造。

## 1. 风格定位

**精致的临床工作台（Clinical Workbench）**——参照 Linear / Vercel 的克制精致感，
但色彩语义是 ICU 的：安静、高信息密度、红色只留给危急。

关键词：**安静、锐利、可扫读**。
- 不用渐变背景、不用毛玻璃、不用装饰性插画。
- 层次靠「边框 + 极浅底色 + 留白」，不靠重阴影。
- 一页只有一个视觉重心（通常是关键指标或主表格）。

## 2. 色彩令牌（唯一色源）

以下值同时写入 `styles/design-system.css`（CSS 变量）与 `styles/tokens/colors.ts`。
**antd ConfigProvider 的 token 必须与本表一致**（当前 `#1D6F63` 青绿 / `#F3F1EA` 米色作废）。

### 2.1 品牌与基础

| 令牌 | 值 | 用途 |
|---|---|---|
| `--color-primary` | `#2563EB` | 主按钮、选中、链接、焦点 |
| `--color-primary-hover` | `#3B82F6` | hover |
| `--color-primary-bg` | `#EFF6FF` | 选中项浅底 |
| `--color-accent` | `#0891B2` | 数据/趋势辅助色 |
| `--color-ai` | `#7C3AED` | AI 生成内容专属色 |

### 2.2 表面

| 令牌 | 值 | 用途 |
|---|---|---|
| `--color-bg-page` | `#F6F8FB` | 页面背景（冷灰蓝） |
| `--color-bg-surface` | `#FFFFFF` | 卡片/面板 |
| `--color-bg-surface-secondary` | `#F1F4F8` | 次级底（表头、内嵌区） |
| `--color-bg-inset` | `#E9EEF5` | hover 浅底、进度槽 |

### 2.3 文字

| 令牌 | 值 |
|---|---|
| `--color-text-primary` | `#111827` |
| `--color-text-secondary` | `#4B5563` |
| `--color-text-tertiary` | `#9CA3AF` |
| `--color-text-inverse` | `#FFFFFF` |

### 2.4 边框

| 令牌 | 值 |
|---|---|
| `--color-border` | `#E5E7EB` |
| `--color-border-strong` | `#D1D5DB` |
| `--color-divider` | `#F0F2F5` |

### 2.5 临床状态色（语义不变）

| 状态 | 前景 | 浅底 | 描边 |
|---|---|---|---|
| 正常 normal | `#16A34A` | `#F0FDF4` | `#BBF7D0` |
| 警告 warning | `#D97706` | `#FFFBEB` | `#FDE68A` |
| 高危 high-risk | `#DC2626` | `#FEF2F2` | `#FECACA` |
| 危急 critical | `#991B1B` | `#FEF2F2` | `#FCA5A5` |
| 信息 info | `#0284C7` | `#E0F2FE` | `#7DD3FC` |

**规则**：状态 = 色 + 图标/文字，二者不可只留色。红色只用于危急/高危，禁止装饰性使用。

### 2.6 侧栏

| 令牌 | 值 |
|---|---|
| `--sidebar-bg` | `#FFFFFF` |
| `--sidebar-border` | `#E5E7EB` |
| 选中指示条 | `#2563EB`，3px，左侧贴边 |

## 3. 字体与字号

字体栈不变（`Noto Sans SC / Microsoft YaHei / PingFang SC`），数字仍可用 `Rajdhani`（仅监护数字）。

| 角色 | 字号/字重 |
|---|---|
| 页面标题 | 20px / 700（旧 24px 收敛，页面更紧凑） |
| 页面副标题 | 13px / 400，`--color-text-secondary` |
| 区块标题 | 15px / 600 |
| 卡片标题 | 13px / 600 |
| 正文 | 13px / 400 / lh 1.55 |
| 辅助/标签 | 12px / 500 |
| 关键指标数字 | 26px / 700，`font-variant-numeric: tabular-nums` |
| 次级指标数字 | 20px / 600 |

**所有数字必须 `tabular-nums`**，指标区必须等宽数字对齐。

## 4. 形状、间距、层次

- 圆角：卡片/面板 `10px`；控件/输入 `6px`；标签/chip `999px`（仅 chip）。
- 基础间距单位 4px。页面内边距 `20px 24px`；卡片内边距 `16px 18px`；
  卡片网格 gap `14px`；区块纵向 gap `20px`。
- 阴影：默认卡片**无阴影，1px 边框**；悬浮卡 `0 1px 3px rgba(17,24,39,.06)`；
  弹窗/下拉 `0 8px 24px rgba(17,24,39,.12)`。禁止多层重阴影。

## 5. 页面骨架（每个页面的固定结构）

```
┌ PageHeader（标题 + 副标题 + 右侧主操作，高 56px 区域） ┐
│ ActionBar / FilterBar（如有筛选，单行，控件高 32px）    │
│ 主内容网格（12 列或 CSS grid auto-fit，gap 14px）        │
│   ├ KPI 区：MetricStrip，4~6 个等宽指标卡               │
│   ├ 主区：卡片（表格/图表），占最大视觉权重              │
│   └ 侧区：次要卡片，与主区 2:1 或 3:1                    │
└─────────────────────────────────────────────────────┘
```

- **优先复用** `components/common/design-system/` 现成组件：
  `PageHeader / SectionHeader / MetricStrip / ActionBar / FilterBar /
  StatusBadge / EmptyState / LoadingState / ErrorState`。
- 页面级 `<style scoped>` 只允许写布局与本页特有样式，颜色/字号/圆角
  **必须引用 CSS 变量**（`var(--color-*)`、`var(--text-*)`、`var(--radius-*)`），
  禁止硬编码 hex（图表 echarts 配置内允许引用变量字符串）。
- 禁止页面自造一套按钮/输入样式：用 antd 组件（`a-button` 等），
  antd 主题已按本规范统一。

## 6. 数据卡片规范（KPI）

```
┌───────────────┐
│ 标签 12px 灰   │  ← 顶部，可带状态小图标
│ 数值 26px 粗   │  ← tabular-nums
│ 单位 + 环比    │  ← 12px，环比用 ↑绿/↓红（业务含义允许时）
└───────────────┘
  白底、1px 边框、10px 圆角、内边距 14px 16px
  有状态时：左侧 3px 状态色条 或 标签前状态点
```

## 7. 表格规范

- 表头：`--color-bg-surface-secondary` 底、12px/600、字色 secondary。
- 行高 44px，行分隔 `--color-divider`；hover `--color-bg-inset`。
- 数字列右对齐 + tabular-nums；状态列用 `StatusBadge`。
- 操作列固定右侧，链接式按钮（type=link）。
- 分页居右，`size="small"`。

## 8. 空态 / 加载 / 错误

统一用 design-system 的 `EmptyState / LoadingState / ErrorState`，
禁止页面自写「暂无数据」裸文本。加载用骨架或 spinner + 文案，不整页白屏。

## 9. 图表

- 统一走 `ClinicalChart` + `clinicalThemes`（已注册明/暗主题）。
- 主系列色 `#2563EB`，次系列 `#0891B2`，AI 系列 `#7C3AED`；
  状态序列用状态色。网格线 `#F0F2F5`，轴字 12px secondary。
- 图表卡片必须带 `SectionHeader`（标题 + 可选右上操作）。

## 10. 大屏（BigScreen）特别条款

指挥大屏允许深色底（`#0B1220`）以突出数据，但：
- 仍使用本规范的主色/状态色（同一套语义色，仅表面色反转）。
- 数字必须 tabular-nums + Rajdhani；关键值 ≥ 32px 允许（大屏条款豁免）。
- 不使用霓虹/发光特效，保持克制。

## 11. 禁止事项

1. 硬编码 hex（必须走变量；新增色先加进 design-system.css）。
2. 页面私造按钮/输入/标签样式（用 antd 或 design-system 组件）。
3. 装饰性红色、渐变背景、毛玻璃、重阴影、超过 10px 的大圆角（chip 除外）。
4. 普通页面出现 ≥32px 的大数字（BigScreen 与 BedSideScreen 豁免）。
5. 改动业务逻辑、API 调用、路由、测试预期。
6. 引入新 npm 依赖。

## 12. 改造每个页面的检查清单

- [ ] PageHeader 就位（标题 20px、副标题说明用途）
- [ ] KPI 用 MetricStrip / 标准指标卡
- [ ] 所有颜色/字号引用变量，无硬编码
- [ ] 状态展示色+文/图标
- [ ] 空态/加载/错误三态齐全
- [ ] 表格符合 §7
- [ ] `vue-tsc` 0 错误、`vitest` 全过
