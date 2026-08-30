<template>
  <div class="evidence">
    <!-- 患者上下文（脱敏） -->
    <div class="ev-question-card">
      <h3 class="ev-card-title">临床推理与循证</h3>
      <div class="ev-question-display">
        <span class="ev-question-text">{{ clinicalQuestion || '基于当前诊断的个体化推理' }}</span>
        <div class="ev-patient-context">
          <span v-if="patientContext.name" class="ev-ctx-item">患者：{{ patientContext.name }}</span>
          <span v-if="patientContext.bed" class="ev-ctx-item">{{ patientContext.bed }}床</span>
          <span v-if="patientContext.dept" class="ev-ctx-item">{{ patientContext.dept }}</span>
          <span v-if="patientContext.age" class="ev-ctx-item">{{ patientContext.age }}岁</span>
          <span v-if="dataCutoffTime" class="ev-ctx-item ev-ctx-time">数据截止：{{ dataCutoffTime }}</span>
        </div>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="ev-card">
      <h3 class="ev-card-title">个体化诊疗推理</h3>
      <div class="ev-skeleton">
        <div class="ev-skeleton-row"></div>
        <div class="ev-skeleton-row ev-skeleton-row--short"></div>
        <div class="ev-skeleton-row"></div>
      </div>
    </div>

    <!-- 错误状态 -->
    <div v-else-if="loadError" class="ev-card">
      <h3 class="ev-card-title">个体化诊疗推理</h3>
      <div class="ev-error">
        <span class="ev-error__icon">⚠</span>
        <span class="ev-error__text">{{ loadError }}</span>
        <button class="ev-retry-btn" @click="loadData">重试</button>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="reasoningState === 'empty'" class="ev-card">
      <h3 class="ev-card-title">个体化诊疗推理</h3>
      <div class="ev-empty-reasoning">
        <span class="ev-empty-icon">🧠</span>
        <span class="ev-empty-title">暂无足够证据生成推理</span>
        <span class="ev-empty-desc">当前患者数据不足以支持AI推理，请确认患者数据已同步或稍后重试</span>
      </div>
    </div>

    <!-- 推理结果 -->
    <template v-else-if="plan">
      <div class="ev-card">
        <h3 class="ev-card-title">个体化诊疗推理</h3>
        <div v-if="plan.core_problem" class="ev-section">
          <h4 class="ev-section-title">当前核心临床问题</h4>
          <p class="ev-section-text">{{ plan.core_problem }}</p>
        </div>
        <div v-if="plan.diagnosis" class="ev-section">
          <h4 class="ev-section-title">诊断推理</h4>
          <p class="ev-section-text">{{ plan.diagnosis }}</p>
        </div>
        <div v-if="plan.supporting_evidence" class="ev-section">
          <h4 class="ev-section-title">支持证据</h4>
          <p class="ev-section-text">{{ plan.supporting_evidence }}</p>
        </div>
        <div v-if="plan.opposing_evidence" class="ev-section">
          <h4 class="ev-section-title">反对证据</h4>
          <p class="ev-section-text">{{ plan.opposing_evidence }}</p>
        </div>
        <div v-if="plan.uncertainty" class="ev-section">
          <h4 class="ev-section-title">不确定性</h4>
          <p class="ev-section-text">{{ plan.uncertainty }}</p>
        </div>
        <div v-if="plan.risk_assessment" class="ev-section">
          <h4 class="ev-section-title">风险评估</h4>
          <p class="ev-section-text">{{ plan.risk_assessment }}</p>
        </div>
        <div v-if="plan.treatment_plan" class="ev-section">
          <h4 class="ev-section-title">治疗方案</h4>
          <p class="ev-section-text">{{ plan.treatment_plan }}</p>
        </div>
        <div v-if="plan.monitoring_plan" class="ev-section">
          <h4 class="ev-section-title">监测计划</h4>
          <p class="ev-section-text">{{ plan.monitoring_plan }}</p>
        </div>
        <div v-if="plan.recommended_data" class="ev-section">
          <h4 class="ev-section-title">推荐补充的数据</h4>
          <p class="ev-section-text">{{ plan.recommended_data }}</p>
        </div>
        <div v-if="plan.referenced_guidelines" class="ev-section">
          <h4 class="ev-section-title">参考指南</h4>
          <p class="ev-section-text">{{ plan.referenced_guidelines }}</p>
        </div>
        <div v-if="plan.reasoning_steps?.length" class="ev-section">
          <h4 class="ev-section-title">推理步骤</h4>
          <div class="ev-steps-list">
            <div v-for="(step, idx) in plan.reasoning_steps" :key="idx" class="ev-step-item">
              <span class="ev-step-num">{{ Number(idx) + 1 }}</span>
              <span class="ev-step-text">{{ step }}</span>
            </div>
          </div>
        </div>
        <div v-if="plan.rag_citations?.length" class="ev-section">
          <h4 class="ev-section-title">RAG引用 ({{ plan.rag_citations.length }})</h4>
          <div class="ev-citations-list">
            <div v-for="(c, idx) in plan.rag_citations" :key="idx" class="ev-citation-item">
              <span class="ev-citation-rank">{{ Number(idx) + 1 }}</span>
              <div class="ev-citation-content">
                <span v-if="c.source" class="ev-citation-source">{{ c.source }}</span>
                <p class="ev-citation-text">{{ c.text || c.content || c.chunk || '' }}</p>
              </div>
            </div>
          </div>
        </div>
        <!-- 时间信息 -->
        <div class="ev-meta-row">
          <span v-if="plan.generated_at" class="ev-meta-item">AI生成时间：{{ formatTime(plan.generated_at) }}</span>
          <span v-if="dataCutoffTime" class="ev-meta-item">数据截止：{{ dataCutoffTime }}</span>
        </div>
        <div class="ev-ai-disclaimer">⚠ AI生成，待临床确认。以上推理基于RAG检索的临床知识，仅供参考。</div>
      </div>
    </template>

    <!-- 知识库文档 -->
    <div class="ev-card">
      <h3 class="ev-card-title">可用知识库 ({{ indexedDocuments.length }}/{{ documents.length }})</h3>
      <!-- 加载中 -->
      <div v-if="docsState === 'loading'" class="ev-skeleton">
        <div class="ev-skeleton-row"></div>
        <div class="ev-skeleton-row ev-skeleton-row--short"></div>
      </div>
      <!-- 权限不足 -->
      <div v-else-if="docsState === 'forbidden'" class="ev-empty-docs">
        <span class="ev-empty-icon">🔒</span>
        <span class="ev-empty-title">当前账号无权访问临床知识库</span>
      </div>
      <!-- 接口错误 -->
      <div v-else-if="docsState === 'error'" class="ev-error">
        <span class="ev-error__icon">⚠</span>
        <span class="ev-error__text">{{ docsError }}</span>
        <button class="ev-retry-btn" @click="loadData">重试</button>
      </div>
      <!-- 无知识库 -->
      <div v-else-if="docsState === 'empty'" class="ev-empty-docs">
        <span class="ev-empty-icon">📚</span>
        <span class="ev-empty-title">当前没有配置可用知识库</span>
      </div>
      <!-- 全部未索引 -->
      <div v-else-if="docsState === 'unindexed'" class="ev-empty-docs">
        <span class="ev-empty-icon">📦</span>
        <span class="ev-empty-title">知识库已配置，但尚未完成索引</span>
        <span class="ev-empty-desc">当前无法用于循证检索。配置文档数：{{ documents.length }}，待索引：{{ unindexedDocuments.length }}</span>
      </div>
      <!-- 部分或全部已索引 -->
      <div v-else class="ev-docs-grid">
        <div v-for="doc in indexedDocuments" :key="doc.id || doc.filename || doc.name" class="ev-doc-item">
          <span class="ev-doc-icon">📄</span>
          <div class="ev-doc-info">
            <span class="ev-doc-name">{{ doc.title || doc.name || doc.filename || '未命名文档' }}</span>
            <div class="ev-doc-meta-row">
              <span v-if="doc.category || doc.document_type" class="ev-doc-tag">{{ doc.category || doc.document_type }}</span>
              <span v-if="doc.guideline_name" class="ev-doc-guideline">{{ doc.guideline_name }}</span>
              <span v-if="doc.institution" class="ev-doc-institution">{{ doc.institution }}</span>
              <span v-if="doc.version" class="ev-doc-version">v{{ doc.version }}</span>
              <span v-if="doc.publish_year" class="ev-doc-year">{{ doc.publish_year }}</span>
            </div>
            <div class="ev-doc-stats">
              <span class="ev-doc-chunks">可检索片段：{{ doc.chunk_count ?? doc.document_count ?? 0 }}</span>
              <span v-if="doc.status" class="ev-doc-status" :class="`ev-doc-status--${doc.status}`">
                {{ statusLabel(doc.status) }}
              </span>
            </div>
          </div>
        </div>
        <!-- 未索引文档折叠区 -->
        <details v-if="unindexedDocuments.length > 0" class="ev-unindexed-section">
          <summary>未完成索引的知识库 ({{ unindexedDocuments.length }})</summary>
          <div v-for="doc in unindexedDocuments" :key="doc.id || doc.filename || doc.name" class="ev-doc-item ev-doc-item--unindexed">
            <span class="ev-doc-icon">📄</span>
            <div class="ev-doc-info">
              <span class="ev-doc-name">{{ doc.title || doc.name || doc.filename || '未命名文档' }}</span>
              <span class="ev-doc-chunks">可检索片段：0</span>
            </div>
          </div>
        </details>
      </div>
    </div>

    <div class="ev-disclaimer">
      ⚠ 以上推理基于RAG检索的临床知识，仅供参考。临床决策请结合患者实际情况和专业判断。
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { getAiClinicalReasoning, getKnowledgeDocuments } from '../../../api'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'evidence',
  targetOrigin: window.location.origin,
  onPatientContextChanged: () => loadData(),
  onRefresh: () => loadData(),
})

