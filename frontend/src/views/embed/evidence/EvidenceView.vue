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
      <h3 class="ev-card-title">可用知识库 ({{ documents.length }})</h3>
      <div v-if="docsLoading" class="ev-skeleton">
        <div class="ev-skeleton-row"></div>
        <div class="ev-skeleton-row ev-skeleton-row--short"></div>
      </div>
      <div v-else-if="documents.length" class="ev-docs-grid">
        <div v-for="doc in documents" :key="doc.id || doc.filename || doc.name" class="ev-doc-item">
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
      </div>
      <div v-else class="ev-empty-docs">
        <span class="ev-empty-icon">📚</span>
        <span class="ev-empty-title">暂无可用知识库</span>
        <span class="ev-empty-desc">知识库可能未完成索引、无访问权限或接口异常</span>
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
const plan = ref<any>(null)
const documents = ref<any[]>([])
const clinicalQuestion = ref('')
const patientContext = ref<{ name?: string; bed?: string; dept?: string; age?: number | string }>({})
const dataCutoffTime = ref('')

const reasoningState = computed<'loading' | 'success' | 'empty' | 'error'>(() => {
  if (loading.value) return 'loading'
  if (loadError.value) return 'error'
  if (!plan.value) return 'empty'
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
  return map[status] || status
}

async function loadData() {
  if (!patientId.value || loading.value) return
  loading.value = true
  loadError.value = ''
  try {
    const [reasoningRes, docsRes] = await Promise.allSettled([
      getAiClinicalReasoning(patientId.value),
      getKnowledgeDocuments(),
    ])

    // 临床推理计划
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

    // 知识库文档
    docsLoading.value = true
    if (docsRes.status === 'fulfilled') {
      const data = docsRes.value.data || {}
      documents.value = data.documents || data.items || []
    }
  } catch (e: any) {
    loadError.value = e?.message || '加载循证数据失败'
    sendReportError('LOAD_FAILED', e?.message || '加载循证数据失败')
  } finally {
    loading.value = false
    docsLoading.value = false
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
</style>
