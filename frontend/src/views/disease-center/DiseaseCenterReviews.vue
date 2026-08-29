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
            <span class="type-icon">{{ typeIcon(item.type) }}</span>
            <span class="type-text">{{ item.type }}</span>
          </div>
          <span :class="['status-badge', `status-badge--${item.status}`]">{{ statusText(item.status) }}</span>
        </div>

        <div class="review-body">
          <h4 class="review-title">{{ item.title }}</h4>
          <p class="review-desc">{{ item.description }}</p>

          <div class="review-meta">
            <div class="meta-item">
              <span class="meta-label">提交人</span>
              <span class="meta-value">{{ item.submitted_by }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">提交时间</span>
              <span class="meta-value">{{ item.submitted_at }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">版本变更</span>
              <span class="meta-value meta-value--code">{{ item.version_from }} → {{ item.version_to }}</span>
            </div>
          </div>

          <!-- 影响范围 -->
          <div v-if="item.impact" class="review-impact">
            <span class="impact-label">影响范围：</span>
            <span class="impact-text">{{ item.impact }}</span>
          </div>

          <!-- 版本差异 -->
          <div v-if="item.changes?.length" class="review-changes">
            <h5 class="changes-title">变更内容</h5>
            <ul class="changes-list">
              <li v-for="(change, i) in item.changes" :key="i" class="change-item">
                <span :class="['change-type', `change-type--${change.type}`]">{{ change.type }}</span>
                <span class="change-text">{{ change.text }}</span>
              </li>
            </ul>
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
import { ref, computed } from 'vue'

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
  type: string
  title: string
  description: string
  submitted_by: string
  submitted_at: string
  version_from: string
  version_to: string
  status: 'pending' | 'reviewing' | 'approved' | 'rejected'
  impact?: string
  changes?: Array<{ type: string; text: string }>
}

const reviews = ref<ReviewItem[]>([])

// 模拟数据
const mockReviews: ReviewItem[] = [
  {
    id: '1',
    type: '病种',
    title: '脓毒症表型规则更新',
    description: '更新脓毒症表型识别规则，增加乳酸阈值条件和时间窗口约束',
    submitted_by: '张医生',
    submitted_at: '2024-03-20 14:30',
    version_from: 'v2.0.0',
    version_to: 'v2.1.0',
    status: 'pending',
    impact: '影响 5 条规则，1247 名患者',
    changes: [
      { type: '新增', text: '乳酸 > 2 mmol/L 条件' },
      { type: '修改', text: 'SOFA 阈值从 3 调整为 2' },
      { type: '新增', text: '6小时时间窗口约束' },
    ],
  },
  {
    id: '2',
    type: '规则',
    title: 'SOFA-2 评分阈值调整',
    description: '根据最新指南调整 SOFA-2 评分的器官功能障碍阈值',
    submitted_by: '李主任',
    submitted_at: '2024-03-19 10:15',
    version_from: 'v1.0.0',
    version_to: 'v2.0.0',
    status: 'reviewing',
    impact: '影响 SOFA-2 评分计算，所有使用 SOFA-2 的规则',
    changes: [
      { type: '修改', text: '呼吸系统 PaO2/FiO2 阈值调整' },
      { type: '修改', text: '肾脏系统肌酐阈值调整' },
    ],
  },
  {
    id: '3',
    type: '知识包',
    title: '指南更新 v2024.3',
    description: '导入最新重症医学指南文档，包含 SCCM 2024 更新',
    submitted_by: '王药师',
    submitted_at: '2024-03-18 16:45',
    version_from: 'v1.4.0',
    version_to: 'v1.5.0',
    status: 'pending',
    impact: '新增 3 份指南文档，更新 2 份',
  },
  {
    id: '4',
    type: '术语',
    title: 'ICD-11 编码补充',
    description: '补充 50 个 ICD-11 编码映射',
    submitted_by: '赵编码员',
    submitted_at: '2024-03-17 09:20',
    version_from: 'v2024.1',
    version_to: 'v2024.2',
    status: 'approved',
    impact: '新增 50 个编码映射',
  },
  {
    id: '5',
    type: '病种',
    title: 'ARDS 分期标准修订',
    description: '根据柏林定义修订 ARDS 轻中重分期标准',
    submitted_by: '陈医生',
    submitted_at: '2024-03-15 11:30',
    version_from: 'v1.2.0',
    version_to: 'v1.3.0',
    status: 'approved',
    impact: '影响 ARDS 相关规则和评分',
  },
]

// 过滤后的列表
const filteredReviews = computed(() => {
  if (activeTab.value === 'all') return reviews.value
  return reviews.value.filter((r) => r.status === activeTab.value)
})

// 类型图标
function typeIcon(type: string) {
  const icons: Record<string, string> = { 病种: '📁', 规则: '🧬', 知识包: '📦', 术语: '🔤' }
  return icons[type] || '📄'
}

// 状态文本
function statusText(status: string) {
  const map: Record<string, string> = { pending: '待审核', reviewing: '审核中', approved: '已通过', rejected: '已拒绝' }
  return map[status] || status
}

// 状态标签
function statusLabel(status: string) {
  const map: Record<string, string> = { pending: '待审核', reviewing: '审核中', approved: '已通过', rejected: '已拒绝' }
  return map[status] || ''
}

// 查看详情
function viewDetail(item: ReviewItem) {
  alert(`查看详情: ${item.title}`)
}

// 通过
function approveItem(item: ReviewItem) {
  if (confirm(`确认通过 "${item.title}"？`)) {
    item.status = 'approved'
    stats.value.pending--
    stats.value.approved++
  }
}

// 拒绝
function rejectItem(item: ReviewItem) {
  if (confirm(`确认拒绝 "${item.title}"？`)) {
    item.status = 'rejected'
    stats.value.pending--
    stats.value.rejected++
  }
}

// 修改后通过
function requestChanges(item: ReviewItem) {
  alert(`已发送修改意见给 ${item.submitted_by}`)
}

// 初始化
import { onMounted } from 'vue'
onMounted(() => {
  reviews.value = mockReviews
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
