<template>
  <a-drawer
    :open="open"
    :title="drawerTitle"
    width="780px"
    @close="$emit('close')"
    class="evidence-drawer"
    :body-style="{ padding: '16px 20px' }"
  >
    <a-spin :spinning="loading">
      <div v-if="error" class="evidence-error">
        <a-alert type="error" :message="error" show-icon />
      </div>

      <div v-if="evidence" class="evidence-body">
        <!-- 1. 结论摘要 -->
        <section class="ev-section ev-conclusion">
          <div class="ev-conclusion-head">
            <span :class="['ev-severity', `sev-${evidence.severity}`]">{{ severityLabel }}</span>
            <span class="ev-confidence">
              置信度
              <a-progress
                :percent="confidencePercent"
                :stroke-color="severityColor"
                :show-text="false"
                size="small"
                style="width: 80px; display: inline-block; margin: 0 6px;"
              />
              <strong>{{ confidencePercent }}%</strong>
            </span>
          </div>
          <p class="ev-conclusion-text">{{ evidence.conclusion }}</p>
        </section>

        <!-- 2. 关键指标 -->
        <section class="ev-section">
          <div class="ev-section-title" @click="toggleSection('metrics')">
            <span>关键指标</span>
            <span class="ev-toggle">{{ expanded.metrics ? '▾' : '▸' }}</span>
          </div>
          <EvidenceMetricCards v-if="expanded.metrics" :metrics="evidence.metrics" />
        </section>

        <!-- 3. 趋势图 -->
        <section class="ev-section">
          <div class="ev-section-title" @click="toggleSection('trends')">
            <span>趋势图</span>
            <span class="ev-toggle">{{ expanded.trends ? '▾' : '▸' }}</span>
          </div>
          <EvidenceTrendChart v-if="expanded.trends" :trends="evidence.trends" />
        </section>

        <!-- 4. 原始证据表格 -->
        <section class="ev-section">
          <div class="ev-section-title" @click="toggleSection('rows')">
            <span>原始证据 ({{ evidence.evidence_rows.length }})</span>
            <span class="ev-toggle">{{ expanded.rows ? '▾' : '▸' }}</span>
          </div>
          <EvidenceTable v-if="expanded.rows" :rows="evidence.evidence_rows" show-source />
        </section>

        <!-- 5. 规则/评分计算明细 -->
        <section class="ev-section">
          <div class="ev-section-title" @click="toggleSection('rule')">
            <span>评分计算明细</span>
            <span class="ev-toggle">{{ expanded.rule ? '▾' : '▸' }}</span>
          </div>
          <RuleCalculationPanel v-if="expanded.rule" :rule-calc="evidence.rule_calculation" />
        </section>

        <!-- 6. AI 分析 -->
        <section class="ev-section">
          <div class="ev-section-title" @click="toggleSection('ai')">
            <span>AI 分析</span>
            <span v-if="evidence.ai_analysis" class="ev-badge-ai">AI</span>
            <span class="ev-toggle">{{ expanded.ai ? '▾' : '▸' }}</span>
          </div>
          <AiEvidenceAnalysis v-if="expanded.ai" :ai-analysis="evidence.ai_analysis" />
        </section>

        <!-- 7. 临床闭环时间线 -->
        <section class="ev-section">
          <div class="ev-section-title" @click="toggleSection('timeline')">
            <span>临床事件时间线 ({{ evidence.timeline.length }})</span>
            <span class="ev-toggle">{{ expanded.timeline ? '▾' : '▸' }}</span>
          </div>
          <EvidenceTimeline v-if="expanded.timeline" :events="evidence.timeline" />
        </section>

        <!-- 8. 数据来源与版本 -->
        <section class="ev-section ev-provenance">
          <div class="ev-section-title" @click="toggleSection('provenance')">
            <span>数据来源与版本</span>
            <span class="ev-toggle">{{ expanded.provenance ? '▾' : '▸' }}</span>
          </div>
          <div v-if="expanded.provenance" class="prov-body">
            <div class="prov-row">
              <span class="prov-label">数据来源</span>
              <span class="prov-value">{{ (evidence.provenance?.data_sources || []).join(', ') || '—' }}</span>
            </div>
            <div class="prov-row">
              <span class="prov-label">数据截止</span>
              <span class="prov-value">{{ formatTime(evidence.data_cutoff_at) }}</span>
            </div>
            <div class="prov-row">
              <span class="prov-label">生成时间</span>
              <span class="prov-value">{{ formatTime(evidence.generated_at) }}</span>
            </div>
            <div class="prov-row">
              <span class="prov-label">规则版本</span>
              <span class="prov-value">{{ evidence.rule_version }}</span>
            </div>
            <div class="prov-row">
              <span class="prov-label">模型版本</span>
              <span class="prov-value">{{ evidence.model_version }}</span>
            </div>
          </div>
        </section>

        <!-- 9. 数据缺失与质量提示 -->
        <section v-if="evidence.missing_data.length" class="ev-section ev-missing">
          <div class="ev-section-title missing-title" @click="toggleSection('missing')">
            <span>⚠ 数据缺失 ({{ evidence.missing_data.length }})</span>
            <span class="ev-toggle">{{ expanded.missing ? '▾' : '▸' }}</span>
          </div>
          <div v-if="expanded.missing" class="missing-body">
            <div v-for="item in evidence.missing_data" :key="item.code" class="missing-item">
              <strong>{{ item.name }}</strong>
              <span>{{ item.reason }}</span>
              <em>{{ item.impact }}</em>
            </div>
          </div>
        </section>
      </div>

      <div v-if="!loading && !error && !evidence" class="evidence-empty">
        请选择上下文加载证据
      </div>
    </a-spin>
  </a-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Drawer as ADrawer, Spin as ASpin, Alert as AAlert, Progress as AProgress } from 'ant-design-vue'
