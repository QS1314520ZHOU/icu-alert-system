<template>
  <div class="saki-analysis">
    <a-tabs v-model:activeKey="activeTab">
      <a-tab-pane key="table1" tab="基线特征表 (Table 1)">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('table1')" :loading="loading">生成基线特征表</a-button>
          <span class="analysis-hint">默认纳入年龄、性别、SOFA、APACHE II、乳酸、肌酐、机械通气、血管活性药、CRRT、ICU 住院天数与死亡</span>
        </div>
        <div v-if="table1Data?.error" class="result-panel error">{{ table1Data.error }}</div>
        <div v-else-if="table1Data" class="result-panel">
          <div class="result-title">{{ table1Data.title || '基线特征表' }}<span v-if="table1Data.n_total != null">（n={{ table1Data.n_total }}）</span></div>
          <table v-if="(table1Data.rows || []).length" class="stat-table">
            <thead><tr><th>变量</th><th v-for="g in table1Data.groups || []" :key="g">{{ g }}</th><th>P 值</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in table1Data.rows" :key="i">
                <td>{{ row.variable }}</td>
                <td v-for="(v, j) in row.values || []" :key="j">{{ v }}</td>
                <td :class="{ 'p-sig': row.significant }">{{ row.p_display ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
          <a-empty v-else description="无可用数据" />
          <p v-if="table1Data.footnote" class="result-foot">{{ table1Data.footnote }}</p>
        </div>
        <a-empty v-else description="点击“生成基线特征表”，按当前 S-AKI 病例库计算" />
      </a-tab-pane>

      <a-tab-pane key="km" tab="生存分析 (KM)">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('km')" :loading="loading">运行 KM 分析</a-button>
        </div>
        <div v-if="kmData && !kmData.error" class="result-panel">
          <p>Log-rank p = {{ kmData.log_rank_p ?? '-' }}</p>
        </div>
        <div v-if="kmData?.error" class="result-panel error">{{ kmData.error }}</div>
      </a-tab-pane>

      <a-tab-pane key="logistic" tab="Logistic 回归">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('logistic')" :loading="loading">运行 Logistic</a-button>
        </div>
        <div v-if="logisticData && !logisticData.error" class="result-panel">
          <p>模型已拟合，系数数量: {{ logisticData.coefficients?.length ?? 0 }}</p>
        </div>
        <div v-if="logisticData?.error" class="result-panel error">{{ logisticData.error }}</div>
      </a-tab-pane>

      <a-tab-pane key="cox" tab="Cox 回归">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('cox')" :loading="loading">运行 Cox</a-button>
        </div>
        <div v-if="coxData && !coxData.error" class="result-panel">
          <p>模型已拟合</p>
        </div>
        <div v-if="coxData?.error" class="result-panel error">{{ coxData.error }}</div>
      </a-tab-pane>

      <a-tab-pane key="roc" tab="ROC 分析">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('roc')" :loading="loading">运行 ROC</a-button>
        </div>
        <div v-if="rocData && !rocData.error" class="result-panel">
          <p>ROC 分析完成</p>
        </div>
        <div v-if="rocData?.error" class="result-panel error">{{ rocData.error }}</div>
      </a-tab-pane>

      <a-tab-pane key="outcomes" tab="住院结局">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('outcomes')" :loading="loading">查看结局</a-button>
        </div>
        <div v-if="outcomesData && !outcomesData.error" class="result-panel">
          <p>总病例: {{ outcomesData.total }}</p>
          <p>S-AKI 阳性: {{ outcomesData.saki_positive }}</p>
        </div>
      </a-tab-pane>
    </a-tabs>
    <div class="disclaimer">统计分析结果基于观察性数据，仅提示关联性，不可作为因果推断依据。</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { runTable1, runKM, runLogistic, runCox, runROC, runOutcomes } from '../../api/saki'

const activeTab = ref('table1')
const loading = ref(false)
const table1Data = ref<any>(null)
const kmData = ref<any>(null)
const logisticData = ref<any>(null)
const coxData = ref<any>(null)
const rocData = ref<any>(null)
const outcomesData = ref<any>(null)

const runners: Record<string, () => Promise<any>> = {
  table1: () => runTable1({}).then(r => r.data),
  km: () => runKM({}).then(r => r.data),
  logistic: () => runLogistic({}).then(r => r.data),
  cox: () => runCox({}).then(r => r.data),
  roc: () => runROC({}).then(r => r.data),
  outcomes: () => runOutcomes({}).then(r => r.data),
}

const runAnalysis = async (type: string) => {
  loading.value = true
  try {
    const data = await runners[type]?.()
    if (type === 'table1') table1Data.value = data
    else if (type === 'km') kmData.value = data
    else if (type === 'logistic') logisticData.value = data
    else if (type === 'cox') coxData.value = data
    else if (type === 'roc') rocData.value = data
    else if (type === 'outcomes') outcomesData.value = data
  } catch (e) {
    message.error('分析失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.saki-analysis { display: flex; flex-direction: column; gap: 16px; }
.analysis-form { margin-bottom: 12px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.analysis-hint { font-size: var(--text-caption); color: var(--color-text-tertiary); }
.result-title { font-weight: 600; margin-bottom: 8px; }
.result-foot { margin: 8px 0 0; font-size: var(--text-caption); color: var(--color-text-tertiary); }
.p-sig { color: var(--color-danger); font-weight: 600; }
.result-panel { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 16px 18px; font-variant-numeric: tabular-nums; }
.result-panel.error { color: var(--color-danger); }
.stat-table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
.stat-table th, .stat-table td { border-bottom: 1px solid var(--color-divider); padding: 8px 10px; text-align: left; }
.stat-table th { background: var(--color-bg-surface-secondary); font-size: var(--text-caption); font-weight: var(--text-table-header-weight); color: var(--color-text-secondary); }
.disclaimer { text-align: center; font-size: var(--text-caption); color: var(--color-warning); padding: 8px; background: var(--color-warning-soft-bg); border: 1px solid var(--color-warning-soft-border); border-radius: var(--radius-md); }
</style>
