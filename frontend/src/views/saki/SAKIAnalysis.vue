<template>
  <div class="saki-analysis">
    <a-tabs v-model:activeKey="activeTab">
      <a-tab-pane key="table1" tab="Table 1">
        <div class="analysis-form">
          <a-button type="primary" @click="runAnalysis('table1')" :loading="loading">运行 Table 1</a-button>
        </div>
        <div v-if="table1Data" class="result-panel">
          <table class="stat-table">
            <thead><tr><th>指标</th><th v-for="(v, k) in table1Data.table?.columns || {}" :key="k">{{ v }}</th></tr></thead>
            <tbody>
              <tr v-for="(row, i) in (table1Data.table?.rows || []).slice(0, 20)" :key="i">
                <td>{{ row.patient_id }}</td>
                <td>{{ row.aki_stage }}</td>
                <td>{{ row.sofa_score }}</td>
                <td>{{ row.sofa_delta }}</td>
              </tr>
            </tbody>
          </table>
        </div>
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
    <div class="disclaimer">⚠️ 统计分析结果基于观察性数据，仅提示关联性，不可作为因果推断依据。</div>
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
.analysis-form { margin-bottom: 12px; }
.result-panel { background: #fff; border-radius: 8px; padding: 16px; }
.result-panel.error { color: #ff4d4f; }
.stat-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.stat-table th, .stat-table td { border: 1px solid #f0f0f0; padding: 6px 10px; text-align: left; }
.stat-table th { background: #fafafa; }
.disclaimer { text-align: center; font-size: 12px; color: #faad14; padding: 8px; background: #fffbe6; border-radius: 6px; }
</style>
