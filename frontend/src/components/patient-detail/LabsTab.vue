<template>
  <div class="detail-tab labs-tab">
    <a-timeline>
      <a-timeline-item v-for="exam in labs" :key="exam.requestId">
        <div class="lab-head">
          <strong>{{ exam.examName || exam.requestName || '检验' }}</strong>
          <span>{{ fmtTime(exam.requestTime) }}</span>
        </div>
        <div class="lab-items">
          <span
            v-for="item in exam.items || []"
            :key="item.itemId || item.itemCode || item.itemName"
            :class="['lab-item', labFlag(item)]"
          >
            {{ item.itemName || item.itemCnName || '指标' }}:
            {{ formatLabValue(item.result ?? item.resultValue ?? item.value) }}
            {{ item.unit || '' }}
          </span>
        </div>
        <div v-if="exam.acidBaseInterpretation" class="acid-base-card">
          <div class="acid-base-head">
            <strong>血气自动解读</strong>
            <span>{{ formatLabValue(exam.acidBaseInterpretation.compensation) || '—' }}</span>
          </div>
          <div class="acid-base-summary">
            <span class="acid-pill acid-primary">{{ formatLabValue(exam.acidBaseInterpretation.primary) }}</span>
            <span v-if="exam.acidBaseInterpretation.secondary" class="acid-pill acid-secondary">{{ formatLabValue(exam.acidBaseInterpretation.secondary) }}</span>
            <span v-if="exam.acidBaseInterpretation.tertiary" class="acid-pill acid-tertiary">{{ formatLabValue(exam.acidBaseInterpretation.tertiary) }}</span>
          </div>
          <div class="acid-base-metrics">
            <span>AG {{ formatLabValue(exam.acidBaseInterpretation.AG) || '—' }}</span>
            <span>校正AG {{ formatLabValue(exam.acidBaseInterpretation.corrected_AG) || '—' }}</span>
            <span>Δ比 {{ formatLabValue(exam.acidBaseInterpretation.delta_ratio) || '—' }}</span>
          </div>
          <div v-if="exam.acidBaseInterpretation.abnormal_components?.length" class="acid-base-components">
            <span
              v-for="comp in exam.acidBaseInterpretation.abnormal_components"
              :key="comp.field"
              :class="['acid-comp', { abnormal: comp.abnormal }]"
            >
              {{ formatLabValue(comp.field) }} {{ formatLabValue(comp.value) || '—' }}{{ comp.unit || '' }}
            </span>
          </div>
        </div>
      </a-timeline-item>
    </a-timeline>
    <div v-if="!labs.length" class="tab-empty">暂无检验记录</div>
  </div>
</template>

<script setup lang="ts">
import { Timeline as ATimeline, TimelineItem as ATimelineItem } from 'ant-design-vue'

defineProps<{
  labs: any[]
  fmtTime: (v: any) => string
  labFlag: (item: any) => string
}>()

function formatLabValue(value: any): string {
  if (value == null || value === '') return ''
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  if (Array.isArray(value)) {
    return value.map((item) => formatLabValue(item)).filter(Boolean).join('；')
  }
  if (typeof value === 'object') {
    const candidates = [
      value.result,
      value.resultValue,
      value.value,
      value.text,
      value.summary,
      value.label,
      value.name,
      value.message,
      value.content,
    ]
    for (const candidate of candidates) {
      const text = formatLabValue(candidate)
      if (text) return text
    }
    return Object.entries(value)
      .map(([key, item]) => {
        const text = formatLabValue(item)
        return text ? `${key}: ${text}` : ''
      })
      .filter(Boolean)
      .join('；')
  }
  return String(value).trim()
}
</script>

