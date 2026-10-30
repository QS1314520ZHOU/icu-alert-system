<template>
  <div class="integrated-risk">
    <div v-if="loading" class="ir-state ir-state--loading">
      <span class="ir-state__text">正在分析综合风险……</span>
    </div>
    <div v-else-if="loadError" class="ir-state ir-state--error">
      <span class="ir-state__text">{{ loadError }}</span>
      <button class="ir-retry-btn" @click="loadData">重试</button>
    </div>
    <div v-else-if="!report" class="ir-state ir-state--empty">
      <span class="ir-state__text">暂无可用综合风险报告</span>
    </div>

    <template v-else>
      <div v-if="report.stale" class="ir-state ir-state--warning">
        <span class="ir-state__text">当前展示最近一次综合风险报告（{{ updatedAt }}），AI服务额度不足，暂时无法更新，请结合最新床旁情况判断。</span>
      </div>

      <!-- 结论：等级 + 一句话态势 + 等级是怎么来的 -->
      <div class="ir-section ir-conclusion" :class="`ir-conclusion--${riskLevel}`">
        <div class="ir-card-header">
          <span class="ir-situation-dot" :class="`ir-dot--${riskLevel}`" />
          <h3 class="ir-card-title">综合风险：{{ RISK_LEVEL_LABELS[riskLevel] }}</h3>
          <span class="ir-source" :class="sourceIsLlm ? 'ir-source--ai' : 'ir-source--rule'">{{ sourceLabel }}</span>
          <span class="ir-card-time">报告时间 {{ updatedAt || '—' }}</span>
        </div>
        <p class="ir-situation-text">{{ situationText || '综合风险分析完成' }}</p>
        <p class="ir-basis">
          <b>等级依据：</b>{{ levelBasis }}
        </p>
      </div>

      <!-- 多器官状态（旧版报告/外部模型提供时展示） -->
      <div v-if="organs.length" class="ir-section">
        <div class="ir-section-header">
          <h3 class="ir-section-title">多器官状态</h3>
        </div>
        <div class="ir-organs-grid">
          <div v-for="organ in organs" :key="organ.key" class="ir-organ-item" :class="`ir-organ--${organ.status}`">
            <span class="ir-organ-name">{{ organ.label }}</span>
            <span class="ir-organ-status">{{ organ.statusText }}</span>
            <span v-if="organ.basis" class="ir-organ-basis">{{ organ.basis }}</span>
          </div>
        </div>
      </div>

      <!-- 第1步：输入了哪些告警 -->
      <div class="ir-section">
        <div class="ir-section-header">
          <h3 class="ir-section-title"><span class="ir-step">1</span>输入数据：活跃告警按器官系统归类</h3>
          <span class="ir-section-hint">共 {{ density.total_alerts ?? alertTotal }} 条，纳入推理的告警 ID {{ sourceAlertCount }} 个</span>
        </div>
        <div v-if="density.total_alerts !== undefined" class="ir-density">
          <span class="ir-density__item">危急 <b class="ir-c-critical">{{ density.critical_count ?? 0 }}</b></span>
          <span class="ir-density__item">高危 <b class="ir-c-high">{{ density.high_count ?? 0 }}</b></span>
          <span class="ir-density__item">回看窗口前半段 <b>{{ density.early_half_count ?? 0 }}</b> 条 → 后半段 <b>{{ density.late_half_count ?? 0 }}</b> 条</span>
          <span class="ir-density__trend" :class="density.accelerating ? 'ir-c-critical' : ''">
            {{ density.accelerating ? '告警密度加速（后半段比前半段多≥2条）' : '告警密度未明显加速' }}
          </span>
        </div>
        <div v-if="alertGroups.length" class="ir-groups">
          <details v-for="g in alertGroups" :key="g.system" class="ir-group" :open="g.rank >= 2">
            <summary class="ir-group__head">
              <span class="ir-group__name">{{ g.system }}</span>
              <span class="ir-evidence-type" :class="`ir-ev--${g.highest}`">{{ SEVERITY_LABELS[g.highest] || g.highest }}</span>
              <span class="ir-group__count">{{ g.count }} 条</span>
            </summary>
            <div v-for="a in g.alerts" :key="a.alert_id || a.title + a.timestamp" class="ir-evidence-item">
              <span class="ir-evidence-time">{{ fmtTime(a.timestamp) }}</span>
              <span class="ir-evidence-type" :class="`ir-ev--${a.level || 'info'}`">{{ SEVERITY_LABELS[a.level] || a.level || '—' }}</span>
              <span class="ir-evidence-text">
                {{ a.title }}
                <span v-for="kv in detailPairs(a.detail)" :key="kv" class="ir-kv">{{ kv }}</span>
              </span>
            </div>
          </details>
        </div>
        <p v-else-if="evidenceList.length === 0" class="ir-causal-text">报告未保存告警明细（旧版报告），请在“告警”页查看原始记录。</p>
        <div v-if="evidenceList.length" class="ir-evidence-list">
          <div v-for="(ev, idx) in evidenceList" :key="idx" class="ir-evidence-item">
            <span class="ir-evidence-time">{{ ev.time }}</span>
            <span class="ir-evidence-type" :class="`ir-ev--${ev.level}`">{{ ev.type }}</span>
            <span class="ir-evidence-text">{{ ev.text }}</span>
          </div>
        </div>
      </div>

      <!-- 第2步：推理过程 -->
      <div v-if="causalChain.length || causalChainText || forecastText || differentials.length" class="ir-section">
        <div class="ir-section-header">
          <h3 class="ir-section-title"><span class="ir-step">2</span>推理过程</h3>
        </div>
        <div v-if="causalChain.length || causalChainText" class="ir-reason-block">
          <h4 class="ir-h4">病理生理关联（风险因果链）</h4>
          <div v-if="causalChain.length" class="ir-causal-chain">
            <div v-for="(node, idx) in causalChain" :key="idx" class="ir-chain-node" :class="`ir-chain--${node.level}`">
              <div class="ir-chain-content">
                <span class="ir-chain-label">{{ node.label }}</span>
                <span v-if="node.time" class="ir-chain-time">{{ node.time }}</span>
                <span v-if="node.metric" class="ir-chain-metric">{{ node.metric }}</span>
              </div>
              <span v-if="Number(idx) < causalChain.length - 1" class="ir-chain-arrow">→</span>
            </div>
          </div>
          <p v-else class="ir-causal-text">{{ causalChainText }}</p>
        </div>
        <div v-if="forecastText" class="ir-reason-block">
          <h4 class="ir-h4">未来 4–12 小时恶化预判</h4>
          <p class="ir-causal-text">{{ forecastText }}</p>
        </div>
        <div v-if="differentials.length" class="ir-reason-block">
          <h4 class="ir-h4">需要鉴别 / 排除</h4>
          <ol class="ir-diff">
            <li v-for="d in differentials" :key="d">{{ d }}</li>
          </ol>
        </div>
      </div>

      <!-- 第3步：行动建议，带理由和时限 -->
      <div v-if="topActions.length" class="ir-section">
        <div class="ir-section-header">
          <h3 class="ir-section-title"><span class="ir-step">3</span>行动建议（按时限排序）</h3>
        </div>
        <div class="ir-actions-list">
          <div v-for="(action, idx) in topActions" :key="idx" class="ir-action-item" :class="`ir-action--${action.priority}`">
            <div class="ir-action-badge">{{ action.urgencyLabel }}</div>
            <div class="ir-action-content">
              <p class="ir-action-text">{{ action.text }}</p>
              <p v-if="action.evidence" class="ir-action-evidence">理由：{{ action.evidence }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 参考知识 -->
      <div v-if="ragHits.length" class="ir-section">
        <div class="ir-section-header">
          <h3 class="ir-section-title">参考的知识库条目（{{ ragHits.length }}）</h3>
        </div>
        <div class="ir-evidence-list">
          <div v-for="(h, idx) in ragHits" :key="h.chunk_id || idx" class="ir-rag">
            <div class="ir-rag__src">{{ h.source || '知识库' }}<span v-if="h.recommendation" class="ir-kv">{{ h.recommendation }}</span></div>
            <div class="ir-rag__content">{{ h.content }}</div>
          </div>
        </div>
      </div>

      <p class="ir-disclaimer">
        本报告由{{ sourceIsLlm ? '大模型基于上述告警整合生成' : '规则模板在 AI 不可用时自动生成（未做个体化推理）' }}，仅作临床决策参考，须由主管医生结合床旁评估确认。
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getAiIntegratedRiskReport } from '../../../api'

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
  return []
}

