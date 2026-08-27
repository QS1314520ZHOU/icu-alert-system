<template>
  <a-drawer
    :open="open"
    :width="drawerWidth"
    :title="patient ? `${patient.bed_no}床 ${patient.name}` : '患者详情'"
    @update:open="$emit('update:open', $event)"
  >
    <template v-if="patient">
      <!-- 关键指标摘要 -->
      <section class="drawer-metrics">
        <article>
          <span>安全评分</span>
          <strong>{{ patient.safety_score ?? '—' }}</strong>
        </article>
        <article>
          <span>参数完整度</span>
          <strong>{{ Math.round((patient.parameter_completeness?.score || 0) * 100) }}%</strong>
        </article>
        <article>
          <span>SBT 状态</span>
          <strong>{{ patient.sbt_candidate_status?.status === 'candidate' ? '可评估' : '暂不适合' }}</strong>
        </article>
      </section>

      <!-- 通气参数表 -->
      <a-descriptions bordered size="small" :column="2">
        <a-descriptions-item label="体位">{{ patient.position ?? '—' }}</a-descriptions-item>
        <a-descriptions-item label="模式">{{ patient.ventilator_mode }}</a-descriptions-item>
        <a-descriptions-item label="FiO₂">{{ fmtVentParam('fio2', patient.fio2) }}</a-descriptions-item>
        <a-descriptions-item label="PEEP">{{ fmtVentParam('peep', patient.peep) }}</a-descriptions-item>
        <a-descriptions-item label="VT(set)">{{ fmtVentParam('vt_set', patient.vt_set) }}</a-descriptions-item>
        <a-descriptions-item label="峰流速">{{ fmtVentParam('peak_flow', patient.peak_flow) }}</a-descriptions-item>
        <a-descriptions-item label="驱动压">{{ fmtVentParam('driving_pressure', patient.driving_pressure) }}</a-descriptions-item>
        <a-descriptions-item label="气道阻力">{{ fmtVentParam('airway_resistance', patient.airway_resistance) }}</a-descriptions-item>
        <a-descriptions-item label="P0.1">{{ fmtVentParam('p01', patient.p01) }}</a-descriptions-item>
        <a-descriptions-item label="Pplat">{{ fmtVentParam('pplat', patient.pplat) }}</a-descriptions-item>
        <a-descriptions-item label="C_STAT">{{ fmtVentParam('c_stat', patient.c_stat) }}</a-descriptions-item>
        <a-descriptions-item label="静态顺应性">{{ fmtVentParam('static_compliance', patient.static_compliance) }}</a-descriptions-item>
        <a-descriptions-item label="P/F">{{ fmtVentParam('pf_ratio', patient.pf_ratio) }}</a-descriptions-item>
        <a-descriptions-item label="EtCO₂">{{ fmtVentParam('etco2', patient.etco2) }}</a-descriptions-item>
        <a-descriptions-item label="间接测热 EE">{{ fmtVentParam('energy_expenditure', patient.energy_expenditure) }}</a-descriptions-item>
        <a-descriptions-item label="RASS">{{ fmtVentParam('rass', patient.rass) }}</a-descriptions-item>
      </a-descriptions>

      <!-- 呼吸恶化预警 -->
      <a-divider>呼吸恶化预警</a-divider>
      <section class="forecast-card">
        <div class="forecast-card__head">
          <div>
            <span>趋势判断</span>
            <strong>{{ forecastView.title }}</strong>
          </div>
          <a-tag :color="forecastView.color">experimental</a-tag>
        </div>
        <div class="forecast-grid">
          <article><span>S/F</span><strong>{{ forecastView.sfRatio }}</strong></article>
          <article><span>6h预测</span><strong>{{ forecastView.projected }}</strong></article>
          <article><span>完整度</span><strong>{{ forecastView.completeness }}</strong></article>
        </div>
        <p>{{ forecastView.note }}</p>
      </section>

      <!-- 参数时间线 -->
      <a-divider>参数时间线</a-divider>
      <a-timeline>
        <a-timeline-item v-for="(item, idx) in timeline" :key="idx">
          {{ fmt(item.time) }} · {{ item.mode || '—' }} / FiO₂{{ fmtVentParam('fio2', item.fio2) }} / PEEP{{ fmtVentParam('peep', item.peep) }} / DP{{ fmtVentParam('driving_pressure', item.driving_pressure) }} / EtCO₂{{ fmtVentParam('etco2', item.etco2) }}
        </a-timeline-item>
      </a-timeline>
      <div v-if="!timeline.length" class="drawer-empty">暂无时间线数据</div>

      <!-- 气道预案 -->
      <a-divider>气道预案</a-divider>
      <div class="airway-tools">
        <a-button size="small" @click="$emit('record-airway')">补录气道记录</a-button>
        <a-button size="small" type="primary" ghost @click="$emit('save-difficult-airway')">标记困难气道预案</a-button>
      </div>
      <section class="airway-plan-card">
        <div class="airway-plan-card__head">
          <div>
            <span>预案状态</span>
            <strong>{{ airwayPlanView.statusText }}</strong>
          </div>
          <a-tag :color="airwayPlanView.tagColor">{{ airwayPlanView.riskText }}</a-tag>
        </div>
        <p>{{ airwayPlanView.note }}</p>
        <div class="airway-plan-grid">
          <article>
            <span>困难气道</span>
            <strong>{{ airwayPlanView.difficultAirway ? '已标记' : '未标记' }}</strong>
          </article>
          <article>
            <span>备选设备</span>
            <strong>{{ airwayPlanView.equipment }}</strong>
          </article>
          <article>
            <span>联络团队</span>
            <strong>{{ airwayPlanView.contacts }}</strong>
          </article>
        </div>
      </section>
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Button as AButton,
  Descriptions as ADescriptions,
  DescriptionsItem as ADescriptionsItem,
  Divider as ADivider,
  Drawer as ADrawer,
  Tag as ATag,
  Timeline as ATimeline,
  TimelineItem as ATimelineItem,
} from 'ant-design-vue'

