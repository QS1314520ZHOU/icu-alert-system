<template>
  <div class="evidence">
    <!-- 临床问题 -->
    <div class="ev-question-card">
      <h3 class="ev-card-title">临床推理与循证</h3>
      <div class="ev-question-display">
        <span class="ev-question-text">{{ clinicalQuestion || '基于当前诊断的个体化推理' }}</span>
        <span class="ev-question-patient">患者：{{ patientId }}</span>
      </div>
    </div>

    <!-- 加载状态 -->
    <div v-if="loading" class="ev-loading">正在进行临床推理...</div>

    <!-- 空状态 -->
    <div v-else-if="!plan && !documents.length" class="ev-empty">
      <span class="ev-empty-icon">📚</span>
      <span>暂无循证数据，请稍后重试</span>
    </div>

    <!-- 临床推理计划 -->
    <template v-else>
      <div v-if="plan" class="ev-card">
        <h3 class="ev-card-title">个体化诊疗推理</h3>
        <div v-if="plan.diagnosis" class="ev-section">
          <h4 class="ev-section-title">诊断推理</h4>
          <p class="ev-section-text">{{ plan.diagnosis }}</p>
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
        <div v-if="plan.evidence_summary" class="ev-section">
          <h4 class="ev-section-title">循证依据</h4>
          <p class="ev-section-text">{{ plan.evidence_summary }}</p>
        </div>
        <div v-if="plan.reasoning_steps?.length" class="ev-section">
          <h4 class="ev-section-title">推理步骤</h4>
          <div class="ev-steps-list">
            <div v-for="(step, idx) in plan.reasoning_steps" :key="idx" class="ev-step-item">
              <span class="ev-step-num">{{ idx + 1 }}</span>
              <span class="ev-step-text">{{ step }}</span>
            </div>
          </div>
        </div>
        <div v-if="plan.rag_citations?.length" class="ev-section">
          <h4 class="ev-section-title">RAG引用 ({{ plan.rag_citations.length }})</h4>
          <div class="ev-citations-list">
            <div v-for="(c, idx) in plan.rag_citations" :key="idx" class="ev-citation-item">
              <span class="ev-citation-rank">{{ idx + 1 }}</span>
              <div class="ev-citation-content">
                <span v-if="c.source" class="ev-citation-source">{{ c.source }}</span>
                <p class="ev-citation-text">{{ c.text || c.content || c.chunk || '' }}</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 知识库文档 -->
      <div v-if="documents.length" class="ev-card">
        <h3 class="ev-card-title">可用知识库 ({{ documents.length }})</h3>
        <div class="ev-docs-grid">
          <div v-for="doc in documents" :key="doc.id || doc.filename" class="ev-doc-item">
            <span class="ev-doc-icon">📄</span>
            <div class="ev-doc-info">
              <span class="ev-doc-name">{{ doc.filename || doc.name || '' }}</span>
              <span class="ev-doc-meta">{{ doc.chunk_count || 0 }} 个片段</span>
            </div>
          </div>
        </div>
      </div>
    </template>

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
  targetOrigin: '*',
  onPatientContextChanged: () => loadData(),
  onRefresh: () => loadData(),
})

const loading = ref(false)
const plan = ref<any>(null)
const documents = ref<any[]>([])
const clinicalQuestion = ref('')

async function loadData() {
  if (!patientId.value || loading.value) return
  loading.value = true
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
    }

    // 知识库文档
    if (docsRes.status === 'fulfilled') {
      const data = docsRes.value.data || {}
      documents.value = data.documents || data.items || []
    }
  } catch (e: any) {
    sendReportError('LOAD_FAILED', e?.message || '加载循证数据失败')
  } finally {
    loading.value = false
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
.ev-question-display { display: flex; flex-direction: column; gap: 4px; }
.ev-question-text { font-size: 15px; color: #182230; }
.ev-question-patient { font-size: 12px; color: #52606D; }

.ev-loading, .ev-empty { text-align: center; padding: 40px 20px; color: #94A3B8; font-size: 14px; }
.ev-empty-icon { display: block; font-size: 32px; margin-bottom: 8px; }

.ev-card { background: #fff; border-radius: 8px; padding: 16px; border: 1px solid #DCE3EC; }

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

.ev-docs-grid { display: flex; flex-direction: column; gap: 8px; }
.ev-doc-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; background: #F8FAFC; border-radius: 6px; border: 1px solid #E8EEF5; }
.ev-doc-icon { font-size: 20px; }
.ev-doc-info { display: flex; flex-direction: column; gap: 2px; }
.ev-doc-name { font-size: 13px; font-weight: 500; color: #182230; }
.ev-doc-meta { font-size: 11px; color: #94A3B8; }

.ev-disclaimer { padding: 10px 16px; background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; font-size: 12px; color: #92400E; }
</style>
