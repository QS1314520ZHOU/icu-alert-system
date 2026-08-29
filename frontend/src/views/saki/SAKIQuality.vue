<template>
  <div class="saki-quality">
    <a-button type="primary" @click="runCheck" :loading="loading" style="margin-bottom:16px">运行数据质量检查</a-button>
    <div v-if="qualityData" class="quality-grid">
      <div class="metric-card">
        <div class="metric-value">{{ qualityData.total_cases }}</div>
        <div class="metric-label">总病例数</div>
      </div>
      <div class="metric-card">
        <div class="metric-value" :style="{ color: qualityData.completeness_pct >= 80 ? '#52c41a' : '#faad14' }">
          {{ qualityData.completeness_pct }}%
        </div>
        <div class="metric-label">数据完整度</div>
      </div>
    </div>
    <div class="fields-table" v-if="qualityData?.fields">
      <h3>字段完整性</h3>
      <table class="stat-table">
        <thead><tr><th>字段</th><th>数量</th><th>完整率</th></tr></thead>
        <tbody>
          <tr v-for="(info, field) in qualityData.fields" :key="field">
            <td>{{ field }}</td>
            <td>{{ info.count }}</td>
            <td>{{ info.pct }}%</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { getSakiQualityCheck } from '../../api/saki'

const loading = ref(false)
const qualityData = ref<any>(null)

const runCheck = async () => {
  loading.value = true
  try { const r = await getSakiQualityCheck(); qualityData.value = r.data } catch {} finally { loading.value = false }
}
</script>

<style scoped>
.saki-quality { display: flex; flex-direction: column; gap: 16px; }
.quality-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.metric-card { background: #fff; border-radius: 8px; padding: 20px; text-align: center; }
.metric-value { font-size: 28px; font-weight: 700; }
.metric-label { font-size: 13px; color: #8c8c8c; margin-top: 4px; }
.fields-table { background: #fff; border-radius: 8px; padding: 16px; }
.fields-table h3 { margin: 0 0 12px; }
.stat-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.stat-table th, .stat-table td { border: 1px solid #f0f0f0; padding: 6px 10px; text-align: left; }
.stat-table th { background: #fafafa; }
</style>
