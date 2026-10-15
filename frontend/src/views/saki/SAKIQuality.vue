<template>
  <div class="saki-quality">
    <a-button type="primary" @click="runCheck" :loading="loading" style="margin-bottom:16px">运行数据质量检查</a-button>
    <div v-if="qualityData" class="quality-grid">
      <div class="metric-card">
        <div class="metric-label">总病例数</div>
        <div class="metric-value">{{ qualityData.total_cases }}</div>
      </div>
      <div class="metric-card">
        <div class="metric-label">数据完整度</div>
        <div class="metric-value" :class="qualityData.completeness_pct >= 80 ? 'is-ok' : 'is-warn'">
          {{ qualityData.completeness_pct }}%
        </div>
      </div>
    </div>
    <div v-else class="empty-wrap">
      <EmptyState description="点击「运行数据质量检查」查看数据质量结果" />
    </div>
    <div class="fields-table" v-if="qualityData?.fields">
      <h3>字段完整性</h3>
      <table class="stat-table">
        <thead><tr><th>字段</th><th>数量</th><th>完整率</th></tr></thead>
        <tbody>
          <tr v-for="(info, field) in qualityData.fields" :key="field">
            <td>{{ field }}</td>
            <td class="num">{{ info.count }}</td>
            <td class="num">{{ info.pct }}%</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Button as AButton } from 'ant-design-vue'
import { ref } from 'vue'
import { getSakiQualityCheck } from '../../api/saki'
import { EmptyState } from '../../components/common/design-system'

const loading = ref(false)
const qualityData = ref<any>(null)

const runCheck = async () => {
  loading.value = true
  try { const r = await getSakiQualityCheck(); qualityData.value = r.data } catch {} finally { loading.value = false }
}
</script>

<style scoped>
.saki-quality { display: flex; flex-direction: column; gap: 16px; }
.quality-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.metric-card { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 14px 16px; text-align: left; }
.metric-label { font-size: var(--text-caption); font-weight: var(--weight-medium); color: var(--color-text-secondary); }
.metric-value { font-size: var(--text-metric-key); font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; color: var(--color-text-primary); }
.metric-value.is-ok { color: var(--color-success); }
.metric-value.is-warn { color: var(--color-warning); }
.empty-wrap { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.fields-table { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 16px 18px; }
.fields-table h3 { margin: 0 0 12px; font-size: var(--text-section-title); font-weight: var(--weight-semibold); color: var(--color-text-primary); }
.stat-table { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
.stat-table th, .stat-table td { border-bottom: 1px solid var(--color-divider); padding: 8px 10px; text-align: left; }
.stat-table th { background: var(--color-bg-surface-secondary); font-size: var(--text-caption); font-weight: var(--text-table-header-weight); color: var(--color-text-secondary); }
.stat-table td.num { text-align: right; font-variant-numeric: tabular-nums; }
</style>
