<template>
  <div class="integrated-risk">
    <!-- 状态栏 -->
    <div v-if="loading" class="ir-state ir-state--loading">
      <span class="ir-state__icon">⏳</span>
      <span class="ir-state__text">正在分析综合风险……</span>
    </div>
    <div v-else-if="loadError" class="ir-state ir-state--error">
      <span class="ir-state__icon">⚠️</span>
      <span class="ir-state__text">{{ loadError }}</span>
      <button class="ir-retry-btn" @click="loadData">重试</button>
    </div>
    <div v-else-if="!report" class="ir-state ir-state--empty">
      <span class="ir-state__icon">📭</span>
      <span class="ir-state__text">暂无可用综合风险报告</span>
    </div>

    <!-- 成功：展示报告 -->
    <template v-else>
      <!-- 过期报告提示 -->
      <div v-if="report.stale" class="ir-state ir-state--warning">
        <span class="ir-state__icon">ℹ️</span>
        <span class="ir-state__text">当前展示最近一次综合风险报告，AI服务额度不足，暂时无法更新。</span>
      </div>

      <!-- 态势结论 + 器官状态 -->
      <div class="ir-overview-row">
        <!-- 态势结论 -->
        <div class="ir-situation-card">
          <div class="ir-card-header">
            <span class="ir-situation-dot" :class="`ir-dot--${riskLevel}`" />
            <h3 class="ir-card-title">风险态势</h3>
            <span class="ir-card-time">{{ updatedAt }}</span>
          </div>
          <p class="ir-situation-text">{{ situationText || '综合风险分析完成' }}</p>
        </div>

        <!-- 多器官状态图 -->
        <div v-if="organs.length" class="ir-organs-card">
          <div class="ir-card-header">
            <h3 class="ir-card-title">多器官状态</h3>
          </div>
          <div class="ir-organs-grid">
            <div v-for="organ in organs" :key="organ.key" class="ir-organ-item" :class="`ir-organ--${organ.status}`">
              <span class="ir-organ-icon">{{ organ.icon }}</span>
              <span class="ir-organ-name">{{ organ.label }}</span>
              <span class="ir-organ-status">{{ organ.statusText }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 因果链 -->
      <div v-if="causalChain.length || causalChainText" class="ir-section">
        <div class="ir-section-header">
          <h3 class="ir-section-title">🔗 风险因果链</h3>
        </div>
        <div v-if="causalChain.length" class="ir-causal-chain">
          <div v-for="(node, idx) in causalChain" :key="idx" class="ir-chain-node" :class="`ir-chain--${node.level}`">
            <div class="ir-chain-content">
              <span class="ir-chain-label">{{ node.label }}</span>
              <span class="ir-chain-time">{{ node.time }}</span>
              <span v-if="node.metric" class="ir-chain-metric">{{ node.metric }}</span>
            </div>
            <span v-if="Number(idx) < causalChain.length - 1" class="ir-chain-arrow">→</span>
          </div>
        </div>
        <p v-else class="ir-causal-text">{{ causalChainText }}</p>
      </div>

      <!-- 行动建议 -->
      <div v-if="topActions.length" class="ir-section">
        <div class="ir-section-header">
          <h3 class="ir-section-title">📋 Top 3 行动建议</h3>
        </div>
        <div class="ir-actions-list">
          <div v-for="(action, idx) in topActions" :key="idx" class="ir-action-item" :class="`ir-action--${action.priority}`">
            <div class="ir-action-badge">{{ action.priorityLabel }}</div>
            <div class="ir-action-content">
              <p class="ir-action-text">{{ action.text }}</p>
              <p v-if="action.evidence" class="ir-action-evidence">{{ action.evidence }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 证据链 -->
      <div v-if="evidenceList.length" class="ir-section">
        <div class="ir-section-header">
          <h3 class="ir-section-title">📊 原始告警证据</h3>
        </div>
        <div class="ir-evidence-list">
          <div v-for="(ev, idx) in evidenceList" :key="idx" class="ir-evidence-item">
            <span class="ir-evidence-time">{{ ev.time }}</span>
            <span class="ir-evidence-type" :class="`ir-ev--${ev.level}`">{{ ev.type }}</span>
            <span class="ir-evidence-text">{{ ev.text }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getAiIntegratedRiskReport } from '../../../api'

// ── 安全数组转换 ──
function asArray(value: unknown): any[] {
  return Array.isArray(value) ? value : []
}

function normalizeCausalChain(value: unknown): any[] {
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>
    if (Array.isArray(obj.nodes)) return obj.nodes
    if (Array.isArray(obj.chain)) return obj.chain
    if (Array.isArray(obj.items)) return obj.items
  }
  // 字符串不在此处转换，由 causalChainText 降级展示
  return []
}

function normalizeOrganStatus(value: unknown): any[] {
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).map(
      ([organ, detail]) => ({
        organ,
        ...(detail && typeof detail === 'object' ? detail : { status: detail }),
      }),
    )
  }
  return []
}