const drawerWidth = computed(() => {
  if (typeof window !== 'undefined' && window.innerWidth < 768) return '100%'
  if (typeof window !== 'undefined' && window.innerWidth < 1024) return '90%'
  return 720
})

defineProps<{
  open: boolean
  patient: any
  timeline: any[]
  forecastView: any
  airwayPlanView: any
  fmtVentParam: (key: string, value: any) => string
  fmt: (v: any) => string
}>()

defineEmits<{
  'update:open': [value: boolean]
  'record-airway': []
  'save-difficult-airway': []
}>()
</script>

<style scoped>
.drawer-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.drawer-metrics article {
  padding: 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.drawer-metrics span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.drawer-metrics strong {
  display: block;
  margin-top: 4px;
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: var(--text-metric-key, 24px);
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
}

.forecast-card {
  display: grid;
  gap: 10px;
  padding: 14px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.forecast-card__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
.forecast-card__head span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.forecast-card__head strong {
  font-size: var(--text-card-title, 14px);
  color: var(--color-text-primary, #18212B);
}
.forecast-grid {
  display: flex;
  gap: 10px;
}
.forecast-grid article {
  flex: 1;
  padding: 8px 10px;
  border-radius: var(--radius-sm, 4px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
}
.forecast-grid span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.forecast-grid strong {
  display: block;
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
}
.forecast-card p {
  margin: 0;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.airway-tools {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.airway-plan-card {
  display: grid;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.airway-plan-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.airway-plan-card span,
.airway-plan-grid span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.airway-plan-card strong,
.airway-plan-grid strong {
  color: var(--color-text-primary, #18212B);
}
.airway-plan-card p {
  margin: 0;
  font-size: var(--text-body, 14px);
  color: var(--color-text-secondary, #667085);
}
.airway-plan-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.airway-plan-grid article {
  min-width: 0;
  padding: 10px;
  border-radius: var(--radius-sm, 4px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

.drawer-empty {
  padding: 24px;
  text-align: center;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

@media (max-width: 768px) {
  .drawer-metrics { grid-template-columns: 1fr; }
  .forecast-grid { flex-direction: column; }
  .airway-plan-grid { grid-template-columns: 1fr; }
}
</style>
