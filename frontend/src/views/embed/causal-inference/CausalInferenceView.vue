<template>
  <div class="causal-inference">
    <!-- 步骤向导 -->
    <div class="ci-steps">
      <div v-for="(step, idx) in steps" :key="idx" class="ci-step" :class="{ 'ci-step--active': currentStep === idx, 'ci-step--done': currentStep > idx }">
        <span class="ci-step-num">{{ idx + 1 }}</span>
        <span class="ci-step-label">{{ step.label }}</span>
      </div>
    </div>

    <!-- Step 1: 定义问题 -->
    <section v-if="currentStep === 0" class="ci-section">
      <h3 class="ci-section-title">定义研究问题</h3>
      <div class="ci-form-grid">
        <div class="ci-form-item">
          <label>治疗/暴露</label>
          <select v-model="question.exposure" class="ci-select">
            <option value="">请选择</option>
            <option v-for="opt in exposureOptions" :key="opt" :value="opt">{{ opt }}</option>
          </select>
        </div>
        <div class="ci-form-item">
          <label>对照</label>
          <select v-model="question.control" class="ci-select">
            <option value="">请选择</option>
            <option value="standard">标准治疗</option>
            <option value="none">无干预</option>
          </select>
        </div>
        <div class="ci-form-item">
          <label>结局</label>
          <select v-model="question.outcome" class="ci-select">
            <option value="">请选择</option>
            <option value="mortality">死亡率</option>
            <option value="aki_progression">AKI进展</option>
            <option value="ventilator_days">机械通气天数</option>
            <option value="icu_los">ICU住院天数</option>
          </select>
        </div>
        <div class="ci-form-item">
          <label>观察窗</label>
          <select v-model="question.window" class="ci-select">
            <option value="24h">24小时</option>
            <option value="48h">48小时</option>
            <option value="72h">72小时</option>
          </select>
        </div>
      </div>
      <button class="ci-btn ci-btn--primary" @click="nextStep" :disabled="!canProceed">下一步</button>
    </section>

    <!-- Step 2: 因果DAG -->
    <section v-if="currentStep === 1" class="ci-section">
      <h3 class="ci-section-title">因果DAG</h3>
      <div class="ci-dag-area">
        <div ref="dagRef" class="ci-dag-chart"></div>
      </div>
      <div class="ci-dag-legend">
        <span class="ci-legend-item"><span class="ci-dot ci-dot--exposure"></span>暴露</span>
        <span class="ci-legend-item"><span class="ci-dot ci-dot--outcome"></span>结局</span>
        <span class="ci-legend-item"><span class="ci-dot ci-dot--confounder"></span>混杂因素</span>
        <span class="ci-legend-item"><span class="ci-dot ci-dot--mediator"></span>中介因素</span>
      </div>
      <button class="ci-btn ci-btn--primary" @click="nextStep">下一步</button>
    </section>

    <!-- Step 3: 匹配与平衡 -->
    <section v-if="currentStep === 2" class="ci-section">
      <h3 class="ci-section-title">匹配与平衡</h3>
      <div class="ci-chart-grid">
        <div class="ci-chart-card">
          <h4>倾向评分分布</h4>
          <div ref="psDistRef" class="ci-chart-area"></div>
        </div>
        <div class="ci-chart-card">
          <h4>Love Plot</h4>
          <div ref="lovePlotRef" class="ci-chart-area"></div>
        </div>
      </div>
      <div class="ci-flow-diagram">
        <div class="ci-flow-node ci-flow-node--included">总样本 {{ matchResult.total || 0 }}</div>
        <div class="ci-flow-arrow">→</div>
        <div class="ci-flow-node">匹配成功 {{ matchResult.matched || 0 }}</div>
        <div class="ci-flow-arrow">→</div>
        <div class="ci-flow-node ci-flow-node--excluded">排除 {{ matchResult.excluded || 0 }}</div>
      </div>
      <button class="ci-btn ci-btn--primary" @click="nextStep">查看结果</button>
    </section>

    <!-- Step 4: 因果效应 -->
    <section v-if="currentStep === 3" class="ci-section">
      <h3 class="ci-section-title">因果效应估计</h3>
      <div class="ci-effect-cards">
        <div class="ci-effect-card">
          <span class="ci-effect-label">ATE (平均处理效应)</span>
          <span class="ci-effect-value">{{ effectResult.ate || '—' }}</span>
          <span class="ci-effect-ci">{{ effectResult.ate_ci || '' }}</span>
        </div>
        <div class="ci-effect-card">
          <span class="ci-effect-label">ATT (处理组效应)</span>
          <span class="ci-effect-value">{{ effectResult.att || '—' }}</span>
          <span class="ci-effect-ci">{{ effectResult.att_ci || '' }}</span>
        </div>
      </div>
      <div class="ci-chart-grid">
        <div class="ci-chart-card">
          <h4>Forest Plot</h4>
          <div ref="forestRef" class="ci-chart-area"></div>
        </div>
        <div class="ci-chart-card">
          <h4>敏感性分析</h4>
          <div ref="sensitivityRef" class="ci-chart-area"></div>
        </div>
      </div>

      <!-- 重要声明 -->
      <div class="ci-disclaimer">
        <h4>⚠ 重要声明</h4>
        <ul>
          <li>这是基于观察性数据的估计，不能替代随机对照试验</li>
          <li>未测量混杂仍可能存在</li>
          <li>不能直接作为单个患者治疗指令</li>
          <li>结果需结合临床专业知识综合判断</li>
        </ul>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useEmbedBridge } from '../../../composables/useEmbedBridge'
import { postAiCausalAnalysis } from '../../../api'

const route = useRoute()
const patientId = computed(() => String(route.params.patientId || ''))

