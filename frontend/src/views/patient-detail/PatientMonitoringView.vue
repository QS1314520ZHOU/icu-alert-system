<template>
  <div class="monitoring-view">
    <PageHeader title="监护监测" subtitle="生命体征趋势、检验结果与波形监测" />
    <!-- 生命体征趋势 -->
    <section class="monitoring-section">
      <div class="section-header">
        <h3>生命体征趋势</h3>
        <a-radio-group v-model:value="trendWindow" size="small" @change="loadTrend">
          <a-radio-button value="6h">6h</a-radio-button>
          <a-radio-button value="24h">24h</a-radio-button>
          <a-radio-button value="72h">72h</a-radio-button>
        </a-radio-group>
      </div>
      <div class="trend-chart-placeholder">
        <VitalSmallMultiples :points="trendPoints" :loading="!trendLoaded" :height="130" />
      </div>
    </section>

    <!-- 双栏：波形 + 检验 -->
    <div class="monitoring-grid">
      <!-- 波形数据 -->
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">生命体征波形</h3></template>
        <template #extra>
          <div class="waveform-controls">
            <a-radio-group v-model:value="waveformHours" size="small" button-style="solid" @change="loadWaveform">
              <a-radio-button :value="1">1h</a-radio-button>
              <a-radio-button :value="6">6h</a-radio-button>
              <a-radio-button :value="12">12h</a-radio-button>
            </a-radio-group>
            <a-select v-model:value="waveformSelectedChannel" size="small" style="width: 120px;" @change="loadWaveform">
              <a-select-option v-for="ch in waveformChannels" :key="ch.key" :value="ch.key">{{ ch.label }}</a-select-option>
            </a-select>
          </div>
        </template>
        <div v-if="waveformLoading" class="loading-placeholder">
          <a-spin />
        </div>
        <div v-else-if="waveformError" class="waveform-error">
          <span class="waveform-error__icon">⚠️</span>
          <span class="waveform-error__text">{{ waveformError }}</span>
          <button class="waveform-empty__btn" @click="loadWaveform">重试</button>
        </div>
        <div v-else-if="waveformPoints.length" class="waveform-chart-container">
          <WaveformChart
            :points="waveformPoints"
            :channel="waveformSelectedChannel"
            :hours="waveformHours"
          />
        </div>
        <div v-else class="waveform-empty">
          <span class="waveform-empty__icon">📊</span>
          <span class="waveform-empty__title">暂无波形数据</span>
          <span class="waveform-empty__desc">请确认监护设备已连接且数据同步正常</span>
          <button class="waveform-empty__btn" @click="loadWaveform">重新加载</button>
        </div>
      </CollapseSection>

      <!-- 检验结果 -->
      <CollapseSection>
        <template #title><h3 style="margin:0;font-size:15px;font-weight:600">检验结果</h3></template>
        <template #extra>
          <a-button size="small" @click="loadLabs" :loading="!labsLoaded && labs.length === 0">刷新</a-button>
        </template>
        <div v-if="labs.length" class="labs-grid">
          <div v-for="exam in labs" :key="exam.reportId || exam.itemName" class="lab-card" :class="labFlagClass(exam)">
            <div class="lab-header">
              <span class="lab-name">{{ exam.itemName || exam.name || '—' }}</span>
              <span class="lab-flag">{{ exam.resultFlag || exam.abnormalFlag || '' }}</span>
            </div>
            <div class="lab-result">
              <span class="lab-value">{{ exam.result ?? exam.value ?? '—' }}</span>
              <span class="lab-unit">{{ exam.unit || '' }}</span>
            </div>
            <div class="lab-time">{{ fmtTime(exam.reportTime || exam.time) }}</div>
          </div>
        </div>
        <a-empty v-else-if="labsLoaded" description="暂无检验数据" :image-style="{ height: '40px' }" />
      </CollapseSection>
    </div>
  </div>
</template>

<script setup lang="ts">
import { PageHeader } from '../../components/common/design-system'
import { onMounted } from 'vue'
import { RadioGroup as ARadioGroup, RadioButton as ARadioButton } from 'ant-design-vue'
import CollapseSection from '../../components/common/CollapseSection.vue'
import { usePatientDetail } from '../../composables/usePatientDetail'
import VitalSmallMultiples from '../../components/charts/VitalSmallMultiples.vue'
import WaveformChart from './components/WaveformChart.vue'

const {
  trendWindow, trendPoints, trendLoaded, loadTrend,
  waveformHours, waveformSelectedChannel, waveformChannels,
  waveformPoints, waveformLoading, waveformError,
  labs, labsLoaded, loadLabs, loadWaveform,
  fmtTime,
} = usePatientDetail()

function labFlagClass(exam: any) {
  const flag = exam.resultFlag || exam.abnormalFlag || exam.flag
  if (!flag) return ''
  const f = String(flag)
  if (f.includes('H') || f.includes('↑')) return 'lab-high'
  if (f.includes('L') || f.includes('↓')) return 'lab-low'
  return ''
}

onMounted(() => {
  if (!trendLoaded.value) loadTrend()
})
</script>

<style scoped>
.monitoring-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.monitoring-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.monitoring-grid > .monitoring-section {
  margin: 0;
}

@media (max-width: 900px) {
  .monitoring-grid {
    grid-template-columns: 1fr;
  }
}

.monitoring-section {
  background: var(--color-bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-header h3 {
  margin: 0;
  font-size: var(--text-section-title);
  font-weight: 600;
  color: var(--color-text-primary);
}

.trend-chart-placeholder {
  min-height: 200px;
}

.waveform-controls {
  display: flex;
  gap: 8px;
  align-items: center;
}

.loading-placeholder {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

.waveform-chart-container {
  min-height: 200px;
}

.waveform-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  gap: 8px;
  text-align: center;
}

.waveform-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  gap: 8px;
  text-align: center;
  background: var(--color-high-risk-bg);
  border: 1px solid var(--color-high-risk-border);
  border-radius: var(--radius-md);
}

.waveform-error__icon {
  font-size: 24px;
}

.waveform-error__text {
  font-size: var(--text-body);
  color: var(--color-warning);
}

.waveform-empty__icon {
  font-size: 32px;
  margin-bottom: 4px;
}

.waveform-empty__title {
  font-size: var(--text-body);
  font-weight: 600;
  color: var(--text-primary);
}

.waveform-empty__desc {
  font-size: var(--text-label);
  color: var(--text-tertiary);
}

.waveform-empty__btn {
  margin-top: 8px;
  padding: 4px 16px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-tag);
  background: var(--color-bg-surface);
  font-size: var(--text-label);
  cursor: pointer;
  color: var(--color-primary);
}

.waveform-empty__btn:hover {
  background: var(--color-bg-hover);
}

/* Labs */
.labs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
}

.lab-card {
  padding: 10px 12px;
  border: 1px solid var(--color-divider);
  border-radius: var(--radius-md);
  background: var(--color-bg-surface-secondary);
}

.lab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.lab-name {
  font-size: var(--text-label);
  color: var(--color-text-secondary);
  font-weight: 500;
}

.lab-flag {
  font-size: var(--text-caption);
  font-weight: 700;
}

.lab-result {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.lab-value {
  font-size: var(--text-metric-normal);
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  color: var(--color-text-primary);
}

.lab-unit {
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
}

.lab-time {
  font-size: var(--text-caption);
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.lab-high .lab-value { color: var(--color-danger); }
.lab-high .lab-flag { color: var(--color-danger); }
.lab-low .lab-value { color: var(--color-primary); }
.lab-low .lab-flag { color: var(--color-primary); }
</style>
