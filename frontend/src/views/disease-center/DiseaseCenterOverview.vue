<template>
  <div class="overview-page">
    <!-- 指标卡行 -->
    <div class="metrics-row">
      <div v-for="metric in metrics" :key="metric.label" :class="['metric-card', `metric-card--${metric.variant || 'default'}`]">
        <div class="metric-card__label">{{ metric.label }}</div>
        <div class="metric-card__value">
          <span class="metric-card__number">{{ metric.value }}</span>
          <span v-if="metric.unit" class="metric-card__unit">{{ metric.unit }}</span>
        </div>
        <div v-if="metric.trend" :class="['metric-card__trend', `metric-card__trend--${metric.trend}`]">
          <svg v-if="metric.trend === 'up'" width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 2L10 7H2L6 2Z" fill="currentColor"/>
          </svg>
          <svg v-else-if="metric.trend === 'down'" width="12" height="12" viewBox="0 0 12 12" fill="none">
            <path d="M6 10L2 5H10L6 10Z" fill="currentColor"/>
          </svg>
          <span v-if="metric.trendValue" class="metric-card__trend-value">{{ metric.trendValue }}</span>
        </div>
      </div>
    </div>

    <!-- 数据区 -->
    <div class="content-grid">
      <!-- 左侧 -->
      <div class="content-left">
        <!-- 病种分类分布 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">病种分类分布</h3>
          </div>
          <div class="card__body">
            <div class="category-list">
              <div v-for="cat in categories" :key="cat.name" class="category-item">
                <div class="category-item__info">
                  <span class="category-item__name">{{ cat.name }}</span>
                  <span class="category-item__count">{{ cat.count }}</span>
                </div>
                <div class="category-item__bar">
                  <div class="category-item__fill" :style="{ width: cat.percentage + '%' }"></div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 最近版本变化 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">最近版本变化</h3>
            <span class="card__action">查看全部</span>
          </div>
          <div class="card__body">
            <div class="version-list">
              <div v-for="ver in recentVersions" :key="ver.id" class="version-item">
                <div class="version-item__icon" :class="`version-item__icon--${ver.type}`">
                  {{ ver.type === 'add' ? '+' : ver.type === 'update' ? '↑' : '↓' }}
                </div>
                <div class="version-item__content">
                  <div class="version-item__name">{{ ver.name }}</div>
                  <div class="version-item__meta">{{ ver.version }} · {{ ver.time }}</div>
                </div>
                <span :class="['version-item__status', `version-item__status--${ver.status}`]">{{ ver.statusText }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧 -->
      <div class="content-right">
        <!-- 我的审核待办 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">我的审核待办</h3>
            <span class="card__badge">{{ pendingReviews.length }}</span>
          </div>
          <div class="card__body">
            <div v-if="pendingReviews.length === 0" class="empty-state">
              <span class="empty-state__icon">✅</span>
              <span class="empty-state__text">暂无待审核事项</span>
            </div>
            <div v-else class="todo-list">
              <div v-for="item in pendingReviews" :key="item.id" class="todo-item">
                <span class="todo-item__type">{{ item.type }}</span>
                <span class="todo-item__name">{{ item.name }}</span>
                <span class="todo-item__time">{{ item.time }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 离线知识包状态 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">离线知识包状态</h3>
          </div>
          <div class="card__body">
            <div class="package-status">
              <div class="package-status__item">
                <span class="package-status__label">ICD数据</span>
                <span class="package-status__value">v2024.1</span>
                <span class="package-status__dot package-status__dot--success"></span>
              </div>
              <div class="package-status__item">
                <span class="package-status__label">医学术语</span>
                <span class="package-status__value">v3.2.0</span>
                <span class="package-status__dot package-status__dot--success"></span>
              </div>
              <div class="package-status__item">
                <span class="package-status__label">指南文档</span>
                <span class="package-status__value">v1.5.0</span>
                <span class="package-status__dot package-status__dot--success"></span>
              </div>
              <div class="package-status__item">
                <span class="package-status__label">AI模型</span>
                <span class="package-status__value">v2.1.0</span>
                <span class="package-status__dot package-status__dot--warning"></span>
              </div>
            </div>
          </div>
        </div>

        <!-- 规则异常 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">规则异常</h3>
            <span class="card__badge card__badge--warning">{{ ruleIssues.length }}</span>
          </div>
          <div class="card__body">
            <div v-if="ruleIssues.length === 0" class="empty-state">
              <span class="empty-state__icon">✅</span>
              <span class="empty-state__text">规则运行正常</span>
            </div>
            <div v-else class="issue-list">
              <div v-for="issue in ruleIssues" :key="issue.id" class="issue-item">
                <span class="issue-item__level" :class="`issue-item__level--${issue.level}`">{{ issue.levelText }}</span>
                <span class="issue-item__desc">{{ issue.desc }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 本地AI运行状态 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">本地AI运行状态</h3>
          </div>
          <div class="card__body">
            <div class="ai-status">
              <div class="ai-status__item">
                <span class="ai-status__label">模型服务</span>
                <span class="ai-status__value ai-status__value--success">在线</span>
              </div>
              <div class="ai-status__item">
                <span class="ai-status__label">RAG引擎</span>
                <span class="ai-status__value ai-status__value--success">在线</span>
              </div>
              <div class="ai-status__item">
                <span class="ai-status__label">推理延迟</span>
                <span class="ai-status__value">128ms</span>
              </div>
              <div class="ai-status__item">
                <span class="ai-status__label">今日调用</span>
                <span class="ai-status__value">1,247</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Metric {
  label: string
  value: string | number
  unit?: string
  variant?: 'default' | 'info' | 'warning' | 'danger' | 'success'
  trend?: 'up' | 'down' | 'stable'
  trendValue?: string
}

// 指标卡数据
const metrics = ref<Metric[]>([
  { label: '已发布病种', value: 156 },
  { label: '标准术语', value: '2,847', variant: 'info' },
  { label: '当前评分规则', value: 24 },
  { label: '待审核', value: 3, variant: 'warning', trend: 'up', trendValue: '+2' },
  { label: '数据冲突', value: 1, variant: 'danger' },
  { label: 'AI待确认建议', value: 7, variant: 'info' },
])

// 病种分类
const categories = ref([
  { name: '感染', count: 32, percentage: 80 },
  { name: '呼吸', count: 28, percentage: 70 },
  { name: '循环', count: 24, percentage: 60 },
  { name: '神经', count: 18, percentage: 45 },
  { name: '肾脏', count: 16, percentage: 40 },
  { name: '凝血', count: 12, percentage: 30 },
  { name: '消化', count: 14, percentage: 35 },
  { name: '营养', count: 12, percentage: 30 },
])

// 最近版本变化
const recentVersions = ref([
  { id: 1, name: '脓毒症表型规则', version: 'v2.1.0', time: '2小时前', type: 'update', status: 'published', statusText: '已发布' },
  { id: 2, name: 'ARDS评分标准', version: 'v1.3.0', time: '5小时前', type: 'add', status: 'review', statusText: '审核中' },
  { id: 3, name: 'AKI诊断标准', version: 'v1.2.1', time: '1天前', type: 'update', status: 'published', statusText: '已发布' },
])

// 审核待办
const pendingReviews = ref([
  { id: 1, type: '病种', name: '急性呼吸窘迫综合征', time: '2小时前' },
  { id: 2, type: '规则', name: 'SOFA-2评分阈值调整', time: '5小时前' },
  { id: 3, type: '知识包', name: '指南更新 v2024.3', time: '1天前' },
])

// 规则异常
const ruleIssues = ref([
  { id: 1, level: 'warning', levelText: '警告', desc: 'SOFA评分缺失值率偏高 (12%)' },
])
</script>

<style scoped>
.overview-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 指标卡 */
.metrics-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 1px;
  background: var(--color-border, #E3E7EC);
  border-radius: 8px;
  overflow: hidden;
}

.metric-card {
  background: #fff;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.metric-card__label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  font-weight: 500;
}

.metric-card__value {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.metric-card__number {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  line-height: 1.2;
}

.metric-card__unit {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.metric-card__trend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
}

.metric-card__trend--up { color: var(--color-success, #16845B); }
.metric-card__trend--down { color: var(--color-danger, #D92D20); }

.metric-card--warning .metric-card__number { color: var(--color-warning, #B54708); }
.metric-card--danger .metric-card__number { color: var(--color-danger, #D92D20); }
.metric-card--info .metric-card__number { color: var(--color-primary, #2563EB); }

/* 内容网格 */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.content-left,
.content-right {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 卡片 */
.card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  overflow: hidden;
}

.card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.card__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}

.card__action {
  font-size: 12px;
  color: var(--color-primary, #2563EB);
  cursor: pointer;
}

.card__badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: var(--color-primary, #2563EB);
  border-radius: 10px;
}

.card__badge--warning {
  background: var(--color-warning, #B54708);
}

.card__body {
  padding: 16px;
}

/* 分类列表 */
.category-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.category-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.category-item__info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.category-item__name {
  font-size: 13px;
  color: var(--color-text-primary, #18212B);
}

.category-item__count {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  font-weight: 500;
}

.category-item__bar {
  height: 4px;
  background: #f0f0f0;
  border-radius: 2px;
  overflow: hidden;
}

.category-item__fill {
  height: 100%;
  background: var(--color-primary, #2563EB);
  border-radius: 2px;
  transition: width 0.3s ease;
}

/* 版本列表 */
.version-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.version-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.version-item__icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
}

.version-item__icon--add {
  background: rgba(22, 132, 91, 0.1);
  color: var(--color-success, #16845B);
}

.version-item__icon--update {
  background: rgba(37, 99, 235, 0.1);
  color: var(--color-primary, #2563EB);
}

.version-item__content {
  flex: 1;
  min-width: 0;
}

.version-item__name {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-item__meta {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  margin-top: 2px;
}

.version-item__status {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

.version-item__status--published {
  color: var(--color-success, #16845B);
  background: rgba(22, 132, 91, 0.1);
}

.version-item__status--review {
  color: var(--color-warning, #B54708);
  background: rgba(181, 71, 8, 0.1);
}

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 20px 0;
}

.empty-state__icon {
  font-size: 24px;
}

.empty-state__text {
  font-size: 13px;
  color: var(--color-text-secondary, #667085);
}

/* 待办列表 */
.todo-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.todo-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: #fafbfc;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
}

.todo-item__type {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(37, 99, 235, 0.1);
  color: var(--color-primary, #2563EB);
  white-space: nowrap;
}

.todo-item__name {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-primary, #18212B);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.todo-item__time {
  font-size: 11px;
  color: var(--color-text-secondary, #667085);
  white-space: nowrap;
}

/* 包状态 */
.package-status {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.package-status__item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.package-status__label {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-primary, #18212B);
}

.package-status__value {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary, #667085);
}

.package-status__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.package-status__dot--success {
  background: var(--color-success, #16845B);
}

.package-status__dot--warning {
  background: var(--color-warning, #B54708);
}

/* 问题列表 */
.issue-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.issue-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  border: 1px solid #f0f0f0;
}

.issue-item__level {
  font-size: 11px;
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 3px;
  white-space: nowrap;
}

.issue-item__level--warning {
  color: var(--color-warning, #B54708);
  background: rgba(181, 71, 8, 0.1);
}

.issue-item__level--error {
  color: var(--color-danger, #D92D20);
  background: rgba(217, 45, 32, 0.1);
}

.issue-item__desc {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-primary, #18212B);
}

/* AI状态 */
.ai-status {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.ai-status__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ai-status__label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.ai-status__value {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

.ai-status__value--success {
  color: var(--color-success, #16845B);
}

/* 响应式 */
@media (max-width: 1024px) {
  .metrics-row {
    grid-template-columns: repeat(3, 1fr);
  }
}

@media (max-width: 768px) {
  .metrics-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .content-grid {
    grid-template-columns: 1fr;
  }
}
</style>
