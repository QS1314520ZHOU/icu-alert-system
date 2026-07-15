<template>
  <div class="isbar-editor">
    <div class="editor-toolbar">
      <h3 class="editor-title">📋 ISBAR 结构化交班</h3>
      <div class="editor-actions">
        <a-tag v-if="aiGeneratedCount" color="blue">AI 生成: {{ aiGeneratedCount }} 字段</a-tag>
        <span class="status-badge" :class="`status-${status}`">{{ statusLabel }}</span>
      </div>
    </div>

    <a-collapse v-model:activeKey="activeKeys" :bordered="false">
      <!-- I: Identify -->
      <a-collapse-panel key="identify" header="I 身份信息">
        <div class="section-grid two-col">
          <div class="field-row" v-for="f in identifyFields" :key="f.key" :class="sourceClass(f.key)">
            <label>{{ f.label }}</label>
            <a-input v-model:value="localSections.identify[f.key]" size="small" @change="onFieldEdit(f.key)" />
          </div>
          <div class="field-row">
            <label>特殊标签</label>
            <a-select
              v-model:value="localSections.identify.special_tags"
              mode="tags"
              size="small"
              placeholder="输入标签..."
              @change="onFieldEdit('identify.special_tags')"
            />
          </div>
        </div>
      </a-collapse-panel>

      <!-- S: Situation -->
      <a-collapse-panel key="situation" header="S 现况">
        <div class="section-grid two-col">
          <div class="field-row" v-for="f in situationFields" :key="f.key" :class="sourceClass(f.key)">
            <label>{{ f.label }}</label>
            <a-textarea
              v-model:value="localSections.situation[f.key]"
              :rows="2"
              size="small"
              @change="onFieldEdit(f.key)"
            />
          </div>
        </div>
      </a-collapse-panel>

      <!-- B: Background -->
      <a-collapse-panel key="background" header="B 背景">
        <div class="section-grid">
          <div class="field-row" v-for="f in backgroundFields" :key="f.key" :class="sourceClass(f.key)">
            <label>{{ f.label }}</label>
            <a-textarea
              v-model:value="localSections.background[f.key]"
              :rows="2"
              size="small"
              @change="onFieldEdit(f.key)"
            />
          </div>
        </div>
      </a-collapse-panel>

      <!-- A: Assessment -->
      <a-collapse-panel key="assessment" header="A 评估（器官系统）">
        <a-collapse v-model:activeKey="assessmentActiveKeys" :bordered="false" size="small">
          <a-collapse-panel v-for="sys in assessmentSystems" :key="sys.key" :header="sys.label">
            <div class="field-row" :class="sourceClass(`assessment.${sys.key}.content`)">
              <label>评估内容</label>
              <a-textarea
                :value="getAssessmentField(sys.key, 'content')"
                :rows="3"
                size="small"
                @update:value="(v: string) => setAssessmentField(sys.key, 'content', v)"
                @change="onFieldEdit(`assessment.${sys.key}.content`)"
              />
            </div>
            <div class="field-row" :class="sourceClass(`assessment.${sys.key}.changes`)">
              <label>本班变化</label>
              <a-input
                :value="getAssessmentField(sys.key, 'changes')"
                size="small"
                @update:value="(v: string) => setAssessmentField(sys.key, 'changes', v)"
                @change="onFieldEdit(`assessment.${sys.key}.changes`)"
              />
            </div>
          </a-collapse-panel>
        </a-collapse>
      </a-collapse-panel>

      <!-- R: Recommendation -->
      <a-collapse-panel key="recommendation" header="R 建议">
        <!-- Critical alerts (always first, highlighted) -->
        <div class="critical-section" v-if="localSections.recommendation.critical_first?.length">
          <h4 class="critical-title">🚨 危急值与未闭环预警（强制交接）</h4>
          <div
            v-for="(alert, ai) in localSections.recommendation.critical_first"
            :key="ai"
            class="critical-item"
          >
            <a-input
              :value="localSections.recommendation.critical_first[ai]?.description || alert"
              size="small"
              @update:value="(v: string) => { if (localSections.recommendation.critical_first[ai]) localSections.recommendation.critical_first[ai].description = v; syncUp(); }"
              @change="onFieldEdit('recommendation.critical_first')"
            />
          </div>
        </div>

        <div class="field-row">
          <label>下一班任务</label>
          <a-textarea
            v-model:value="tasksText"
            :rows="3"
            size="small"
            placeholder="每行一项"
            @change="onTasksChange"
          />
        </div>
        <div class="field-row">
          <label>待回报结果 / 未完成医嘱</label>
          <a-textarea
            v-model:value="pendingText"
            :rows="3"
            size="small"
            placeholder="每行一项"
            @change="onPendingChange"
          />
        </div>
        <div class="field-row" :class="sourceClass('recommendation.escalation')">
          <label>🆘 紧急升级条件</label>
          <a-textarea
            v-model:value="escalationText"
            :rows="2"
            size="small"
            placeholder="每行一项"
            @change="onEscalationChange"
          />
        </div>
      </a-collapse-panel>
    </a-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Collapse as ACollapse,
  CollapsePanel as ACollapsePanel,
  Input as AInput,
  Textarea as ATextarea,
  Select as ASelect,
  Tag as ATag,
} from 'ant-design-vue'

type Sections = Record<string, any>

const props = defineProps<{
  sections: Sections
  aiGeneratedFields: string[]
  contentSources: Record<string, string>
  status: string
}>()