const loading = ref(false)
const docsLoading = ref(false)
const loadError = ref('')
const docsError = ref('')
const docsForbidden = ref(false)
const plan = ref<any>(null)
const documents = ref<any[]>([])
const clinicalQuestion = ref('')
const patientContext = ref<{ name?: string; bed?: string; dept?: string; age?: number | string }>({})
const dataCutoffTime = ref('')

/** 请求序号：防止切换患者时旧请求覆盖新数据 */
let requestSeq = 0

const reasoningState = computed<'loading' | 'success' | 'empty' | 'error'>(() => {
  if (loading.value) return 'loading'
  if (loadError.value) return 'error'
  if (!plan.value) return 'empty'
  return 'success'
})

/** 已索引的文档（chunk_count > 0） */
const indexedDocuments = computed(() =>
  documents.value.filter(doc => Number(doc.chunk_count ?? doc.document_count ?? 0) > 0)
)

/** 未索引的文档（chunk_count === 0） */
const unindexedDocuments = computed(() =>
  documents.value.filter(doc => Number(doc.chunk_count ?? doc.document_count ?? 0) === 0)
)

/** 所有文档都未索引 */
const allDocumentsUnindexed = computed(() =>
  documents.value.length > 0 && indexedDocuments.value.length === 0
)

/** 知识库状态：loading | success | empty | unindexed | forbidden | error */
const docsState = computed(() => {
  if (docsLoading.value) return 'loading'
  if (docsForbidden.value) return 'forbidden'
  if (docsError.value) return 'error'
  if (documents.value.length === 0) return 'empty'
  if (allDocumentsUnindexed.value) return 'unindexed'
  return 'success'
})

