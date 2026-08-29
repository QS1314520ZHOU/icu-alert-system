<template>
  <div class="reviews-page">
    <!-- 统计卡 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-value">{{ stats.pending }}</div>
        <div class="stat-label">待审核</div>
      </div>
      <div class="stat-card stat-card--info">
        <div class="stat-value">{{ stats.reviewing }}</div>
        <div class="stat-label">审核中</div>
      </div>
      <div class="stat-card stat-card--success">
        <div class="stat-value">{{ stats.approved }}</div>
        <div class="stat-label">已通过</div>
      </div>
      <div class="stat-card stat-card--danger">
        <div class="stat-value">{{ stats.rejected }}</div>
        <div class="stat-label">已拒绝</div>
      </div>
    </div>

    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="filter-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['tab-btn', { 'tab-btn--active': activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span v-if="tab.count" class="tab-count">{{ tab.count }}</span>
        </button>
      </div>
    </div>

    <!-- 审核列表 -->
    <div class="review-list">
      <div v-for="item in filteredReviews" :key="item.id" class="review-card">
        <div class="review-header">
          <div class="review-type">
            <span class="type-icon">{{ typeIcon(item.resource_type) }}</span>
            <span class="type-text">{{ resourceTypeText(item.resource_type) }}</span>
          </div>
          <span :class="['status-badge', `status-badge--${item.status}`]">{{ statusText(item.status) }}</span>
        </div>

        <div class="review-body">
          <h4 class="review-title">{{ resourceTypeText(item.resource_type) }}审核</h4>
          <p class="review-desc">资源ID: {{ item.resource_id }}</p>

          <div class="review-meta">
            <div class="meta-item">
              <span class="meta-label">提交人</span>
              <span class="meta-value">{{ item.submitter_id }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">提交时间</span>
              <span class="meta-value">{{ item.submitted_at }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">版本</span>
              <span class="meta-value meta-value--code">{{ item.resource_version }}</span>
            </div>
          </div>

          <!-- 审核意见 -->
          <div v-if="item.review_comment" class="review-impact">
            <span class="impact-label">审核意见：</span>
            <span class="impact-text">{{ item.review_comment }}</span>
          </div>

          <!-- 修改请求 -->
          <div v-if="item.change_request" class="review-impact">
            <span class="impact-label">修改要求：</span>
            <span class="impact-text">{{ item.change_request }}</span>
          </div>
        </div>

        <div v-if="item.status === 'pending' || item.status === 'reviewing'" class="review-footer">
          <button class="btn btn--outline" @click="viewDetail(item)">查看详情</button>
          <div class="footer-actions">
            <button class="btn btn--outline btn--danger" @click="rejectItem(item)">拒绝</button>
            <button class="btn btn--outline" @click="requestChanges(item)">修改后通过</button>
            <button class="btn btn--primary" @click="approveItem(item)">通过</button>
          </div>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="filteredReviews.length === 0" class="empty-state">
        <span class="empty-icon">✅</span>
        <span class="empty-text">暂无{{ activeTab === 'all' ? '' : statusLabel(activeTab) }}审核事项</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { getReviews } from '../../api/diseaseCenter'

// 状态
const activeTab = ref('pending')

// 统计
const stats = ref({ pending: 3, reviewing: 2, approved: 12, rejected: 1 })

// 标签
const tabs = computed(() => [
  { key: 'all', label: '全部', count: reviews.value.length },
  { key: 'pending', label: '待审核', count: stats.value.pending },
  { key: 'reviewing', label: '审核中', count: stats.value.reviewing },
  { key: 'approved', label: '已通过', count: stats.value.approved },
  { key: 'rejected', label: '已拒绝', count: stats.value.rejected },
])

// 审核项
interface ReviewItem {
  id: string
  resource_type: string
  resource_id: string
  resource_version: string
  status: string
  submitter_id: string
  submitted_at: string
  reviewer_id?: string
  reviewed_at?: string
  review_comment?: string
  change_request?: string
  diff?: string
}

const reviews = ref<ReviewItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

// 过滤后的列表
const filteredReviews = computed(() => {
  if (activeTab.value === 'all') return reviews.value
  return reviews.value.filter((r) => r.status === activeTab.value)
})

// 类型图标
function typeIcon(type: string) {
  const icons: Record<string, string> = { disease: '📋', rule: '📐', terminology: '📖', offline: '📦', phenotype_rule: '🧬', clinical_pathway: '🗺️', quality_indicator: '📊', scoring: '🎯' }
  return icons[type] || '📄'
}

// 资源类型文本
function resourceTypeText(type: string) {
  const map: Record<string, string> = { disease: '病种', rule: '规则', terminology: '术语', offline: '离线包', phenotype_rule: '表型规则', clinical_pathway: '临床路径', quality_indicator: '质量指标', scoring: '评分体系' }
  return map[type] || type
}

// 状态文本
function statusText(status: string) {
  const map: Record<string, string> = { pending: '待审核', reviewing: '审核中', approved: '已通过', rejected: '已拒绝', changes_requested: '需修改' }
  return map[status] || status
}

// 状态标签
function statusLabel(status: string) {
  const map: Record<string, string> = { pending: '待审核', reviewing: '审核中', approved: '已通过', rejected: '已拒绝' }
  return map[status] || ''
}

// 查看详情
function viewDetail(item: ReviewItem) {
  // TODO: 实现查看详情逻辑
  message.info(`查看详情: ${resourceTypeText(item.resource_type)} - ${item.resource_id}`)
}

// 通过
function approveItem(item: ReviewItem) {
  Modal.confirm({
    title: '审核确认',
    content: `确认通过 "${resourceTypeText(item.resource_type)}" 审核？`,
    okText: '确认',
    cancelText: '取消',
    onOk() {
      // TODO: 调用审核API
      item.status = 'approved'
      stats.value.pending--
      stats.value.approved++
      message.success('审核通过')
    },
  })
}

// 拒绝
function rejectItem(item: ReviewItem) {
  Modal.confirm({
    title: '拒绝确认',
    content: `确认拒绝 "${resourceTypeText(item.resource_type)}" 审核？`,
    okText: '确认',
    cancelText: '取消',
    onOk() {
      // TODO: 调用审核API
      item.status = 'rejected'
      stats.value.pending--
      stats.value.rejected++
      message.success('已拒绝')
    },
  })
}

// 修改后通过
function requestChanges(item: ReviewItem) {
  // TODO: 实现发送修改意见逻辑
  message.success(`已发送修改意见给 ${item.submitter_id}`)
}

// 加载数据
async function loadReviews() {
  loading.value = true
  error.value = null

  try {
    const { data } = await getReviews()
    reviews.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    error.value = e?.message || '获取审核列表失败，请稍后重试'
    reviews.value = []
  } finally {
    loading.value = false
  }
}

// 初始化
onMounted(() => {
  loadReviews()
})
</script>

<style scoped>
.reviews-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 统计卡 */
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.stat-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  padding: 16px;
  text-align: center;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  line-height: 1;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.stat-card--info .stat-value { color: var(--color-primary, #2563EB); }
.stat-card--success .stat-value { color: var(--color-success, #16845B); }
.stat-card--danger .stat-value { color: var(--color-danger, #D92D20); }

/* 筛选栏 */
.filter-bar {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  padding: 8px 12px;
}

.filter-tabs {
  display: flex;
  gap: 4px;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-secondary, #667085);
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn:hover { background: var(--color-bg-surface-secondary, #F1F3F5); color: var(--color-text-primary, #18212B); }
.tab-btn--active { background: var(--color-primary, #2563EB); color: #fff; }

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9px;
  background: rgba(0, 0, 0, 0.1);
}

.tab-btn--active .tab-count { background: rgba(255, 255, 255, 0.3); }

/* 审核列表 */
.review-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.review-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  overflow: hidden;
}

.review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.review-type {
  display: flex;
  align-items: center;
  gap: 8px;
}

.type-icon { font-size: 16px; }
.type-text { font-size: 12px; font-weight: 500; color: var(--color-text-secondary, #667085); }

/* 状态徽章 */
.status-badge { display: inline-flex; padding: 2px 10px; font-size: 11px; font-weight: 500; border-radius: 4px; }
.status-badge--pending { color: var(--color-warning, #B54708); background: rgba(181, 71, 8, 0.1); }
.status-badge--reviewing { color: var(--color-primary, #2563EB); background: rgba(37, 99, 235, 0.1); }
.status-badge--approved { color: var(--color-success, #16845B); background: rgba(22, 132, 91, 0.1); }
.status-badge--rejected { color: var(--color-danger, #D92D20); background: rgba(217, 45, 32, 0.1); }

.review-body { padding: 16px; }

.review-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0 0 6px;
}

.review-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #667085);
  margin: 0 0 12px;
  line-height: 1.5;
}

/* 元数据 */
.review-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 12px;
}

.meta-item { display: flex; align-items: center; gap: 6px; }
.meta-label { font-size: 12px; color: var(--color-text-secondary, #667085); }
.meta-value { font-size: 12px; color: var(--color-text-primary, #18212B); font-weight: 500; }
.meta-value--code { font-family: 'SF Mono', 'Consolas', monospace; font-size: 11px; padding: 1px 4px; background: var(--color-bg-surface-secondary, #F1F3F5); border-radius: 3px; }

/* 影响范围 */
.review-impact {
  padding: 10px 12px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: 6px;
  margin-bottom: 12px;
}

.impact-label { font-size: 12px; color: var(--color-text-secondary, #667085); }
.impact-text { font-size: 12px; color: var(--color-text-primary, #18212B); font-weight: 500; }

/* 变更内容 */
.review-changes {
  padding: 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: 6px;
}

.changes-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0 0 8px;
}

.changes-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.change-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.change-type {
  display: inline-flex;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 500;
  border-radius: 3px;
  min-width: 32px;
  justify-content: center;
}

.change-type--新增 { color: var(--color-success, #16845B); background: rgba(22, 132, 91, 0.1); }
.change-type--修改 { color: var(--color-warning, #B54708); background: rgba(181, 71, 8, 0.1); }
.change-type--删除 { color: var(--color-danger, #D92D20); background: rgba(217, 45, 32, 0.1); }

.change-text { color: var(--color-text-primary, #18212B); }

/* 操作栏 */
.review-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-top: 1px solid #f0f0f0;
}

.footer-actions { display: flex; gap: 8px; }

/* 空状态 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 60px 20px;
  text-align: center;
}

.empty-icon { font-size: 48px; opacity: 0.4; }
.empty-text { font-size: 14px; color: var(--color-text-secondary, #667085); }

/* 按钮 */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 14px; font-size: 13px; font-weight: 500; border-radius: 6px; cursor: pointer; transition: all 0.15s; border: 1px solid transparent; white-space: nowrap; }
.btn--outline { background: #fff; color: var(--color-text-primary, #18212B); border-color: var(--color-border, #D0D5DD); }
.btn--outline:hover { background: var(--color-bg-surface-secondary, #F9FAFB); border-color: #B0B8C4; }
.btn--outline.btn--danger { color: var(--color-danger, #D92D20); border-color: rgba(217, 45, 32, 0.3); }
.btn--outline.btn--danger:hover { background: rgba(217, 45, 32, 0.04); }
.btn--primary { background: var(--color-primary, #2563EB); color: #fff; border-color: var(--color-primary, #2563EB); }
.btn--primary:hover { background: #1D4FD8; }

/* 响应式 */
@media (max-width: 768px) {
  .stats-row { grid-template-columns: repeat(2, 1fr); }
  .filter-tabs { overflow-x: auto; }
  .review-meta { flex-direction: column; gap: 8px; }
  .review-footer { flex-direction: column; gap: 12px; }
  .footer-actions { width: 100%; }
  .footer-actions .btn { flex: 1; }
}
</style>