function normalizeOrganStatus(value: unknown): any[] {
  if (Array.isArray(value)) return value
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).map(([organ, detail]) => ({
      organ,
      ...(detail && typeof detail === 'object' ? detail : { status: detail }),
    }))
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
    _causal_chain_text: typeof chainRaw === 'string' ? chainRaw.trim() : '',
    top_actions: asArray(raw.top_actions?.length ? raw.top_actions : raw.top3_actions),
    evidence: asArray(raw.evidence),
  }
}

const RISK_LEVEL_LABELS: Record<string, string> = { critical: '危急', high: '高危', warning: '需关注', normal: '平稳' }
const SEVERITY_LABELS: Record<string, string> = { critical: '危急', high: '高危', warning: '警告', info: '提示' }
const SEVERITY_RANK: Record<string, number> = { critical: 3, high: 2, warning: 1 }

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'integrated-risk',
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => loadData(),
  onRefresh: () => loadData(),
})

const loading = ref(false)
const loadError = ref('')
const report = ref<any | null>(null)

const riskLevel = computed(() => {
  const s = String(report.value?.risk_level || '').toLowerCase()
  if (s.includes('critical') || s.includes('危')) return 'critical'
  if (s.includes('high') || s.includes('高')) return 'high'
  if (s.includes('warning') || s.includes('警告')) return 'warning'
  return 'normal'
})