function formatTime(t: string) {
  if (!t) return ''
  try { return new Date(t).toLocaleString('zh-CN') } catch { return t }
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    indexed: '已索引',
    active: '可用',
    indexing: '索引中',
    failed: '索引失败',
    disabled: '未启用',
    pending: '待索引',
  }
  return map[status] || '状态未知'
}

async function loadData() {
  if (!patientId.value || loading.value) return
  const seq = ++requestSeq
  const currentPatientId = patientId.value

  loading.value = true
  docsLoading.value = true
  loadError.value = ''
  docsError.value = ''
  docsForbidden.value = false
  // 清空上一位患者数据，防止切换时短暂展示旧数据
  plan.value = null
  documents.value = []
  patientContext.value = {}
  dataCutoffTime.value = ''
  try {
    const [reasoningRes, docsRes] = await Promise.allSettled([
      getAiClinicalReasoning(currentPatientId),
      getKnowledgeDocuments(),
    ])

    // 如果患者已切换，丢弃旧请求结果
    if (seq !== requestSeq || currentPatientId !== patientId.value) return

    // 临床推理计划（独立于知识库）
    if (reasoningRes.status === 'fulfilled') {
      const data = reasoningRes.value.data || {}
      plan.value = data.plan || null
      clinicalQuestion.value = data.plan?.clinical_question || '基于当前诊断的个体化推理'
      if (data.patient_context) {
        patientContext.value = data.patient_context
      }
      if (data.data_cutoff_time) {
        dataCutoffTime.value = formatTime(data.data_cutoff_time)
      }
    } else {
      loadError.value = reasoningRes.reason?.message || '加载临床推理失败'
    }

    // 知识库文档（独立于推理）
    if (docsRes.status === 'fulfilled') {
      const data = docsRes.value.data || {}
      documents.value = data.documents || data.items || []
    } else {
      const err = docsRes.reason
      const status = err?.response?.status
      if (status === 401) docsError.value = '登录状态已失效，请重新登录'
      else if (status === 403) { docsError.value = '当前账号无权访问临床知识库'; docsForbidden.value = true }
      else if (status === 404) docsError.value = '知识库服务未配置'
      else if (status >= 500) docsError.value = '知识库加载失败，请稍后重试'
      else docsError.value = err?.message || '知识库加载失败'
      documents.value = []
    }
  } catch (e: any) {
    if (seq !== requestSeq) return
    loadError.value = e?.message || '加载循证数据失败'
    sendReportError('LOAD_FAILED', e?.message || '加载循证数据失败')
  } finally {
    if (seq === requestSeq) {
      loading.value = false
      docsLoading.value = false
    }
  }
}

