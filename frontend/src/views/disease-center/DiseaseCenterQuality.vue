<template>
  <div class="quality-page">
    <!-- 概览卡 -->
    <div class="overview-cards">
      <div class="overview-card">
        <DataCompletenessRing :value="overview.completeness" :size="64" />
        <div class="card-info">
          <div class="card-value">{{ overview.completeness }}%</div>
          <div class="card-label">病种完整性</div>
        </div>
      </div>
      <div class="overview-card">
        <DataCompletenessRing :value="overview.icd_quality" :size="64" />
        <div class="card-info">
          <div class="card-value">{{ overview.icd_quality }}%</div>
          <div class="card-label">ICD编码质量</div>
        </div>
      </div>
      <div class="overview-card">
        <div class="card-icon card-icon--warning">⚠</div>
        <div class="card-info">
          <div class="card-value">{{ overview.version_issues }}</div>
          <div class="card-label">版本问题</div>
        </div>
      </div>
      <div class="overview-card">
        <div class="card-icon card-icon--danger">✕</div>
        <div class="card-info">
          <div class="card-value">{{ overview.false_positives }}</div>
          <div class="card-label">误报数</div>
        </div>
      </div>
      <div class="overview-card">
        <DataCompletenessRing :value="overview.ai_accuracy" :size="64" />
        <div class="card-info">
          <div class="card-value">{{ overview.ai_accuracy }}%</div>
          <div class="card-label">AI建议准确率</div>
        </div>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="content-grid">
      <!-- 左侧：问题列表 -->
      <div class="panel panel--issues">
        <div class="panel__header">
          <h3 class="panel__title">质量异常</h3>
          <div class="header-tabs">
            <button
              v-for="tab in issueTabs"
              :key="tab.key"
              :class="['tab-btn', { 'tab-btn--active': activeTab === tab.key }]"
              @click="activeTab = tab.key"
            >
              {{ tab.label }}
              <span v-if="tab.count" class="tab-count">{{ tab.count }}</span>
            </button>
          </div>
        </div>
        <div class="panel__body">
          <div v-if="filteredIssues.length === 0" class="empty-state">
            <span class="empty-icon">✅</span>
            <span class="empty-text">暂无{{ activeTab === 'all' ? '' : tabLabel(activeTab) }}异常</span>
          </div>
          <div v-else class="issue-list">
            <div
              v-for="issue in filteredIssues"
              :key="issue.id"
              :class="['issue-card', `issue-card--${issue.severity}`]"
            >
              <div class="issue-header">
                <span :class="['severity-badge', `severity-badge--${issue.severity}`]">{{ severityText(issue.severity) }}</span>
                <span class="issue-type">{{ issue.issue_type || issue.type }}</span>
              </div>
              <h4 class="issue-title">{{ issue.title || issue.description }}</h4>
              <p class="issue-desc">{{ issue.description }}</p>
              <div class="issue-meta">
                <span class="meta-item">发现时间: {{ issue.detected_at }}</span>
                <span v-if="issue.affected_count" class="meta-item">影响: {{ issue.affected_count }} 项</span>
              </div>
              <div class="issue-actions">
                <button class="btn btn--sm btn--outline" @click="viewIssueDetail(issue)">查看详情</button>
                <button class="btn btn--sm btn--primary" @click="fixIssue(issue)">修复</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：图表和链接 -->
      <div class="panel--right">
        <!-- 趋势图 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">质量趋势（近30天）</h3>
          </div>
          <div class="card__body">
            <div class="trend-chart">
              <div v-for="(point, i) in trendData" :key="i" class="trend-bar">
                <div class="bar-fill" :style="{ height: point.value + '%' }" :class="`bar-fill--${point.status}`"></div>
                <span class="bar-label">{{ point.day }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 规则健康链接 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">系统级规则健康</h3>
          </div>
          <div class="card__body">
            <p class="link-desc">查看 Scanner 运行状态、扫描次数、告警数量、运行时延等系统级指标。</p>
            <a href="/admin/scanner-health" class="health-link">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
              打开规则健康页面
            </a>
          </div>
        </div>

        <!-- 金标准病例 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">金标准病例验证</h3>
          </div>
          <div class="card__body">
            <div class="gold-stats">
              <div class="gold-item">
                <span class="gold-value gold-value--success">{{ goldStandard.passed }}</span>
                <span class="gold-label">通过</span>
              </div>
              <div class="gold-item">
                <span class="gold-value gold-value--danger">{{ goldStandard.failed }}</span>
                <span class="gold-label">失败</span>
              </div>
              <div class="gold-item">
                <span class="gold-value">{{ goldStandard.total }}</span>
                <span class="gold-label">总计</span>
              </div>
            </div>
            <div class="gold-rate">
              <span class="rate-label">通过率</span>
              <div class="rate-bar">
                <div class="rate-fill" :style="{ width: goldStandard.rate + '%' }"></div>
              </div>
              <span class="rate-value">{{ goldStandard.rate }}%</span>
            </div>
          </div>
        </div>

        <!-- 离线包完整性 -->
        <div class="card">
          <div class="card__header">
            <h3 class="card__title">离线包完整性</h3>
          </div>
          <div class="card__body">
            <div class="package-checks">
              <div v-for="pkg in packageChecks" :key="pkg.name" class="check-item">
                <span :class="['check-dot', pkg.ok ? 'check-dot--success' : 'check-dot--danger']"></span>
                <span class="check-name">{{ pkg.name }}</span>
                <span class="check-status">{{ pkg.ok ? '正常' : '异常' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { getQualityIssues } from '../../api/diseaseCenter'
import DataCompletenessRing from '../../components/charts/risk/DataCompletenessRing.vue'

// 状态
const activeTab = ref('all')

// 概览数据
const overview = ref({
  completeness: 94,
  icd_quality: 88,
  version_issues: 3,
  false_positives: 5,
  ai_accuracy: 92,
})

// 标签
const issueTabs = computed(() => [
  { key: 'all', label: '全部', count: issues.value.length },
  { key: 'completeness', label: '完整性', count: issues.value.filter((i) => (i.issue_type || i.type) === '完整性').length },
  { key: 'icd', label: 'ICD编码', count: issues.value.filter((i) => (i.issue_type || i.type) === 'ICD编码').length },
  { key: 'version', label: '版本', count: issues.value.filter((i) => (i.issue_type || i.type) === '版本').length },
  { key: 'phenotype', label: '表型误报', count: issues.value.filter((i) => (i.issue_type || i.type) === '表型误报').length },
])

// 问题类型
interface QualityIssue {
  id: string
  issue_type: string
  type?: string
  severity: string
  title?: string
  description: string
  detected_at?: string
  affected_count?: number
}

const issues = ref<QualityIssue[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

// 过滤后的问题
const filteredIssues = computed(() => {
  if (activeTab.value === 'all') return issues.value
  const typeMap: Record<string, string> = {
    completeness: '完整性',
    icd: 'ICD编码',
    version: '版本',
    phenotype: '表型误报',
  }
  return issues.value.filter((i) => (i.issue_type || i.type) === typeMap[activeTab.value])
})

// 标签文本
function tabLabel(tab: string) {
  const map: Record<string, string> = {
    completeness: '完整性',
    icd: 'ICD编码',
    version: '版本',
    phenotype: '表型误报',
  }
  return map[tab] || ''
}

// 严重程度文本
function severityText(severity: string) {
  const map: Record<string, string> = { high: '高', medium: '中', low: '低' }
  return map[severity] || severity
}

// 趋势数据
const trendData = ref([
  { day: '1', value: 85, status: 'good' },
  { day: '5', value: 88, status: 'good' },
  { day: '10', value: 82, status: 'warning' },
  { day: '15', value: 90, status: 'good' },
  { day: '20', value: 87, status: 'good' },
  { day: '25', value: 92, status: 'good' },
  { day: '30', value: 94, status: 'good' },
])

// 金标准病例
const goldStandard = ref({
  passed: 45,
  failed: 3,
  total: 48,
  rate: 93.75,
})

// 离线包检查
const packageChecks = ref([
  { name: 'ICD数据包', ok: true },
  { name: '医学术语库', ok: true },
  { name: '指南文档', ok: true },
  { name: 'AI模型', ok: true },
  { name: '向量索引', ok: false },
])

// 查看详情
function viewIssueDetail(issue: QualityIssue) {
  const rows: Array<[string, string]> = [
    ['标题', issue.title || '-'],
    ['类型', issue.issue_type || issue.type || '-'],
    ['严重程度', severityText(issue.severity)],
    ['发现时间', issue.detected_at || '-'],
    ['影响数量', issue.affected_count != null ? `${issue.affected_count} 项` : '-'],
  ]
  Modal.info({
    title: '质量问题详情',
    content: () =>
      h('div', [
        ...rows.map(([k, v]) =>
          h('div', { style: 'display:flex;gap:8px;margin-bottom:6px;' }, [
            h('span', { style: 'min-width:70px;color:#667085;flex-shrink:0;' }, k),
            h('span', { style: 'word-break:break-all;' }, v),
          ])
        ),
        h('div', { style: 'margin-top:10px;padding-top:10px;border-top:1px solid #f0f0f0;' }, [
          h('div', { style: 'font-weight:600;margin-bottom:6px;' }, '描述'),
          h('div', { style: 'white-space:pre-wrap;' }, issue.description || '-'),
        ]),
      ]),
    okText: '关闭',
    width: 520,
  })
}

// 修复问题
function fixIssue(_issue: QualityIssue) {
  message.info('后端暂未提供质量问题修复接口')
}

// 加载数据
async function loadIssues() {
  loading.value = true
  error.value = null

  try {
    const { data } = await getQualityIssues()
    issues.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    error.value = e?.message || '获取质量问题失败，请稍后重试'
    issues.value = []
  } finally {
    loading.value = false
  }
}

// 初始化
import { onMounted } from 'vue'
onMounted(() => {
  loadIssues()
})
</script>

<style scoped>.quality-page { display: flex; flex-direction: column; gap: 20px }

/* 概览卡 */ .overview-cards { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px }
.overview-card { display: flex; align-items: center; gap: 12px; padding: 16px; background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB) }
.card-icon { width: 40px; height: 40px; border-radius: var(--radius-lg, 10px); display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 700 }
.card-icon--success { background: rgba(22, 132, 91, 0.1); color: var(--color-success, #16845B) }
.card-icon--info { background: rgba(37, 99, 235, 0.1); color: var(--color-primary, #2563EB) }
.card-icon--warning { background: rgba(181, 71, 8, 0.1); color: var(--color-warning, #B54708) }
.card-icon--danger { background: rgba(217, 45, 32, 0.1); color: var(--color-danger, #D92D20) }
.card-icon--ai { background: var(--color-ai-light, #F0EDFF); color: var(--color-ai, #6E5AE6) }
.card-value  {  font-size: var(--text-metric-normal, 20px); font-weight: 700; color: var(--color-text-primary, #111827); line-height: 1 ; font-variant-numeric: tabular-nums }
.card-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); margin-top: 2px }

/* 内容区 */ .content-grid { display: grid; grid-template-columns: 1fr 320px; gap: 16px }

/* 面板 */ .panel { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); display: flex; flex-direction: column; overflow: hidden }
.panel__header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--color-divider, #F0F2F5); flex-wrap: wrap; gap: 8px }
.panel__title { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 }
.panel__body { flex: 1; overflow-y: auto; padding: 16px; max-height: 600px }
.header-tabs { display: flex; gap: 4px }
.tab-btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; font-size: var(--text-caption, 12px); font-weight: 500; border: none; border-radius: var(--radius-tag, 4px); background: transparent; color: var(--color-text-secondary, #4B5563); cursor: pointer; transition: all 0.15s }
.tab-btn:hover { background: var(--color-bg-surface-secondary, #F1F4F8) }
.tab-btn--active { background: var(--color-primary, #2563EB); color: var(--color-text-inverse, #FFFFFF) }
.tab-count { display: inline-flex; align-items: center; justify-content: center; min-width: 16px; height: 16px; padding: 0 3px; font-size: var(--text-caption, 12px); font-weight: 600; border-radius: var(--radius-md, 6px); background: rgba(0, 0, 0, 0.1) }
.tab-btn--active .tab-count { background: rgba(255, 255, 255, 0.3) }

/* 问题列表 */ .issue-list { display: flex; flex-direction: column; gap: 12px }
.issue-card { padding: 14px; border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB) }
.issue-card--high { border-left: 3px solid var(--color-danger, #D92D20) }
.issue-card--medium { border-left: 3px solid var(--color-warning, #B54708) }
.issue-card--low { border-left: 3px solid var(--color-primary, #2563EB) }
.issue-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px }
.severity-badge { display: inline-flex; padding: 1px 6px; font-size: var(--text-caption, 12px); font-weight: 500; border-radius: var(--radius-tag, 4px) }
.severity-badge--high { color: var(--color-danger, #D92D20); background: rgba(217, 45, 32, 0.1) }
.severity-badge--medium { color: var(--color-warning, #B54708); background: rgba(181, 71, 8, 0.1) }
.severity-badge--low { color: var(--color-primary, #2563EB); background: rgba(37, 99, 235, 0.1) }
.issue-type { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.issue-title { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 0 4px }
.issue-desc { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); margin: 0 0 8px; line-height: 1.5 }
.issue-meta { display: flex; gap: 12px; margin-bottom: 10px }
.meta-item { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.issue-actions { display: flex; gap: 8px }

/* 右侧卡片 */ .panel--right { display: flex; flex-direction: column; gap: 16px }
.card { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); overflow: hidden }
.card__header { padding: 12px 16px; border-bottom: 1px solid var(--color-divider, #F0F2F5) }
.card__title { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 }
.card__body { padding: 14px }

/* 趋势图 */ .trend-chart { display: flex; align-items: flex-end; gap: 8px; height: 100px }
.trend-bar { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; height: 100%; justify-content: flex-end }
.bar-fill { width: 100%; border-radius: 2px 2px 0 0; transition: height 0.3s }
.bar-fill--good { background: var(--color-success, #16845B) }
.bar-fill--warning { background: var(--color-warning, #B54708) }
.bar-label { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }

/* 链接 */ .link-desc { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); margin: 0 0 10px; line-height: 1.5 }
.health-link { display: flex; align-items: center; gap: 6px; font-size: var(--text-body, 13px); color: var(--color-primary, #2563EB); text-decoration: none }
.health-link:hover { text-decoration: underline }

/* 金标准 */ .gold-stats { display: flex; gap: 16px; margin-bottom: 12px }
.gold-item { display: flex; flex-direction: column; align-items: center; gap: 2px }
.gold-value  {  font-size: var(--text-metric-normal, 20px); font-weight: 700; color: var(--color-text-primary, #111827) ; font-variant-numeric: tabular-nums }
.gold-value--success { color: var(--color-success, #16845B) }
.gold-value--danger { color: var(--color-danger, #D92D20) }
.gold-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.gold-rate { display: flex; align-items: center; gap: 8px }
.rate-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.rate-bar { flex: 1; height: 6px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-tag, 4px); overflow: hidden }
.rate-fill { height: 100%; background: var(--color-success, #16845B); border-radius: var(--radius-tag, 4px) }
.rate-value { font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-success, #16845B) }

/* 离线包检查 */ .package-checks { display: flex; flex-direction: column; gap: 8px }
.check-item { display: flex; align-items: center; gap: 8px }
.check-dot { width: 8px; height: 8px; border-radius: 50% }
.check-dot--success { background: var(--color-success, #16845B) }
.check-dot--danger { background: var(--color-danger, #D92D20) }
.check-name { flex: 1; font-size: var(--text-caption, 12px); color: var(--color-text-primary, #111827) }
.check-status { font-size: var(--text-caption, 12px); font-weight: 500 }
.check-dot--success + .check-name + .check-status { color: var(--color-success, #16845B) }
.check-dot--danger + .check-name + .check-status { color: var(--color-danger, #D92D20) }

/* 空状态 */ .empty-state { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 40px 20px; text-align: center }
.empty-icon { font-size: 32px; opacity: 0.6 }
.empty-text { font-size: var(--text-body, 13px); color: var(--color-text-secondary, #4B5563) }

/* 按钮 */ .btn { display: inline-flex; align-items: center; justify-content: center; gap: 4px; padding: 6px 12px; font-size: var(--text-caption, 12px); font-weight: 500; border-radius: var(--radius-tag, 4px); cursor: pointer; transition: all 0.15s; border: 1px solid transparent }
.btn--sm { padding: 4px 10px; font-size: var(--text-caption, 12px) }
.btn--outline { background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); border-color: var(--color-border, #E5E7EB) }
.btn--outline:hover { background: var(--color-bg-surface-secondary, #F1F4F8) }
.btn--primary { background: var(--color-primary, #2563EB); color: var(--color-text-inverse, #FFFFFF) }
.btn--primary:hover { background: var(--color-primary-hover, #3B82F6) }

/* 响应式 */

@media (max-width: 1024px) {.overview-cards { grid-template-columns: repeat(3, 1fr) }
.content-grid { grid-template-columns: 1fr }
.panel--right { order: -1 }

}

@media (max-width: 768px) {.overview-cards { grid-template-columns: repeat(2, 1fr) }

}

</style>