const emit = defineEmits<{
  'update:sections': [sections: Sections]
  'field-edit': [fieldPath: string]
}>()

const localSections = ref<Sections>(structuredClone(toRaw(props.sections)))
const activeKeys = ref<string[]>(['identify', 'situation', 'assessment', 'recommendation'])
const assessmentActiveKeys = ref<string[]>(['neuro', 'resp', 'circ'])

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    not_created: '未创建', draft: '草稿', pending: '待交班',
    submitted: '已提交', acknowledged: '已签收',
  }
  return map[props.status] || props.status
})

const aiGeneratedCount = computed(() => props.aiGeneratedFields?.length || 0)

const identifyFields = [
  { key: 'bed', label: '床号' }, { key: 'name', label: '姓名' },
  { key: 'sex', label: '性别' }, { key: 'age', label: '年龄' },
  { key: 'admission_no', label: '住院号' }, { key: 'medical_group', label: '医疗分组' },
]
const situationFields = [
  { key: 'diagnosis', label: '诊断' }, { key: 'surgery', label: '手术名称' },
  { key: 'post_op_day', label: '术后天数' }, { key: 'icu_day', label: '入科天数' },
  { key: 'main_problems', label: '当前主要问题' }, { key: 'life_support_level', label: '生命支持级别' },
  { key: 'life_support_changes', label: '本班变化' },
]
const backgroundFields = [
  { key: 'admission_course', label: '入院/诊疗经过' },
  { key: 'past_history', label: '相关既往史' },
  { key: 'isolation', label: '隔离' },
  { key: 'allergies', label: '过敏' },
]
const assessmentSystems = [
  { key: 'neuro', label: '🧠 神经' }, { key: 'resp', label: '🫁 呼吸' },
  { key: 'circ', label: '❤️ 循环' }, { key: 'temp', label: '🌡️ 体温' },
  { key: 'gi', label: '🫄 消化' }, { key: 'heme', label: '🩸 血液' },
  { key: 'specialty', label: '🔬 专科要点' }, { key: 'nursing', label: '💊 护理要点' },
  { key: 'lines', label: '🪡 管路' }, { key: 'skin', label: '🖐️ 皮肤' },
  { key: 'items', label: '📦 物品交接' },
]

const tasksText = ref((props.sections.recommendation?.tasks || []).join('\n'))
const pendingText = ref((props.sections.recommendation?.pending || []).join('\n'))
const escalationText = ref((props.sections.recommendation?.escalation || []).join('\n'))

function sourceClass(fieldPath: string) {
  const src = props.contentSources?.[fieldPath]
  if (src === 'ai_generated') return 'source-ai'
  if (src === 'human_modified') return 'source-modified'
  return ''
}

function onFieldEdit(fieldPath: string) {
  emit('field-edit', fieldPath)
  syncUp()
}

function onTasksChange() {
  localSections.value.recommendation.tasks = tasksText.value.split('\n').filter(Boolean)
  onFieldEdit('recommendation.tasks')
}
function onPendingChange() {
  localSections.value.recommendation.pending = pendingText.value.split('\n').filter(Boolean)
  onFieldEdit('recommendation.pending')
}
function onEscalationChange() {
  localSections.value.recommendation.escalation = escalationText.value.split('\n').filter(Boolean)
  onFieldEdit('recommendation.escalation')
}

function getAssessmentField(sysKey: string, field: string): any {
  const a = localSections.value.assessment
  if (typeof a[sysKey] === 'object' && a[sysKey] !== null) {
    return a[sysKey][field] || ''
  }
  return ''
}

function setAssessmentField(sysKey: string, field: string, value: string) {
  const a = localSections.value.assessment
  if (typeof a[sysKey] !== 'object' || a[sysKey] === null) {
    a[sysKey] = {}
  }
  a[sysKey][field] = value
  syncUp()
}

function syncUp() {
  emit('update:sections', structuredClone(toRaw(localSections.value)))
}

function toRaw(v: any): any {
  return JSON.parse(JSON.stringify(v))
}

watch(() => props.sections, (val) => {
  localSections.value = structuredClone(toRaw(val))
  tasksText.value = (val.recommendation?.tasks || []).join('\n')
  pendingText.value = (val.recommendation?.pending || []).join('\n')
  escalationText.value = (val.recommendation?.escalation || []).join('\n')
}, { deep: true })
</script>

<style scoped>
.isbar-editor {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.editor-title {
  margin: 0;
  font-size: 15px;
  color: var(--text-main);
}
.editor-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}
.status-draft { background: var(--bg-elevated, #1e293b); color: var(--text-secondary); }
.status-submitted { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.status-acknowledged { background: rgba(34, 197, 94, 0.15); color: #22c55e; }

.section-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.section-grid.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.field-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.field-row label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}
.field-row.source-ai :deep(.ant-input),
.field-row.source-ai :deep(textarea) {
  border-color: #3b82f6;
  border-width: 2px;
}
.field-row.source-modified :deep(.ant-input),
.field-row.source-modified :deep(textarea) {
  border-color: var(--border-color, #334155);
}

.critical-section {
  background: rgba(239, 68, 68, 0.06);
  border: 1px solid rgba(239, 68, 68, 0.2);
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 12px;
}
.critical-title {
  margin: 0 0 8px;
  font-size: 13px;
  color: #ef4444;
}
.critical-item {
  margin-bottom: 6px;
}
</style>