onMounted(() => {
  sendUpdateTitle('循证查询')
  loadData()
})
</script>

<style scoped>
.evidence { display: flex; flex-direction: column; gap: 14px; }

.ev-question-card { background: #F0F5FF; border: 1px solid #BDDEFF; border-radius: 8px; padding: 16px; }
.ev-card-title { margin: 0 0 10px; font-size: 14px; font-weight: 600; color: #182230; }
.ev-question-display { display: flex; flex-direction: column; gap: 6px; }
.ev-question-text { font-size: 15px; color: #182230; }

.ev-patient-context {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #52606D;
}

.ev-ctx-item {
  padding: 2px 8px;
  background: rgba(255,255,255,0.6);
  border-radius: 4px;
}

.ev-ctx-time {
  color: #94A3B8;
}

.ev-loading, .ev-empty { text-align: center; padding: 40px 20px; color: #94A3B8; font-size: 14px; }
.ev-empty-icon { display: block; font-size: 32px; margin-bottom: 8px; }

.ev-card { background: #fff; border-radius: 8px; padding: 16px; border: 1px solid #DCE3EC; }

.ev-skeleton { display: flex; flex-direction: column; gap: 10px; padding: 12px 0; }
.ev-skeleton-row {
  height: 16px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: skeleton-pulse 1.5s infinite;
  border-radius: 4px;
}
.ev-skeleton-row--short { width: 60%; }
@keyframes skeleton-pulse {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.ev-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px;
  text-align: center;
}
.ev-error__icon { font-size: 24px; }
.ev-error__text { font-size: 13px; color: #52606D; }
.ev-retry-btn {
  padding: 4px 16px;
  border: 1px solid #DCE3EC;
  border-radius: 4px;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  color: #2563EB;
}

.ev-empty-reasoning {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 20px;
  text-align: center;
}
.ev-empty-title { font-size: 14px; font-weight: 600; color: #182230; }
.ev-empty-desc { font-size: 12px; color: #94A3B8; max-width: 400px; }

.ev-section { margin-top: 14px; }
.ev-section:first-child { margin-top: 0; }
.ev-section-title { margin: 0 0 8px; font-size: 13px; font-weight: 600; color: #2563EB; }
.ev-section-text { margin: 0; font-size: 13px; line-height: 1.6; color: #334155; white-space: pre-wrap; }

.ev-steps-list { display: flex; flex-direction: column; gap: 8px; }
.ev-step-item { display: flex; gap: 10px; padding: 8px 12px; background: #F8FAFC; border-radius: 6px; }
.ev-step-num { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; background: #2563EB; color: #fff; border-radius: 50%; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.ev-step-text { font-size: 13px; line-height: 1.5; color: #334155; }

.ev-citations-list { display: flex; flex-direction: column; gap: 8px; }
.ev-citation-item { display: flex; gap: 10px; padding: 10px 12px; background: #F8FAFC; border-radius: 6px; border: 1px solid #E8EEF5; }
.ev-citation-rank { width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; background: #E8EEF5; border-radius: 50%; font-size: 11px; font-weight: 600; flex-shrink: 0; }
.ev-citation-content { flex: 1; }
.ev-citation-source { font-size: 11px; color: #2563EB; font-weight: 500; }
.ev-citation-text { margin: 4px 0 0; font-size: 12px; line-height: 1.5; color: #52606D; }

.ev-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #E8EEF5;
  font-size: 11px;
  color: #94A3B8;
}

.ev-ai-disclaimer {
  margin-top: 10px;
  padding: 8px 12px;
  background: #FFFBEB;
  border: 1px solid #FDE68A;
  border-radius: 6px;
  font-size: 12px;
  color: #92400E;
}

.ev-docs-grid { display: flex; flex-direction: column; gap: 8px; }
.ev-doc-item { display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; background: #F8FAFC; border-radius: 6px; border: 1px solid #E8EEF5; }
.ev-doc-icon { font-size: 20px; flex-shrink: 0; margin-top: 2px; }
.ev-doc-info { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.ev-doc-name { font-size: 13px; font-weight: 600; color: #182230; }

.ev-doc-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 11px;
}

.ev-doc-tag {
  padding: 1px 6px;
  background: #EFF6FF;
  color: #1E40AF;
  border-radius: 3px;
}

.ev-doc-guideline {
  color: #52606D;
}

.ev-doc-institution {
  color: #94A3B8;
}

.ev-doc-version {
  color: #2563EB;
  font-weight: 500;
}

.ev-doc-year {
  color: #94A3B8;
}

.ev-doc-stats {
  display: flex;
  gap: 10px;
  font-size: 11px;
}

.ev-doc-chunks {
  color: #52606D;
}

.ev-doc-status {
  font-weight: 500;
}

.ev-doc-status--indexed, .ev-doc-status--active { color: #16A34A; }
.ev-doc-status--indexing { color: #F59E0B; }
.ev-doc-status--failed { color: #DC2626; }
.ev-doc-status--disabled, .ev-doc-status--pending { color: #94A3B8; }

.ev-empty-docs {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 32px 20px;
  text-align: center;
}

.ev-disclaimer { padding: 10px 16px; background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; font-size: 12px; color: #92400E; }

.ev-unindexed-section {
  margin-top: 8px;
  border: 1px solid #E8EEF5;
  border-radius: 6px;
  overflow: hidden;
}
.ev-unindexed-section summary {
  padding: 8px 12px;
  font-size: 12px;
  color: #94A3B8;
  cursor: pointer;
  background: #F8FAFC;
}
.ev-unindexed-section summary:hover { background: #F0F5FF; }
.ev-doc-item--unindexed { opacity: 0.6; }
</style>
