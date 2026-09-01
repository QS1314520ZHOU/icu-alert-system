<template>
  <div class="case-timeline">
    <div v-if="loading" class="timeline-loading">
      <a-spin tip="加载时间线..." />
    </div>

    <template v-else>
      <div v-if="timeline.length === 0" class="timeline-empty">
        <a-empty description="暂无时间线数据" />
      </div>

      <a-timeline v-else>
        <a-timeline-item
          v-for="item in timeline"
          :key="item.id"
          :color="getTimelineColor(item)"
        >
          <template #dot>
            <span class="timeline-dot">{{ getTimelineIcon(item) }}</span>
          </template>

          <div class="timeline-content">
            <div class="timeline-header">
              <a-tag :color="getTagColor(item)" size="small">
                {{ getTimelineTypeLabel(item) }}
              </a-tag>
              <span class="timeline-time">{{ formatTime(item.timestamp) }}</span>
            </div>

            <div class="timeline-body">
              <!-- 证据类型 -->
              <template v-if="item.type === 'evidence'">
                <span class="timeline-label">
                  {{ item.data?.source_field || getEvidenceTypeLabel(item.data?.evidence_type) }}
                </span>
                <span class="timeline-value">
                  {{ item.data?.raw_value ?? '-' }}
                  {{ item.data?.raw_unit || '' }}
                </span>
                <span v-if="item.data?.matched" class="timeline-matched">
                  <a-tag color="var(--color-success-light)" size="small">匹配规则</a-tag>
                </span>
              </template>

              <!-- 确认类型 -->
              <template v-if="item.type === 'confirmation'">
                <span class="timeline-label">
                  {{ getActionLabel(item.data?.action) }}
                </span>
                <span v-if="item.data?.reason" class="timeline-reason">
                  {{ item.data.reason }}
                </span>
                <span class="timeline-operator">
                  操作人: {{ item.data?.operator_id || '-' }}
                </span>
              </template>
            </div>
          </div>
        </a-timeline-item>
      </a-timeline>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { getCaseTimeline } from '@/api/diseaseCenter'
import type { TimelineItem } from '@/api/diseaseCenter'

const props = defineProps<{
  caseId: string
}>()

const loading = ref(false)
const timeline = ref<TimelineItem[]>([])

function getTimelineColor(item: TimelineItem) {
  if (item.type === 'confirmation') return 'var(--color-primary)'
  if (item.data?.matched) return 'var(--color-success)'
  return 'var(--color-border)'
}

function getTimelineIcon(item: TimelineItem) {
  if (item.type === 'confirmation') return '✓'
  if (item.data?.matched) return '●'
  return '○'
}

function getTimelineTypeLabel(item: TimelineItem) {
  if (item.type === 'confirmation') return '医生操作'
  return '临床数据'
}

function getTagColor(item: TimelineItem) {
  if (item.type === 'confirmation') return 'var(--color-primary-light)'
  return 'default'
}

function getEvidenceTypeLabel(type?: string) {
  const map: Record<string, string> = {
    vital_sign: '生命体征',
    lab_result: '检验结果',
    drug: '药物',
    assessment: '评估量表',
    imaging: '影像',
    clinical_note: '临床文书',
    diagnosis: '诊断',
    procedure: '操作',
    device: '设备数据',
    nursing: '护理记录',
  }
  return map[type || ''] || type || '数据'
}

function getActionLabel(action?: string) {
  const map: Record<string, string> = {
    confirm: '确认诊断',
    exclude: '排除诊断',
    modify: '修改信息',
    recalculate: '重新计算',
    task_complete: '完成任务',
    status_change: '状态变更',
  }
  return map[action || ''] || action || '操作'
}

function formatTime(t?: string | null) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

async function loadTimeline() {
  loading.value = true
  try {
    timeline.value = (await getCaseTimeline(props.caseId)).data
  } catch {
    timeline.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.caseId, () => {
  if (props.caseId) loadTimeline()
}, { immediate: true })

onMounted(() => {
  if (props.caseId) loadTimeline()
})
</script>

<style scoped>
.case-timeline {
  padding: 8px 0;
}

.timeline-loading {
  display: flex;
  justify-content: center;
  padding: 40px 0;
}

.timeline-dot {
  font-size: 12px;
}

.timeline-content {
  padding-left: 8px;
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.timeline-time {
  font-size: 12px;
  color: var(--color-text-tertiary, #98A2B3);
}

.timeline-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.timeline-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

.timeline-value {
  font-size: 13px;
  color: var(--color-text-secondary, #667085);
}

.timeline-matched {
  margin-top: 2px;
}

.timeline-reason {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.timeline-operator {
  font-size: 12px;
  color: var(--color-text-tertiary, #98A2B3);
}
</style>