function normalizeReport(raw: any): any {
  if (!raw || typeof raw !== 'object') return raw
  const chainRaw = raw.causal_chain
  return {
    ...raw,
    organ_status: normalizeOrganStatus(raw.organ_status),
    causal_chain: normalizeCausalChain(chainRaw),
    // 保留原始字符串供 causalChainText 降级展示
    _causal_chain_text: typeof chainRaw === 'string' ? chainRaw.trim() : '',
    top_actions: asArray(raw.top_actions ?? raw.top3_actions),
    evidence: asArray(raw.evidence),
  }
}

// ── 路由与桥接 ──
const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'integrated-risk',
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => loadData(),
  onRefresh: () => loadData(),
})

// ── 状态 ──
const loading = ref(false)
const loadError = ref('')
const report = ref<any | null>(null)

// ── 派生数据 ──
const riskLevel = computed(() => {
  const s = String(report.value?.risk_level || '').toLowerCase()
  if (s.includes('critical') || s.includes('危')) return 'critical'
  if (s.includes('high') || s.includes('高')) return 'high'
  if (s.includes('warning') || s.includes('警告')) return 'warning'
  return 'normal'
})

const situationText = computed(() => report.value?.situation_summary || report.value?.summary || '')
const updatedAt = computed(() => {
  const t = report.value?.updated_at
  if (!t) return ''
  try { return new Date(t).toLocaleTimeString('zh-CN') } catch { return '' }
})

const organs = computed(() => {
  const data = asArray(report.value?.organ_status)
  const icons: Record<string, string> = { respiratory: '🫁', circulatory: '❤️', renal: '🫘', coagulation: '🩸', hepatic: '🫀', neurologic: '🧠' }
  const labels: Record<string, string> = { respiratory: '呼吸', circulatory: '循环', renal: '肾脏', coagulation: '凝血', hepatic: '肝脏', neurologic: '神经' }
  const statusTexts: Record<string, string> = { normal: '正常', impaired: '受损', failure: '衰竭' }
  return data.map((o: any) => ({
    key: o.organ || o.key,
    icon: icons[o.organ || o.key] || '🫁',
    label: labels[o.organ || o.key] || o.organ || o.key,
    status: o.status || 'normal',
    statusText: statusTexts[o.status] || o.status || '—',
  }))
})

const causalChain = computed(() => {
  const chain = asArray(report.value?.causal_chain)
  return chain.map((c: any) => ({
    label: c?.label || c?.event || '',
    time: c?.time || '',
    metric: c?.metric || '',
    level: c?.level || 'info',
  }))
})

/** causal_chain 为纯文本时的降级展示 */
const causalChainText = computed(() => {
  return report.value?._causal_chain_text || ''
})

const topActions = computed(() => {
  const actions = asArray(report.value?.top_actions)
  const priorityLabels: Record<string, string> = { critical: '紧急', high: '重要', medium: '建议', low: '参考' }
  return actions.slice(0, 3).map((a: any) => ({
    text: a?.text || a?.action || '',
    priority: a?.priority || 'medium',
    priorityLabel: priorityLabels[a?.priority] || '建议',
    evidence: a?.evidence || a?.rationale || '',
  }))
})

const evidenceList = computed(() => {
  const evs = asArray(report.value?.evidence)
  return evs.map((e: any) => ({
    time: e?.time || '',
    type: e?.type || e?.alert_type || '',
    text: e?.text || e?.description || '',
    level: e?.level || e?.severity || 'info',
  }))
})

