<template>
  <div class="vcr-page">
    <header class="vcr-header">
      <div>
        <h1>语音查房纠错 Review</h1>
        <p>系统性错例候选清单。采纳后自动写回 correction_hints.yaml 并热重载。</p>
      </div>
      <div class="header-actions">
        <a-button :loading="loading" @click="loadCandidates">刷新</a-button>
        <a-button :loading="reloading" @click="reloadHints">重载 Hints</a-button>
      </div>
    </header>

    <section v-if="error" class="vcr-error">
      <strong>加载失败</strong>
      <span>{{ error }}</span>
      <a-button size="small" @click="loadCandidates">重试</a-button>
    </section>

    <!-- 药名严审区（置顶） -->
    <section v-if="drugCandidates.length" class="vcr-drug-warning">
      <h2>⚠️ 药名易混严审区</h2>
      <p>以下候选涉及易混药名，<strong>禁止走快速采纳</strong>，必须由临床负责人在 yaml 中手动审定。</p>
      <table class="vcr-table">
        <thead>
          <tr>
            <th>Before</th>
            <th>After</th>
            <th>出现次数</th>
            <th>跨医生</th>
            <th>系统性分</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in drugCandidates" :key="c._id" class="vcr-row-drug">
            <td><code>{{ c.before_variants.join(' / ') }}</code></td>
            <td><code>{{ c.after }}</code></td>
            <td>{{ c.count }}</td>
            <td>{{ c.distinct_actors }}</td>
            <td>{{ c.systematic_score }}</td>
            <td>
              <a-button size="small" danger @click="reject(c)">驳回</a-button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 普通候选 -->
    <section class="vcr-main">
      <h2>待审候选（{{ nonDrugCandidates.length }}）</h2>
      <table v-if="nonDrugCandidates.length" class="vcr-table">
        <thead>
          <tr>
            <th>建议归类</th>
            <th>Before 变体</th>
            <th>统一 After</th>
            <th>出现次数</th>
            <th>跨医生</th>
            <th>跨患者</th>
            <th>系统性分</th>
            <th>方向一致性</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in nonDrugCandidates" :key="c._id">
            <td>
              <select v-model="c._targetCategory" class="vcr-category-select">
                <option value="accent_errors">口音错字</option>
                <option value="dialect_phrases">方言口语</option>
              </select>
            </td>
            <td><code>{{ c.before_variants.join(' / ') }}</code></td>
            <td><code>{{ c.after }}</code></td>
            <td>{{ c.count }}</td>
            <td :class="{ 'vcr-highlight': c.distinct_actors >= 3 }">{{ c.distinct_actors }}</td>
            <td>{{ c.distinct_patients }}</td>
            <td>{{ c.systematic_score }}</td>
            <td>{{ c.direction_consistency }}</td>
            <td>
              <a-button size="small" type="primary" @click="accept(c)">采纳</a-button>
              <a-button size="small" @click="reject(c)">驳回</a-button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="vcr-empty">暂无待审候选。</p>
    </section>

    <!-- 操作反馈 -->
    <div v-if="feedback" :class="['vcr-feedback', feedback.ok ? 'vcr-feedback-ok' : 'vcr-feedback-err']">
      {{ feedback.message }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { Button as AButton } from 'ant-design-vue'
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  timeout: 30000,
})

interface Candidate {
  _id: string
  before_variants: string[]
  after: string
  suggested_category: string
  count: number
  distinct_actors: number
  distinct_patients: number
  systematic_score: number
  direction_consistency: number
  is_drug_confusable: boolean
  sample_log_ids: string[]
  status: string
  _targetCategory?: string
}

const candidates = ref<Candidate[]>([])
const loading = ref(false)
const reloading = ref(false)
const error = ref('')
const feedback = ref<{ ok: boolean; message: string } | null>(null)

const drugCandidates = computed(() => candidates.value.filter(c => c.is_drug_confusable))
const nonDrugCandidates = computed(() => candidates.value.filter(c => !c.is_drug_confusable))

async function loadCandidates() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/admin/voice-correction-candidates', { params: { status: 'pending' } })
    candidates.value = (data.candidates || []).map((c: Candidate) => ({
      ...c,
      _targetCategory: c.suggested_category === 'drug_review' ? 'accent_errors' : c.suggested_category,
    }))
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function accept(c: Candidate) {
  feedback.value = null
  try {
    const { data } = await api.post(`/api/admin/voice-correction-candidates/${c._id}/decision`, {
      action: 'accept',
      target_category: c._targetCategory || c.suggested_category,
    })
    feedback.value = { ok: true, message: data.message || '采纳成功' }
    await loadCandidates()
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message
    feedback.value = { ok: false, message: `采纳失败: ${detail}` }
  }
}

async function reject(c: Candidate) {
  feedback.value = null
  try {
    const { data } = await api.post(`/api/admin/voice-correction-candidates/${c._id}/decision`, {
      action: 'reject',
    })
    feedback.value = { ok: true, message: data.message || '已驳回' }
    await loadCandidates()
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message
    feedback.value = { ok: false, message: `驳回失败: ${detail}` }
  }
}

async function reloadHints() {
  reloading.value = true
  feedback.value = null
  try {
    const { data } = await api.post('/api/admin/voice-correction-candidates/reload-hints')
    feedback.value = { ok: true, message: data.message || '重载成功' }
  } catch (err: any) {
    const detail = err.response?.data?.detail || err.message
    feedback.value = { ok: false, message: `重载失败: ${detail}` }
  } finally {
    reloading.value = false
  }
}

onMounted(loadCandidates)
</script>

<style scoped>
.vcr-page {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}
.vcr-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}
.vcr-header h1 {
  margin: 0 0 4px;
  font-size: 22px;
}
.vcr-header p {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 14px;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.vcr-error {
  background: var(--color-danger-bg);
  border-left: 3px solid var(--color-danger);
  padding: 12px;
  margin-bottom: 16px;
  border-radius: 4px;
}
.vcr-drug-warning {
  background: var(--color-warning-soft-bg);
  border: 2px solid var(--color-warning);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
}
.vcr-drug-warning h2 {
  margin: 0 0 8px;
  color: var(--color-warning);
  font-size: 16px;
}
.vcr-drug-warning p {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--color-warning);
}
.vcr-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.vcr-table th {
  text-align: left;
  padding: 8px 6px;
  border-bottom: 2px solid var(--color-border);
  font-weight: 600;
  white-space: nowrap;
}
.vcr-table td {
  padding: 6px;
  border-bottom: 1px solid var(--color-bg-inset);
}
.vcr-row-drug {
  background: var(--color-warning-soft-bg);
}
.vcr-table code {
  background: var(--color-bg-surface-secondary);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}
.vcr-highlight {
  font-weight: 700;
  color: var(--color-primary);
}
.vcr-category-select {
  padding: 2px 4px;
  font-size: 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
}
.vcr-empty {
  color: var(--color-text-tertiary);
  text-align: center;
  padding: 40px;
}
.vcr-feedback {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 12px 20px;
  border-radius: 6px;
  font-size: 14px;
  z-index: 1000;
  box-shadow: var(--shadow-md);
}
.vcr-feedback-ok {
  background: var(--color-success-bg);
  color: var(--color-success);
  border: 1px solid var(--color-normal-border);
}
.vcr-feedback-err {
  background: var(--color-critical-bg);
  color: var(--color-danger);
  border: 1px solid var(--color-critical-border);
}
</style>