import { useClinicalEvidence } from '../../composables/useClinicalEvidence'
import type { ContextType, OrganSystem, TimeRange } from '../../api/clinicalEvidence'
import EvidenceMetricCards from './EvidenceMetricCards.vue'
import EvidenceTrendChart from './EvidenceTrendChart.vue'
import EvidenceTable from './EvidenceTable.vue'
import RuleCalculationPanel from './RuleCalculationPanel.vue'
import AiEvidenceAnalysis from './AiEvidenceAnalysis.vue'
import EvidenceTimeline from './EvidenceTimeline.vue'

const props = defineProps<{
  open: boolean
  patientId: string
  contextType: ContextType
  contextId?: string
  organSystem?: OrganSystem
  title?: string
  timeRange?: TimeRange
  includeAi?: boolean
}>()

defineEmits<{ close: [] }>()

const {
  loading, error, evidence,
  severityLabel, severityColor, confidencePercent,
  loadEvidence,
} = useClinicalEvidence()

const expanded = ref({
  metrics: true,
  trends: true,
  rows: false,
  rule: true,
  ai: true,
  timeline: true,
  provenance: false,
  missing: true,
})

const drawerTitle = computed(() => {
  if (props.title) return props.title
  if (!evidence.value) return '临床证据'
  return `证据链 — ${evidence.value.conclusion.slice(0, 40)}`
})

function toggleSection(key: keyof typeof expanded.value) {
  expanded.value[key] = !expanded.value[key]
}

function formatTime(t: string | null | undefined): string {
  if (!t) return '—'
  const d = new Date(t)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

watch(
  () => [props.open, props.patientId, props.contextType, props.contextId, props.organSystem],
  () => {
    if (props.open && props.patientId) {
      void loadEvidence(props.patientId, {
        context_type: props.contextType,
        context_id: props.contextId,
        organ_system: props.organSystem,
        time_range: props.timeRange || '24h',
        include_ai: props.includeAi ?? true,
      })
    }
  },
  { immediate: true },
)
</script>

<style scoped>
.evidence-body {
  display: grid;
  gap: 12px;
}

/* 结论摘要 */
.ev-conclusion {
  padding: 12px 14px;
  border-radius: 8px;
  background: var(--bg-surface, #fff);
  border: 1px solid var(--color-border, #E5E7EB);
}
.ev-conclusion-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.ev-severity {
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
}
.ev-severity.sev-critical { background: #DC2626; color: #fff; }
.ev-severity.sev-high { background: #EA580C; color: #fff; }
.ev-severity.sev-warning { background: #D97706; color: #fff; }
.ev-severity.sev-info { background: #2563EB; color: #fff; }
.ev-severity.sev-stable { background: #16A34A; color: #fff; }
.ev-confidence {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary, #6B7280);
}
.ev-confidence strong { color: var(--text-primary, #182230); }
.ev-conclusion-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-primary, #182230);
  margin: 0;
}

/* 通用 section */
.ev-section {
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--bg-surface, #fff);
  border: 1px solid var(--color-border, #E5E7EB);
}
.ev-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary, #182230);
  cursor: pointer;
  user-select: none;
  padding: 2px 0;
}
.ev-section-title:hover { color: var(--color-primary, #2563EB); }
.ev-toggle { font-size: 10px; color: var(--text-tertiary, #9CA3AF); margin-left: auto; }
.ev-badge-ai {
  padding: 1px 5px;
  border-radius: 4px;
  background: #7C3AED;
  color: #fff;
  font-size: 9px;
  font-weight: 700;
}

/* 来源 */
.prov-body { display: grid; gap: 4px; margin-top: 8px; }
.prov-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
}
.prov-label { color: var(--text-tertiary, #9CA3AF); min-width: 70px; }
.prov-value { color: var(--text-primary, #182230); }

/* 缺失 */
.missing-title { color: #D97706 !important; }
.missing-body { display: grid; gap: 6px; margin-top: 8px; }
.missing-item {
  display: flex;
  gap: 8px;
  align-items: baseline;
  padding: 6px 10px;
  border-radius: 4px;
  background: #FFFBEB;
  font-size: 12px;
}
.missing-item strong { color: #92400E; }
.missing-item span { color: var(--text-secondary, #6B7280); }
.missing-item em { color: var(--text-tertiary, #9CA3AF); font-style: normal; margin-left: auto; }

/* 错误和空状态 */
.evidence-error { margin-bottom: 12px; }
.evidence-empty {
  text-align: center;
  padding: 40px 20px;
  color: var(--text-tertiary, #9CA3AF);
  font-size: 14px;
}
</style>