// ── 加载数据 ──
async function loadData() {
  if (!patientId.value) return

  loading.value = true
  loadError.value = ''
  report.value = null

  try {
    const res = await getAiIntegratedRiskReport(patientId.value)
    const data = res.data || {}

    if (data.error) {
      loadError.value = String(data.error)
      return
    }

    if (!data.report || typeof data.report !== 'object') {
      loadError.value = '当前暂无可用的综合风险报告'
      return
    }

    report.value = normalizeReport(data.report)
  } catch (e: any) {
    const status = e?.response?.status

    if (status === 401) {
      loadError.value = '登录状态已失效，请重新登录'
    } else if (status === 403) {
      loadError.value = '当前账号无权访问该患者综合风险'
    } else if (status === 429) {
      loadError.value = 'AI服务额度已用完，请联系管理员'
    } else if (status === 503) {
      loadError.value = e?.response?.data?.detail || 'AI服务额度不足，暂时无法生成综合风险报告'
    } else if (status && status >= 500) {
      loadError.value = '综合风险服务暂时不可用'
    } else {
      loadError.value =
        e?.response?.data?.detail ||
        e?.message ||
        '加载综合风险失败'
    }

    sendReportError('LOAD_FAILED', loadError.value)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  sendUpdateTitle('综合风险')
  loadData()
})

// 直接渲染模式下组件会被复用：切换患者时路由参数变化需手动重载
watch(patientId, (id, prev) => {
  if (id && id !== prev) loadData()
})
</script>

<style scoped>.integrated-risk { display: flex; flex-direction: column; gap: 16px; padding: 4px }

