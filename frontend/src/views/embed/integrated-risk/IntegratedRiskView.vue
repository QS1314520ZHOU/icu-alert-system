<template>
  <div class="integrated-risk">
    <!-- 加载中 -->
    <div v-if="loading" class="ir-state-bar ir-state--loading">
      <span class="ir-state-icon">⏳</span>
      <span>正在分析综合风险……</span>
    </div>

    <!-- 错误 -->
    <div v-else-if="loadError" class="ir-state-bar ir-state--error">
      <span class="ir-state-icon">⚠️</span>
      <span>{{ loadError }}</span>
      <button class="ir-retry-btn" @click="loadData">重试</button>
    </div>

    <!-- 空数据 -->
    <div v-else-if="!report" class="ir-state-bar ir-state--empty">
      <span class="ir-state-icon">📭</span>
      <span>暂无可用综合风险报告</span>
    </div>

    <!-- 成功：展示报告 -->
    <template v-else>
      <!-- 过期报告提示 -->
      <div v-if="report.stale" class="ir-state-bar ir-state--warning">
        <span class="ir-state-icon">ℹ️</span>
        <span>当前展示最近一次综合风险报告，AI服务额度不足，暂时无法更新。</span>
      </div>

      <!-- 态势结论 -->
      <div class="ir-situation-bar">
        <span class="ir-situation-icon" :class="`ir-situation--${riskLevel}`">●</span>
        <span class="ir-situation-text">{{ situationText || '综合风险分析完成' }}</span>
        <span class="ir-situation-time">{{ updatedAt }}</span>
      </div>

      <!-- 多器官状态图 -->
      <div v-if="organs.length" class="ir-organs-row">
        <div v-for="organ in organs" :key="organ.key" class="ir-organ-card" :class="`ir-organ--${organ.status}`">
          <div class="ir-organ-icon">{{ organ.icon }}</div>
          <span class="ir-organ-name">{{ organ.label }}</span>
          <span class="ir-organ-status">{{ organ.statusText }}</span>
        </div>
      </div>

      <!-- 因果链 -->
      <div v-if="causalChain.length" class="ir-section">
        <h3 class="ir-section-title">风险因果链</h3>
        <div class="ir-causal-chain">
          <div v-for="(node, idx) in causalChain" :key="idx" class="ir-chain-node" :class="`ir-chain--${node.level}`">
            <div class="ir-chain-content">
              <span class="ir-chain-label">{{ node.label }}</span>
              <span class="ir-chain-time">{{ node.time }}</span>
              <span v-if="node.metric" class="ir-chain-metric">{{ node.metric }}</span>
            </div>
            <span v-if="Number(idx) < causalChain.length - 1" class="ir-chain-arrow">→</span>
          </div>
        </div>
      </div>

      <!-- 因果链为纯文本时的降级展示 -->
      <div v-else-if="causalChainText" class="ir-section">
        <h3 class="ir-section-title">风险因果链</h3>
        <p class="ir-causal-text">{{ causalChainText }}</p>
      </div>

      <!-- 行动建议 -->
      <div v-if="topActions.length" class="ir-section">
        <h3 class="ir-section-title">Top 3 行动建议</h3>
        <div class="ir-actions-grid">
          <div v-for="(action, idx) in topActions" :key="idx" class="ir-action-card" :class="`ir-action--${action.priority}`">
            <span class="ir-action-priority">{{ action.priorityLabel }}</span>
            <span class="ir-action-text">{{ action.text }}</span>
            <span class="ir-action-evidence">{{ action.evidence }}</span>
          </div>
        </div>
      </div>

      <!-- 证据链 -->
      <div v-if="evidenceList.length" class="ir-section">
        <h3 class="ir-section-title">原始告警证据</h3>
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
}

/* ── 状态栏 ── */
.ir-state-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 20px 24px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--border, #DCE3EC);
  font-size: 14px;
}

.ir-state-icon { font-size: 18px; }