const sourceIsLlm = computed(() => String(report.value?.analysis_source || '') === 'llm')
const sourceLabel = computed(() => {
  const s = String(report.value?.analysis_source || '')
  if (s === 'llm') return 'AI 推理'
  if (s === 'heuristic_fallback') return '规则兜底（AI 未参与）'
  return s || '来源未标注'
})

function fmtTime(t: unknown): string {
  if (!t) return ''
  const d = new Date(String(t))
  if (Number.isNaN(d.getTime())) return String(t)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

const situationText = computed(() => report.value?.situation_summary || report.value?.summary || '')
const updatedAt = computed(() => fmtTime(report.value?.updated_at || report.value?.created_at))
const forecastText = computed(() => String(report.value?.deterioration_forecast || '').trim())
const differentials = computed(() => asArray(report.value?.differential_diagnosis).map(String).filter(Boolean))
const density = computed<Record<string, any>>(() => (report.value?.density && typeof report.value.density === 'object') ? report.value.density : {})
const sourceAlertCount = computed(() => asArray(report.value?.source_alert_ids).length)

const alertGroups = computed(() => {
  const g = report.value?.grouped_alerts
  if (!g || typeof g !== 'object') return []
  return Object.entries(g as Record<string, any>)
    .map(([system, row]) => {
      const highest = String(row?.highest_severity || 'warning')
      return {
        system,
        count: Number(row?.count || asArray(row?.alerts).length),
        highest,
        rank: SEVERITY_RANK[highest] || 0,
        alerts: asArray(row?.alerts)
          .slice()
          .sort((a: any, b: any) => String(b?.timestamp || '').localeCompare(String(a?.timestamp || ''))),
      }
    })
    .sort((a, b) => b.rank - a.rank || b.count - a.count)
})
const alertTotal = computed(() => alertGroups.value.reduce((n, g) => n + g.count, 0))

/** 从告警 extra 里挑出可读的数值字段，展示“触发时的实际值” */
const DETAIL_SKIP = new Set(['patient_id', 'rule_id', 'alert_id', 'id', '_id', 'explanation', 'suggestion', 'summary', 'text', 'evidence', 'detail'])
function detailPairs(detail: unknown): string[] {
  if (!detail || typeof detail !== 'object') return []
  const out: string[] = []
  for (const [k, v] of Object.entries(detail as Record<string, unknown>)) {
    if (DETAIL_SKIP.has(k)) continue
    if (typeof v === 'number') out.push(`${k}=${Number.isInteger(v) ? v : v.toFixed(2)}`)
    else if (typeof v === 'string' && v.length <= 24 && v.trim()) out.push(`${k}=${v}`)
    else if (typeof v === 'boolean' && v) out.push(k)
    if (out.length >= 4) break
  }
  return out
}

const organs = computed(() => {
  const labels: Record<string, string> = { respiratory: '呼吸', circulatory: '循环', renal: '肾脏', coagulation: '凝血', hepatic: '肝脏', neurologic: '神经' }
  const statusTexts: Record<string, string> = { normal: '正常', impaired: '受损', failure: '衰竭' }
  return asArray(report.value?.organ_status).map((o: any) => {
    const key = o.organ || o.key
    const basis = [o.metric, o.value !== undefined ? `${o.value}${o.unit || ''}` : '', o.reason || o.evidence]
      .filter((x) => x !== undefined && x !== null && String(x).trim()).map(String).join(' · ')
    return {
      key,
      label: labels[key] || key,
      status: o.status || 'normal',
      statusText: statusTexts[o.status] || o.status || '—',
      basis,
    }
  })
})

const causalChain = computed(() =>
  asArray(report.value?.causal_chain).map((c: any) => ({
    label: c?.label || c?.event || '',
    time: c?.time || '',
    metric: c?.metric || '',
    level: c?.level || 'info',
  })),
)
const causalChainText = computed(() => report.value?._causal_chain_text || '')

function urgencyPriority(min: number): string {
  if (min < 30) return 'critical'
  if (min <= 120) return 'high'
  return 'medium'
}
function urgencyLabel(min: number): string {
  if (!Number.isFinite(min)) return '建议'
  if (min < 60) return `${min} 分钟内`
  const h = min / 60
  return `${Number.isInteger(h) ? h : h.toFixed(1)} 小时内`
}

const topActions = computed(() => {
  const priorityLabels: Record<string, string> = { critical: '紧急', high: '重要', medium: '建议', low: '参考' }
  return asArray(report.value?.top_actions)
    .map((a: any) => {
      const urgency = Number(a?.urgency)
      const hasUrgency = Number.isFinite(urgency) && urgency > 0
      const p = typeof a?.priority === 'string' && priorityLabels[a.priority]
        ? a.priority
        : (hasUrgency ? urgencyPriority(urgency) : 'medium')
      return {
        text: a?.text || a?.action || '',
        priority: p,
        urgency: hasUrgency ? urgency : Number.POSITIVE_INFINITY,
        urgencyLabel: hasUrgency ? urgencyLabel(urgency) : (priorityLabels[p] || '建议'),
        evidence: a?.evidence || a?.rationale || '',
      }
    })
    .filter((a) => a.text)
    .sort((a, b) => a.urgency - b.urgency)
    .slice(0, 3)
})

const levelBasis = computed(() => {
  const finite = topActions.value.filter((a) => Number.isFinite(a.urgency))
  if (finite.length) {
    const min = Math.min(...finite.map((a) => a.urgency))
    return `最紧急行动需在 ${urgencyLabel(min)} 完成（<30 分钟=危急，30–120 分钟=高危，>120 分钟=需关注）；最高告警级别 ${SEVERITY_LABELS[String(density.value.highest_severity)] || density.value.highest_severity || '—'}。`
  }
  return `由最高告警级别（${SEVERITY_LABELS[String(density.value.highest_severity)] || '未知'}）及告警数量综合判定。`
})

const ragHits = computed(() => asArray(report.value?.rag_hits).filter((h: any) => h && (h.content || h.recommendation)))

const evidenceList = computed(() =>
  asArray(report.value?.evidence).map((e: any) => ({
    time: e?.time || '',
    type: e?.type || e?.alert_type || '',
    text: e?.text || e?.description || '',
    level: e?.level || e?.severity || 'info',
  })),
)

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
.ir-organ-basis { font-size: 11px; color: var(--color-text-secondary, #4B5563); text-align: center }
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


/* ── 过程化展示补充 ── */ .ir-conclusion--critical { border-left: 4px solid var(--color-critical, #D92D20) }
.ir-conclusion--high { border-left: 4px solid var(--color-danger, #D92D20) }
.ir-conclusion--warning { border-left: 4px solid var(--color-warning, #B54708) }
.ir-basis { margin: 0; padding: 0 18px 14px; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); line-height: 1.6 }
.ir-source { font-size: var(--text-caption, 12px); padding: 2px 8px; border-radius: var(--radius-tag, 4px) }
.ir-source--ai { background: var(--color-ai-bg, #F5F3FF); color: var(--color-ai, #7C3AED) }
.ir-source--rule { background: var(--color-warning-soft-bg, #FFF9D8); color: var(--color-warning, #B54708) }
.ir-section-header { display: flex; align-items: center; justify-content: space-between; gap: 12px }
.ir-section-hint { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }
.ir-step { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; margin-right: 8px; border-radius: 50%; background: var(--color-primary-bg, #EFF6FF); color: var(--color-primary, #2563EB); font-size: 11px; font-weight: 700 }
.ir-density { display: flex; flex-wrap: wrap; gap: 16px; padding: 12px 18px; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); border-bottom: 1px solid var(--color-border, #E5E7EB) }
.ir-density__trend { margin-left: auto; font-weight: 600 }
.ir-c-critical { color: var(--color-critical, #D92D20) }
.ir-c-high { color: var(--color-danger, #D92D20) }
.ir-groups { padding: 4px 18px 12px }
.ir-group { border-bottom: 1px solid var(--color-border, #E5E7EB) }
.ir-group:last-child { border-bottom: none }
.ir-group__head { display: flex; align-items: center; gap: 10px; padding: 10px 0; cursor: pointer; list-style: none }
.ir-group__head::-webkit-details-marker { display: none }
.ir-group__head::before { content: '▸'; color: var(--color-text-tertiary, #9CA3AF) }
.ir-group[open] > .ir-group__head::before { content: '▾' }
.ir-group__name { font-weight: 600; color: var(--color-text-primary, #111827); font-size: var(--text-body, 13px) }
.ir-group__count { margin-left: auto; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.ir-group .ir-evidence-item { grid-template-columns: 90px 56px 1fr; padding: 8px 0 8px 18px }
.ir-kv { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: var(--radius-tag, 4px); background: var(--color-bg-surface-secondary, #F1F4F8); font-family: 'SF Mono', Consolas, monospace; font-size: 11px; color: var(--color-text-secondary, #4B5563) }
.ir-reason-block { border-bottom: 1px solid var(--color-border, #E5E7EB) }
.ir-reason-block:last-child { border-bottom: none }
.ir-h4 { margin: 0; padding: 12px 18px 0; font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-text-tertiary, #9CA3AF) }
.ir-diff { margin: 0; padding: 8px 18px 14px 36px; font-size: var(--text-body, 13px); color: var(--color-text-secondary, #4B5563); line-height: 1.8 }
.ir-rag { padding: 10px 0; border-bottom: 1px solid var(--color-border, #E5E7EB) }
.ir-rag:last-child { border-bottom: none }
.ir-rag__src { font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-text-primary, #111827) }
.ir-rag__content { margin-top: 4px; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); line-height: 1.6 }
.ir-disclaimer { margin: 0; font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF); text-align: center }

/* ── 响应式 ── */

@media (max-width: 1200px) {.ir-overview-row { grid-template-columns: 1fr }
.ir-organs-grid { grid-template-columns: repeat(3, 1fr) }

}

@media (max-width: 768px) {.ir-organs-grid { grid-template-columns: repeat(2, 1fr) }
.ir-evidence-item { grid-template-columns: 1fr; gap: 4px }

}

</style>