/* ── 状态栏 ── */ .ir-state { display: flex; align-items: center; gap: 10px; padding: 16px 20px; border-radius: var(--radius-lg, 10px); font-size: var(--text-body, 13px) }
.ir-state__icon { font-size: 18px }
.ir-state--loading { background: var(--color-bg-surface-secondary, #F1F4F8); color: var(--color-text-secondary, #4B5563); border: 1px solid var(--color-border, #E5E7EB) }
.ir-state--error { background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20); border: 1px solid var(--color-critical-border, #FDA29B) }
.ir-state--empty { background: var(--color-bg-surface-secondary, #F1F4F8); color: var(--color-text-tertiary, #9CA3AF); border: 1px solid var(--color-border, #E5E7EB) }
.ir-state--warning { background: var(--color-warning-soft-bg, #FFF9D8); color: var(--color-warning, #B54708); border: 1px solid var(--color-warning-soft-border, #FFE58F) }
.ir-retry-btn { margin-left: auto; padding: 6px 16px; border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); background: var(--color-bg-surface, #FFFFFF); cursor: pointer; font-size: var(--text-body, 13px); transition: all 0.2s }
.ir-retry-btn:hover { background: var(--color-bg-surface-secondary, #F1F4F8); border-color: var(--color-border-strong, #D1D5DB) }

/* ── 概览行：态势 + 器官状态 ── */ .ir-overview-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px }
.ir-situation-card, .ir-organs-card, .ir-section { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); overflow: hidden }
.ir-card-header { display: flex; align-items: center; gap: 10px; padding: 14px 18px; border-bottom: 1px solid var(--color-border, #E5E7EB) }
.ir-card-title { margin: 0; font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }
.ir-card-time { margin-left: auto; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.ir-situation-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0 }
.ir-dot--critical { background: var(--color-critical, #D92D20) }
.ir-dot--high { background: var(--color-danger, #D92D20) }
.ir-dot--warning { background: var(--color-warning, #B54708) }
.ir-dot--normal { background: var(--color-normal, #12A66A) }
.ir-situation-text { margin: 0; padding: 18px; font-size: var(--text-section-title, 15px); font-weight: 500; line-height: 1.6; color: var(--color-text-secondary, #4B5563) }

/* ── 器官状态 ── */ .ir-organs-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; padding: 16px }
.ir-organ-item { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 14px 10px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB); transition: all 0.2s }
.ir-organ--normal { border-bottom: 3px solid var(--color-normal, #12A66A) }
.ir-organ--impaired { border-bottom: 3px solid var(--color-warning, #B54708); background: var(--color-warning-soft-bg, #FFF9D8) }
.ir-organ--failure { border-bottom: 3px solid var(--color-danger, #D92D20); background: var(--color-critical-bg, #FEECEB) }
.ir-organ-icon { font-size: 28px }
.ir-organ-name { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); font-weight: 500 }
.ir-organ-status { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }

/* ── 通用 section ── */ .ir-section-header { padding: 14px 18px; border-bottom: 1px solid var(--color-border, #E5E7EB) }
.ir-section-title { margin: 0; font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }
.ir-causal-text { font-size: var(--text-body, 13px); line-height: 1.6; color: var(--color-text-secondary, #4B5563); margin: 0; padding: 16px 18px }

/* ── 因果链 ── */ .ir-causal-chain { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 16px 18px }
.ir-chain-node { display: flex; align-items: center; gap: 6px }
.ir-chain-content { padding: 10px 16px; border-radius: var(--radius-md, 6px); background: var(--color-bg-surface-secondary, #F1F4F8); border: 1px solid var(--color-border, #E5E7EB); text-align: center }
.ir-chain--danger .ir-chain-content { background: var(--color-critical-bg, #FEECEB); border-color: var(--color-critical-border, #FDA29B) }
.ir-chain--warning .ir-chain-content { background: var(--color-warning-soft-bg, #FFF9D8); border-color: var(--color-warning-soft-border, #FFE58F) }
.ir-chain-label { display: block; font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-text-secondary, #4B5563) }
.ir-chain-time { display: block; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); margin-top: 2px }
.ir-chain-metric { display: block; font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-primary, #2563EB); font-family: 'Rajdhani', monospace; margin-top: 4px }
.ir-chain-arrow { font-size: var(--text-section-title, 15px); color: var(--color-text-tertiary, #9CA3AF); margin: 0 2px }

/* ── 行动建议 ── */ .ir-actions-list { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px }
.ir-action-item { display: flex; gap: 14px; padding: 14px 16px; border-radius: var(--radius-md, 6px); background: var(--color-bg-surface-secondary, #F1F4F8); border: 1px solid var(--color-border, #E5E7EB) }
.ir-action--critical { border-left: 4px solid var(--color-critical, #D92D20) }
.ir-action--high { border-left: 4px solid var(--color-danger, #D92D20) }
.ir-action--medium { border-left: 4px solid var(--color-warning, #B54708) }
.ir-action--low { border-left: 4px solid var(--color-normal, #12A66A) }
.ir-action-badge { flex-shrink: 0; font-size: var(--text-caption, 12px); font-weight: 600; padding: 4px 10px; border-radius: var(--radius-md, 6px); background: var(--color-bg-inset, #E9EEF5); color: var(--color-text-secondary, #4B5563); height: fit-content }
.ir-action--critical .ir-action-badge { background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20) }
.ir-action--high .ir-action-badge { background: var(--color-critical-bg, #FEECEB); color: var(--color-danger, #D92D20) }
.ir-action--medium .ir-action-badge { background: var(--color-warning-soft-bg, #FFF9D8); color: var(--color-warning, #B54708) }
.ir-action-content { flex: 1; min-width: 0 }
.ir-action-text { margin: 0; font-size: var(--text-body, 13px); line-height: 1.5; color: var(--color-text-secondary, #4B5563) }
.ir-action-evidence { margin: 6px 0 0; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); line-height: 1.4 }

/* ── 证据 ── */ .ir-evidence-list { display: flex; flex-direction: column; padding: 0 18px 12px }
.ir-evidence-item { display: grid; grid-template-columns: 80px 80px 1fr; gap: 12px; padding: 12px 0; border-bottom: 1px solid var(--color-border, #E5E7EB); font-size: var(--text-caption, 12px); align-items: center }
.ir-evidence-item:last-child { border-bottom: none }
.ir-evidence-time { color: var(--color-text-tertiary, #9CA3AF); font-family: 'Rajdhani', monospace; font-size: var(--text-body, 13px) }
.ir-evidence-type { font-weight: 500; padding: 3px 8px; border-radius: var(--radius-tag, 4px); text-align: center; font-size: var(--text-caption, 12px) }
.ir-ev--critical { background: var(--color-critical-bg, #FEECEB); color: var(--color-critical, #D92D20) }
.ir-ev--high { background: var(--color-critical-bg, #FEECEB); color: var(--color-danger, #D92D20) }
.ir-ev--warning { background: var(--color-warning-soft-bg, #FFF9D8); color: var(--color-warning, #B54708) }
.ir-ev--info { background: var(--color-primary-bg, #EFF6FF); color: var(--color-primary, #2563EB) }
.ir-evidence-text { color: var(--color-text-secondary, #4B5563); line-height: 1.4 }

/* ── 响应式 ── */

@media (max-width: 1200px) {.ir-overview-row { grid-template-columns: 1fr }
.ir-organs-grid { grid-template-columns: repeat(3, 1fr) }

}

@media (max-width: 768px) {.ir-organs-grid { grid-template-columns: repeat(2, 1fr) }
.ir-evidence-item { grid-template-columns: 1fr; gap: 4px }

}

</style>
