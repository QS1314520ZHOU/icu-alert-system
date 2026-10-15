<template>
  <div class="reviews-page">
    <!-- 统计卡 -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-label">待临床确认</div>
        <div class="stat-value">{{ stats.pending }}</div>
      </div>
      <div class="stat-card stat-card--info">
        <div class="stat-label">审核中</div>
        <div class="stat-value">{{ stats.reviewing }}</div>
      </div>
      <div class="stat-card stat-card--success">
        <div class="stat-label">已通过</div>
        <div class="stat-value">{{ stats.approved }}</div>
      </div>
      <div class="stat-card stat-card--danger">
        <div class="stat-label">已拒绝</div>
        <div class="stat-value">{{ stats.rejected }}</div>
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
import { ref, computed, onMounted, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { getReviews, getReviewDetail, approveReview, rejectReview } from '../../api/diseaseCenter'

// 状态
const activeTab = ref('pending')

// 统计（从列表实时计算，避免与真实数据脱节）
const stats = computed(() => {
  const s = { pending: 0, reviewing: 0, approved: 0, rejected: 0 }
  for (const r of reviews.value) {
    if (r.status === 'pending') s.pending++
    else if (r.status === 'reviewing' || r.status === 'changes_requested') s.reviewing++
    else if (r.status === 'approved') s.approved++
    else if (r.status === 'rejected') s.rejected++
  }
  return s
})

// 标签
const tabs = computed(() => [
  { key: 'all', label: '全部', count: reviews.value.length },
  { key: 'pending', label: '待临床确认', count: stats.value.pending },
  { key: 'reviewing', label: '确认中', count: stats.value.reviewing },
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
  const map: Record<string, string> = { pending: '待临床确认', reviewing: '确认中', approved: '已通过', rejected: '已拒绝', changes_requested: '需修改' }
  return map[status] || status
}

// 状态标签
function statusLabel(status: string) {
  const map: Record<string, string> = { pending: '待临床确认', reviewing: '确认中', approved: '已通过', rejected: '已拒绝' }
  return map[status] || ''
}

// 查看详情
async function viewDetail(item: ReviewItem) {
  let detail: ReviewItem = item
  try {
    const { data } = await getReviewDetail(item.id)
    detail = { ...item, ...data }
  } catch (e: any) {
    message.error('获取审核详情失败: ' + (e?.message || '未知错误'))
  }
  const rows: Array<[string, string]> = [
    ['资源类型', resourceTypeText(detail.resource_type)],
    ['资源ID', detail.resource_id],
    ['资源版本', detail.resource_version || '-'],
    ['状态', statusText(detail.status)],
    ['提交人', detail.submitter_id],
    ['提交时间', detail.submitted_at],
    ['审核人', detail.reviewer_id || '-'],
    ['审核时间', detail.reviewed_at || '-'],
  ]
  const renderRow = (k: string, v: string) =>
    h('div', { style: 'display:flex;gap:8px;margin-bottom:6px;align-items:flex-start;' }, [
      h('span', { style: 'min-width:70px;color:#667085;flex-shrink:0;' }, k),
      h('span', { style: 'word-break:break-all;' }, v),
    ])
  const extra: Array<ReturnType<typeof renderRow>> = []
  if (detail.review_comment) extra.push(renderRow('审核意见', detail.review_comment))
  if (detail.change_request) extra.push(renderRow('修改要求', detail.change_request))
  if (detail.diff) extra.push(renderRow('差异', detail.diff))
  Modal.info({
    title: '审核详情',
    content: () => h('div', [...rows.map(([k, v]) => renderRow(k, v)), ...extra]),
    okText: '关闭',
    width: 560,
  })
}

// 通过
function approveItem(item: ReviewItem) {
  Modal.confirm({
    title: '审核确认',
    content: `确认通过 "${resourceTypeText(item.resource_type)}" 审核？`,
    okText: '确认',
    cancelText: '取消',
    async onOk() {
      try {
        await approveReview(item.id, item.reviewer_id || item.submitter_id || '')
        item.status = 'approved'
        message.success('审核通过')
      } catch (e: any) {
        message.error('审核失败: ' + (e?.message || '未知错误'))
        throw e
      }
    },
  })
}

// 拒绝
function rejectItem(item: ReviewItem) {
  let comment = ''
  Modal.confirm({
    title: '拒绝确认',
    content: () =>
      h('div', [
        h('p', `确认拒绝 "${resourceTypeText(item.resource_type)}" 审核？`),
        h('textarea', {
          placeholder: '拒绝原因（必填）',
          style: 'width:100%;min-height:72px;padding:6px 8px;border:1px solid #d9d9d9;border-radius:4px;',
          onInput: (e: Event) => {
            comment = (e.target as HTMLTextAreaElement).value
          },
        }),
      ]),
    okText: '确认拒绝',
    cancelText: '取消',
    async onOk() {
      if (!comment.trim()) {
        message.warning('请填写拒绝原因')
        throw new Error('comment required')
      }
      try {
        await rejectReview(item.id, item.reviewer_id || item.submitter_id || '', comment.trim())
        item.status = 'rejected'
        item.review_comment = comment.trim()
        message.success('已拒绝')
      } catch (e: any) {
        message.error('拒绝失败: ' + (e?.message || '未知错误'))
        throw e
      }
    },
  })
}

// 修改后通过（发送修改意见，后端会记录意见并将资源置为需修改）
function requestChanges(item: ReviewItem) {
  let comment = ''
  Modal.confirm({
    title: '发送修改意见',
    content: () =>
      h('div', [
        h('p', `为 "${resourceTypeText(item.resource_type)}" 审核填写修改意见：`),
        h('textarea', {
          placeholder: '修改意见（必填）',
          style: 'width:100%;min-height:72px;padding:6px 8px;border:1px solid #d9d9d9;border-radius:4px;',
          onInput: (e: Event) => {
            comment = (e.target as HTMLTextAreaElement).value
          },
        }),
      ]),
    okText: '发送',
    cancelText: '取消',
    async onOk() {
      if (!comment.trim()) {
        message.warning('请填写修改意见')
        throw new Error('comment required')
      }
      try {
        await rejectReview(item.id, item.reviewer_id || item.submitter_id || '', comment.trim())
        item.status = 'rejected'
        item.review_comment = comment.trim()
        message.success('已发送修改意见')
      } catch (e: any) {
        message.error('发送失败: ' + (e?.message || '未知错误'))
        throw e
      }
    },
  })
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

<style scoped>.reviews-page { display: flex; flex-direction: column; gap: 20px }

/* 统计卡 */ .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px }
.stat-card { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); padding: 14px 16px; text-align: center }
.stat-value { font-size: var(--text-metric-key, 26px); font-weight: 700; color: var(--color-text-primary, #111827); line-height: 1.15; font-variant-numeric: tabular-nums }
.stat-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); margin-bottom: 4px }
.stat-card--info .stat-value { color: var(--color-primary, #2563EB) }
.stat-card--success .stat-value { color: var(--color-success, #16845B) }
.stat-card--danger .stat-value { color: var(--color-danger, #D92D20) }

/* 筛选栏 */ .filter-bar { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB); padding: 8px 12px }
.filter-tabs { display: flex; gap: 4px }
.tab-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; font-size: var(--text-body, 13px); font-weight: 500; border: none; border-radius: var(--radius-md, 6px); background: transparent; color: var(--color-text-secondary, #4B5563); cursor: pointer; transition: all 0.15s }
.tab-btn:hover { background: var(--color-bg-surface-secondary, #F1F4F8); color: var(--color-text-primary, #111827) }
.tab-btn--active { background: var(--color-primary, #2563EB); color: var(--color-text-inverse, #FFFFFF) }
.tab-count { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; padding: 0 4px; font-size: var(--text-caption, 12px); font-weight: 600; border-radius: var(--radius-md, 6px); background: rgba(0, 0, 0, 0.1) }
.tab-btn--active .tab-count { background: rgba(255, 255, 255, 0.3) }

/* 审核列表 */ .review-list { display: flex; flex-direction: column; gap: 12px }
.review-card { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); overflow: hidden }
.review-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--color-divider, #F0F2F5) }
.review-type { display: flex; align-items: center; gap: 8px }
.type-icon { font-size: 16px }
.type-text { font-size: var(--text-caption, 12px); font-weight: 500; color: var(--color-text-secondary, #4B5563) }

/* 状态徽章 */ .status-badge { display: inline-flex; padding: 2px 10px; font-size: var(--text-caption, 12px); font-weight: 500; border-radius: var(--radius-tag, 4px) }
.status-badge--pending { color: var(--color-warning, #B54708); background: rgba(181, 71, 8, 0.1) }
.status-badge--reviewing { color: var(--color-primary, #2563EB); background: rgba(37, 99, 235, 0.1) }
.status-badge--approved { color: var(--color-success, #16845B); background: rgba(22, 132, 91, 0.1) }
.status-badge--rejected { color: var(--color-danger, #D92D20); background: rgba(217, 45, 32, 0.1) }
.review-body { padding: 16px }
.review-title { font-size: var(--text-section-title, 15px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 0 6px }
.review-desc { font-size: var(--text-body, 13px); color: var(--color-text-secondary, #4B5563); margin: 0 0 12px; line-height: 1.5 }

/* 元数据 */ .review-meta { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 12px }
.meta-item { display: flex; align-items: center; gap: 6px }
.meta-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.meta-value { font-size: var(--text-caption, 12px); color: var(--color-text-primary, #111827); font-weight: 500 }
.meta-value--code { font-family: 'SF Mono', 'Consolas', monospace; font-size: var(--text-caption, 12px); padding: 1px 4px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-tag, 4px) }

/* 影响范围 */ .review-impact { padding: 10px 12px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px); margin-bottom: 12px }
.impact-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.impact-text { font-size: var(--text-caption, 12px); color: var(--color-text-primary, #111827); font-weight: 500 }

/* 变更内容 */ .review-changes { padding: 12px; border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px) }
.changes-title { font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 0 8px }
.changes-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 6px }
.change-item { display: flex; align-items: center; gap: 8px; font-size: var(--text-caption, 12px) }
.change-type { display: inline-flex; padding: 1px 6px; font-size: var(--text-caption, 12px); font-weight: 500; border-radius: var(--radius-tag, 4px); min-width: 32px; justify-content: center }
.change-type--新增 { color: var(--color-success, #16845B); background: rgba(22, 132, 91, 0.1) }
.change-type--修改 { color: var(--color-warning, #B54708); background: rgba(181, 71, 8, 0.1) }
.change-type--删除 { color: var(--color-danger, #D92D20); background: rgba(217, 45, 32, 0.1) }
.change-text { color: var(--color-text-primary, #111827) }

/* 操作栏 */ .review-footer { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; background: var(--color-bg-surface-secondary, #F1F4F8); border-top: 1px solid var(--color-divider, #F0F2F5) }
.footer-actions { display: flex; gap: 8px }

/* 空状态 */ .empty-state { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 60px 20px; text-align: center }
.empty-icon { font-size: 48px; opacity: 0.4 }
.empty-text { font-size: var(--text-body, 13px); color: var(--color-text-secondary, #4B5563) }

/* 按钮 */ .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 14px; font-size: var(--text-body, 13px); font-weight: 500; border-radius: var(--radius-md, 6px); cursor: pointer; transition: all 0.15s; border: 1px solid transparent; white-space: nowrap }
.btn--outline { background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); border-color: var(--color-border, #E5E7EB) }
.btn--outline:hover { background: var(--color-bg-surface-secondary, #F1F4F8); border-color: var(--color-border-strong, #D1D5DB) }
.btn--outline.btn--danger { color: var(--color-danger, #D92D20); border-color: rgba(217, 45, 32, 0.3) }
.btn--outline.btn--danger:hover { background: rgba(217, 45, 32, 0.04) }
.btn--primary { background: var(--color-primary, #2563EB); color: var(--color-text-inverse, #FFFFFF); border-color: var(--color-primary, #2563EB) }
.btn--primary:hover { background: var(--color-primary-hover, #3B82F6) }

/* 响应式 */

@media (max-width: 768px) {.stats-row { grid-template-columns: repeat(2, 1fr) }
.filter-tabs { overflow-x: auto }
.review-meta { flex-direction: column; gap: 8px }
.review-footer { flex-direction: column; gap: 12px }
.footer-actions { width: 100% }
.footer-actions .btn { flex: 1 }

}

</style>