const { sendUpdateTitle, sendReportError } = useEmbedBridge({
  moduleKey: 'causal-inference',
  targetOrigin: '*',
})

const currentStep = ref(0)
const steps = [
  { label: '定义问题' },
  { label: '因果DAG' },
  { label: '匹配平衡' },
  { label: '效应估计' },
]

const question = ref({
  exposure: '',
  control: 'standard',
  outcome: 'mortality',
  window: '48h',
})

const exposureOptions = [
  '高剂量升压药', '液体正平衡', '俯卧位通气', 'CRRT早期启动',
  '高PEEP', '镇静深度', '早期活动', '肠内营养',
]

const canProceed = computed(() => question.value.exposure && question.value.outcome)

const matchResult = ref({ total: 0, matched: 0, excluded: 0 })
const effectResult = ref({ ate: '', ate_ci: '', att: '', att_ci: '' })

// Chart refs
const dagRef = ref<HTMLElement | null>(null)
const psDistRef = ref<HTMLElement | null>(null)
const lovePlotRef = ref<HTMLElement | null>(null)
const forestRef = ref<HTMLElement | null>(null)
const sensitivityRef = ref<HTMLElement | null>(null)

function nextStep() {
  if (currentStep.value < steps.length - 1) {
    currentStep.value++
    if (currentStep.value === 3) loadResults()
  }
}

async function loadResults() {
  if (!patientId.value) return
  try {
    const res = await postAiCausalAnalysis(patientId.value, {
      abnormal_finding: question.value.exposure,
      outcome: question.value.outcome,
    })
    const data = res.data?.data || res.data || {}
    effectResult.value = {
      ate: data.ate || '—',
      ate_ci: data.ate_ci || '',
      att: data.att || '—',
      att_ci: data.att_ci || '',
    }
    matchResult.value = {
      total: data.total_samples || 0,
      matched: data.matched_samples || 0,
      excluded: data.excluded_samples || 0,
    }
  } catch (e: any) {
    sendReportError('LOAD_FAILED', e?.message || '因果分析失败')
  }
}

onMounted(() => {
  sendUpdateTitle('因果推断')
})
</script>

<style scoped>
.causal-inference {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.ci-steps {
  display: flex;
  gap: 4px;
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  border: 1px solid var(--border, #DCE3EC);
}

.ci-step {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-tertiary, #94A3B8);
  flex: 1;
  justify-content: center;
}

.ci-step--active {
  background: var(--primary-light, #EFF6FF);
  color: var(--primary, #2563EB);
  font-weight: 600;
}

.ci-step--done {
  color: var(--normal, #16A34A);
}

.ci-step-num {
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--border, #DCE3EC);
  font-size: 11px;
  font-weight: 600;
}

.ci-step--active .ci-step-num {
  background: var(--primary, #2563EB);
  color: #fff;
}

.ci-step--done .ci-step-num {
  background: var(--normal, #16A34A);
  color: #fff;
}

.ci-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  border: 1px solid var(--border, #DCE3EC);
}

.ci-section-title {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}

.ci-form-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.ci-form-item label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary, #52606D);
  margin-bottom: 4px;
}

.ci-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border, #DCE3EC);
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
}

.ci-btn {
  padding: 8px 20px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid var(--border, #DCE3EC);
  background: #fff;
  transition: all 0.15s;
}

.ci-btn--primary {
  background: var(--primary, #2563EB);
  color: #fff;
  border-color: var(--primary, #2563EB);
}

.ci-btn--primary:hover {
  background: var(--primary-hover, #3B82F6);
}

.ci-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.ci-dag-area {
  margin-bottom: 12px;
}

.ci-dag-chart {
  height: 300px;
  background: #F8FAFC;
  border-radius: 6px;
}

.ci-dag-legend {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
}

.ci-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary, #52606D);
}

.ci-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}

.ci-dot--exposure { background: var(--primary, #2563EB); }
.ci-dot--outcome { background: var(--critical, #991B1B); }
.ci-dot--confounder { background: var(--warning, #F59E0B); }
.ci-dot--mediator { background: var(--accent, #0891B2); }

.ci-chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

.ci-chart-card {
  background: #F8FAFC;
  border-radius: 6px;
  padding: 12px;
}

.ci-chart-card h4 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
}

.ci-chart-area {
  height: 220px;
}

.ci-flow-diagram {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-bottom: 16px;
}

.ci-flow-node {
  padding: 10px 20px;
  background: #EFF6FF;
  border: 1px solid var(--primary, #2563EB);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
}

.ci-flow-node--included { background: #F0FDF4; border-color: #16A34A; }
.ci-flow-node--excluded { background: #FEF2F2; border-color: #DC2626; }

.ci-flow-arrow {
  font-size: 18px;
  color: var(--text-tertiary, #94A3B8);
}

.ci-effect-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}

.ci-effect-card {
  background: #F8FAFC;
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid var(--border, #DCE3EC);
}

.ci-effect-label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary, #52606D);
  margin-bottom: 8px;
}

.ci-effect-value {
  display: block;
  font-size: 28px;
  font-weight: 700;
  font-family: var(--font-digit, monospace);
  color: var(--primary, #2563EB);
}

.ci-effect-ci {
  display: block;
  font-size: 12px;
  color: var(--text-tertiary, #94A3B8);
  margin-top: 4px;
}

.ci-disclaimer {
  background: #FFFBEB;
  border: 1px solid #FDE68A;
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}

.ci-disclaimer h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #92400E;
}

.ci-disclaimer ul {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #92400E;
  line-height: 1.8;
}

@media (max-width: 1200px) {
  .ci-chart-grid { grid-template-columns: 1fr; }
  .ci-form-grid { grid-template-columns: 1fr; }
}
</style>