.ir-state--loading { color: var(--text-secondary, #52606D); }
.ir-state--error { color: #991B1B; background: #FEF2F2; border-color: #FECACA; }
.ir-state--empty { color: var(--text-tertiary, #94A3B8); }
.ir-state--warning { color: #92400E; background: #FFFBEB; border-color: #FDE68A; }

.ir-retry-btn {
  margin-left: auto;
  padding: 4px 16px;
  border: 1px solid #DCE3EC;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
}
.ir-retry-btn:hover { background: #F8FAFC; }

.ir-causal-text {
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary, #52606D);
  margin: 0;
}

/* ── 态势结论 ── */
.ir-situation-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--border, #DCE3EC);
}

.ir-situation-icon { font-size: 10px; }
.ir-situation--critical { color: #991B1B; }
.ir-situation--high { color: #DC2626; }
.ir-situation--warning { color: #F59E0B; }
.ir-situation--normal { color: #16A34A; }

.ir-situation-text {
  flex: 1;
  font-size: 14px;
  font-weight: 600;
}

.ir-situation-time {
  font-size: 11px;
  color: var(--text-tertiary, #94A3B8);
}

/* ── 器官状态 ── */
.ir-organs-row {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
}

.ir-organ-card {
  background: #fff;
  border-radius: 8px;
  padding: 14px 10px;
  text-align: center;
  border: 1px solid var(--border, #DCE3EC);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.ir-organ--normal { border-bottom: 3px solid #16A34A; }
.ir-organ--impaired { border-bottom: 3px solid #F59E0B; }
.ir-organ--failure { border-bottom: 3px solid #DC2626; }

.ir-organ-icon { font-size: 24px; }
.ir-organ-name { font-size: 12px; color: var(--text-secondary, #52606D); }
.ir-organ-status { font-size: 13px; font-weight: 600; }

/* ── 通用 section ── */
.ir-section {
  background: #fff;
  border-radius: 8px;
  padding: 16px 20px;
  border: 1px solid var(--border, #DCE3EC);
}

.ir-section-title {
  margin: 0 0 14px;
  font-size: 14px;
  font-weight: 600;
}

/* ── 因果链 ── */
.ir-causal-chain {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}

.ir-chain-node {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ir-chain-content {
  padding: 10px 14px;
  border-radius: 6px;
  background: #F8FAFC;
  border: 1px solid var(--border, #DCE3EC);
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
}

.ir-chain-time {
  display: block;
  font-size: 10px;
  color: var(--text-tertiary, #94A3B8);
}

.ir-chain-metric {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--primary, #2563EB);
  font-family: var(--font-digit, monospace);
}

.ir-chain-arrow {
  font-size: 16px;
  color: var(--text-tertiary, #94A3B8);
  margin: 0 2px;
}

/* ── 行动建议 ── */
.ir-actions-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ir-action-card {
  display: grid;
  grid-template-columns: 60px 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 6px;
  background: #F8FAFC;
  border: 1px solid var(--border, #DCE3EC);
}

.ir-action--critical { border-left: 3px solid #991B1B; }
.ir-action--high { border-left: 3px solid #DC2626; }
.ir-action--medium { border-left: 3px solid #F59E0B; }
.ir-action--low { border-left: 3px solid #16A34A; }

.ir-action-priority {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  background: #E8EEF5;
  text-align: center;
}

.ir-action--critical .ir-action-priority { background: #FEF2F2; color: #991B1B; }
.ir-action--high .ir-action-priority { background: #FEF2F2; color: #DC2626; }

.ir-action-text {
  font-size: 13px;
}

.ir-action-evidence {
  font-size: 11px;
  color: var(--text-tertiary, #94A3B8);
}

/* ── 证据 ── */
.ir-evidence-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ir-evidence-item {
  display: grid;
  grid-template-columns: 80px 80px 1fr;
  gap: 8px;
  padding: 8px 0;
  border-bottom: 1px solid #F0F0F0;
  font-size: 12px;
}

.ir-evidence-time {
  color: var(--text-tertiary, #94A3B8);
  font-family: var(--font-mono, monospace);
}

.ir-evidence-type {
  font-weight: 500;
  padding: 1px 6px;
  border-radius: 3px;
  text-align: center;
}

.ir-ev--critical { background: #FEF2F2; color: #991B1B; }
.ir-ev--high { background: #FEF2F2; color: #DC2626; }
.ir-ev--warning { background: #FFFBEB; color: #92400E; }
.ir-ev--info { background: #EFF6FF; color: #1E40AF; }

@media (max-width: 1200px) {
  .ir-organs-row { grid-template-columns: repeat(3, 1fr); }
}
</style>