<style scoped>
.detail-tab {
  display: grid;
  gap: 12px;
}
.labs-tab :deep(.ant-timeline-item-tail) {
  border-inline-start-color: var(--color-accent);
}
.labs-tab :deep(.ant-timeline-item-head) {
  background: var(--accent);
  border-color: var(--color-info-border);
  box-shadow: var(--shadow-sm);
}
.labs-tab :deep(.ant-timeline-item-content) {
  padding-bottom: 14px;
}
.lab-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.lab-head strong {
  font-size: var(--text-body);
  color: var(--text-primary);
}
.lab-head span {
  color: var(--accent);
  font-size: var(--text-caption);
}
.lab-items {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.lab-item {
  font-size: var(--text-label);
  padding: 4px 8px;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}
.lab-item.lab-high {
  color: var(--color-danger);
  background: var(--bg-surface);
  border-color: var(--color-border);
}
.lab-item.lab-low {
  color: var(--color-accent);
  background: var(--bg-surface);
  border-color: var(--color-border);
}
.acid-base-card {
  margin-top: 10px;
  padding: 10px 12px;
  border-radius: var(--card-radius);
  border: 1px solid var(--color-border);
  background: var(--bg-surface);
}
.acid-base-head,
.acid-base-summary,
.acid-base-metrics,
.acid-base-components {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.acid-base-head {
  justify-content: space-between;
  margin-bottom: 6px;
  color: var(--text-primary);
}
.acid-base-summary {
  margin-bottom: 6px;
}
.acid-pill,
.acid-comp {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: var(--card-radius);
  font-size: var(--text-label);
}
.acid-primary { background: var(--color-info-bg); color: var(--color-accent); }
.acid-secondary { background: var(--color-warning-soft-bg); color: var(--warning); }
.acid-tertiary { background: var(--color-critical-bg); color: var(--color-danger); }
.acid-base-metrics { color: var(--color-text-secondary); font-size: var(--text-label); margin-bottom: 6px; }
.acid-comp { background: var(--color-primary-bg); color: var(--text-primary); }
.acid-comp.abnormal { background: var(--color-critical-bg); color: var(--color-danger); }
.tab-empty {
  color: var(--accent);
  font-size: var(--text-caption);
  padding: 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  border: 1px dashed var(--color-border);
}

/* Light mode overrides */
html[data-theme='light'] .labs-tab :deep(.ant-timeline-item-tail) { border-inline-start-color: var(--color-accent); }
html[data-theme='light'] .labs-tab :deep(.ant-timeline-item-head) { background: var(--brand); border-color: var(--color-info-border); box-shadow: var(--shadow-sm); }
html[data-theme='light'] .lab-head { color: var(--text-secondary); }
html[data-theme='light'] .lab-head strong { color: var(--text-secondary); }
html[data-theme='light'] .lab-head span { color: var(--text-secondary); }
html[data-theme='light'] .lab-item { background: var(--bg-surface); color: var(--text-secondary); border-color: var(--color-border); }
html[data-theme='light'] .lab-item.lab-high { background: var(--color-critical-bg); color: var(--color-danger); border-color: var(--color-critical-border); }
html[data-theme='light'] .lab-item.lab-low { background: var(--color-info-bg); color: var(--brand); border-color: var(--color-info-border); }
html[data-theme='light'] .acid-base-card { background: var(--color-bg-surface); border-color: var(--color-border); }
html[data-theme='light'] .acid-base-head { color: var(--text-secondary); }
html[data-theme='light'] .acid-primary { background: var(--color-primary-bg); color: var(--brand); }
html[data-theme='light'] .acid-secondary { background: var(--color-warning-soft-bg); color: var(--warning); }
html[data-theme='light'] .acid-tertiary { background: var(--color-critical-bg); color: var(--danger); }
html[data-theme='light'] .acid-base-metrics { color: var(--text-secondary); }
html[data-theme='light'] .acid-comp { background: var(--bg-surface); color: var(--text-secondary); border: 1px solid var(--color-border); }
html[data-theme='light'] .acid-comp.abnormal { background: var(--color-critical-bg); color: var(--color-danger); border-color: var(--color-critical-border); }
html[data-theme='light'] .tab-empty { color: var(--text-secondary); background: var(--color-bg-surface); border-color: var(--color-border); }
</style>
