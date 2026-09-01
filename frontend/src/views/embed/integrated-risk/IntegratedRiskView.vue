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
import { ref, computed, onMounted } from 'vue'
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
</script>

<style scoped>
.integrated-risk {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 4px;
}

/* ── 状态栏 ── */
.ir-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px 20px;
  border-radius: 10px;
  font-size: 14px;
}

.ir-state__icon { font-size: 18px; }

.ir-state--loading { background: #F8FAFC; color: #52606D; border: 1px solid #E8EEF5; }
.ir-state--error { background: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }
.ir-state--empty { background: #F8FAFC; color: #94A3B8; border: 1px solid #E8EEF5; }
.ir-state--warning { background: #FFFBEB; color: #92400E; border: 1px solid #FDE68A; }

.ir-retry-btn {
  margin-left: auto;
  padding: 6px 16px;
  border: 1px solid #DCE3EC;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}
.ir-retry-btn:hover { background: #F8FAFC; border-color: #94A3B8; }

/* ── 概览行：态势 + 器官状态 ── */
.ir-overview-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.ir-situation-card,
.ir-organs-card,
.ir-section {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #E8EEF5;
  overflow: hidden;
}

.ir-card-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  border-bottom: 1px solid #F0F4F8;
}

.ir-card-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #182230;
}

.ir-card-time {
  margin-left: auto;
  font-size: 11px;
  color: #94A3B8;
}

.ir-situation-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.ir-dot--critical { background: #991B1B; }
.ir-dot--high { background: #DC2626; }
.ir-dot--warning { background: #F59E0B; }
.ir-dot--normal { background: #16A34A; }

.ir-situation-text {
  margin: 0;
  padding: 18px;
  font-size: 15px;
  font-weight: 500;
  line-height: 1.6;
  color: #334155;
}

/* ── 器官状态 ── */
.ir-organs-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 16px;
}

.ir-organ-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 14px 10px;
  background: #F8FAFC;
  border-radius: 8px;
  border: 1px solid #E8EEF5;
  transition: all 0.2s;
}

.ir-organ--normal { border-bottom: 3px solid #16A34A; }
.ir-organ--impaired { border-bottom: 3px solid #F59E0B; background: #FFFBEB; }
.ir-organ--failure { border-bottom: 3px solid #DC2626; background: #FEF2F2; }

.ir-organ-icon { font-size: 28px; }
.ir-organ-name { font-size: 12px; color: #64748B; font-weight: 500; }
.ir-organ-status { font-size: 13px; font-weight: 600; color: #182230; }

/* ── 通用 section ── */
.ir-section-header {
  padding: 14px 18px;
  border-bottom: 1px solid #F0F4F8;
}

.ir-section-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #182230;
}

.ir-causal-text {
  font-size: 13px;
  line-height: 1.6;
  color: #52606D;
  margin: 0;
  padding: 16px 18px;
}

/* ── 因果链 ── */
.ir-causal-chain {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 16px 18px;
}

.ir-chain-node {
  display: flex;
  align-items: center;
  gap: 6px;
}

.ir-chain-content {
  padding: 10px 16px;
  border-radius: 8px;
  background: #F8FAFC;
  border: 1px solid #E8EEF5;
  text-align: center;
}

.ir-chain--danger .ir-chain-content {
  background: #FEF2F2;
  border-color: #FECACA;
}

.ir-chain--warning .ir-chain-content {
  background: #FFFBEB;
  border-color: #FDE68A;
}

.ir-chain-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}

.ir-chain-time {
  display: block;
  font-size: 10px;
  color: #94A3B8;
  margin-top: 2px;
}

.ir-chain-metric {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #2563EB;
  font-family: 'Rajdhani', monospace;
  margin-top: 4px;
}

.ir-chain-arrow {
  font-size: 18px;
  color: #CBD5E1;
  margin: 0 2px;
}

/* ── 行动建议 ── */
.ir-actions-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 18px;
}

.ir-action-item {
  display: flex;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 8px;
  background: #F8FAFC;
  border: 1px solid #E8EEF5;
}

.ir-action--critical { border-left: 4px solid #991B1B; }
.ir-action--high { border-left: 4px solid #DC2626; }
.ir-action--medium { border-left: 4px solid #F59E0B; }
.ir-action--low { border-left: 4px solid #16A34A; }

.ir-action-badge {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 6px;
  background: #E8EEF5;
  color: #475569;
  height: fit-content;
}

.ir-action--critical .ir-action-badge { background: #FEF2F2; color: #991B1B; }
.ir-action--high .ir-action-badge { background: #FEF2F2; color: #DC2626; }
.ir-action--medium .ir-action-badge { background: #FFFBEB; color: #92400E; }

.ir-action-content {
  flex: 1;
  min-width: 0;
}

.ir-action-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: #334155;
}

.ir-action-evidence {
  margin: 6px 0 0;
  font-size: 12px;
  color: #94A3B8;
  line-height: 1.4;
}

/* ── 证据 ── */
.ir-evidence-list {
  display: flex;
  flex-direction: column;
  padding: 0 18px 12px;
}

.ir-evidence-item {
  display: grid;
  grid-template-columns: 80px 80px 1fr;
  gap: 12px;
  padding: 12px 0;
  border-bottom: 1px solid #F0F4F8;
  font-size: 12px;
  align-items: center;
}

.ir-evidence-item:last-child { border-bottom: none; }

.ir-evidence-time {
  color: #94A3B8;
  font-family: 'Rajdhani', monospace;
  font-size: 13px;
}

.ir-evidence-type {
  font-weight: 500;
  padding: 3px 8px;
  border-radius: 4px;
  text-align: center;
  font-size: 11px;
}

.ir-ev--critical { background: #FEF2F2; color: #991B1B; }
.ir-ev--high { background: #FEF2F2; color: #DC2626; }
.ir-ev--warning { background: #FFFBEB; color: #92400E; }
.ir-ev--info { background: #EFF6FF; color: #1E40AF; }

.ir-evidence-text {
  color: #475569;
  line-height: 1.4;
}

/* ── 响应式 ── */
@media (max-width: 1200px) {
  .ir-overview-row { grid-template-columns: 1fr; }
  .ir-organs-grid { grid-template-columns: repeat(3, 1fr); }
}

@media (max-width: 768px) {
  .ir-organs-grid { grid-template-columns: repeat(2, 1fr); }
  .ir-evidence-item { grid-template-columns: 1fr; gap: 4px; }
}
</style>
