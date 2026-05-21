<template>
  <div class="progress-note-editor">
    <!-- S 主观 -->
    <section class="pne-section" @mouseenter="emit('section-focus', 'subjective')">
      <div class="pne-section-header">
        <span class="pne-section-tag pne-section-tag--s">S</span>
        <span class="pne-section-title">主观</span>
      </div>
      <CitationTextarea
        :model-value="localDraft?.subjective || ''"
        @update:model-value="localDraft.subjective = $event"
        :citations="citations"
        :rows="2"
        :disabled="readonly"
      />
    </section>

    <!-- O 客观 -->
    <section class="pne-section" @mouseenter="emit('section-focus', 'objective')">
      <div class="pne-section-header">
        <span class="pne-section-tag pne-section-tag--o">O</span>
        <span class="pne-section-title">客观</span>
      </div>
      <div v-for="(val, key) in localDraft?.objective" :key="key" class="pne-sub-field">
        <label class="pne-sub-label">{{ objectiveLabels[key as keyof typeof localDraft.objective] || key }}</label>
        <CitationTextarea
          :model-value="val || ''"
          @update:model-value="localDraft.objective[key as keyof typeof localDraft.objective] = $event"
          :citations="citations"
          :rows="2"
          :disabled="readonly"
        />
      </div>
    </section>

    <!-- A 评估 -->
    <section class="pne-section" @mouseenter="emit('section-focus', 'assessment')">
      <div class="pne-section-header">
        <span class="pne-section-tag pne-section-tag--a">A</span>
        <span class="pne-section-title">评估</span>
      </div>
      <div v-for="(val, sys) in localDraft?.assessment" :key="sys" class="pne-sub-field">
        <div class="pne-sub-label-row">
          <label class="pne-sub-label">{{ sys }}</label>
          <a-button type="link" danger size="small" :disabled="readonly" @click="removeSystem(sys as string)">移除</a-button>
        </div>
        <CitationTextarea
          :model-value="val || ''"
          @update:model-value="localDraft.assessment[sys as string] = $event"
          :citations="citations"
          :rows="2"
          :disabled="readonly"
        />
      </div>
      <a-button size="small" type="dashed" block :disabled="readonly" @click="showAddSystem = true">
        + 添加系统评估
      </a-button>
      <a-modal
        v-model:open="showAddSystem"
        title="添加系统评估"
        @ok="confirmAddSystem"
        ok-text="添加"
        cancel-text="取消"
      >
        <a-select
          v-model:value="newSystemKey"
          placeholder="选择系统"
          style="width: 100%"
          :options="availableSystems"
        />
      </a-modal>
    </section>

    <!-- P 计划 -->
    <section class="pne-section" @mouseenter="emit('section-focus', 'plan')">
      <div class="pne-section-header">
        <span class="pne-section-tag pne-section-tag--p">P</span>
        <span class="pne-section-title">计划</span>
      </div>
      <div v-for="(item, idx) in localDraft?.plan" :key="idx" class="pne-plan-item">
        <a-textarea
          :value="item"
          @input="localDraft.plan[idx] = ($event.target as HTMLTextAreaElement).value"
          :auto-size="{ minRows: 1, maxRows: 4 }"
          :disabled="readonly"
          class="pne-plan-input"
        />
        <a-button type="link" danger size="small" :disabled="readonly" @click="localDraft.plan.splice(idx, 1)">删</a-button>
      </div>
      <a-button size="small" type="dashed" block :disabled="readonly" @click="localDraft.plan.push('')">
        + 添加计划
      </a-button>
    </section>

    <!-- Footer: trend + key concerns -->
    <div class="pne-footer">
      <div class="pne-trend-row">
        <span class="pne-trend-label">总体趋势</span>
        <a-tag :color="trendColor">{{ localDraft?.overall_trend }}</a-tag>
      </div>
      <div class="pne-concerns">
        <span class="pne-concerns-label">重点关注</span>
        <div class="pne-concerns-list">
          <a-tag v-for="(c, i) in localDraft?.key_concerns" :key="i" color="orange">{{ c }}</a-tag>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Button as AButton,
  Modal as AModal,
  Select as ASelect,
  Tag as ATag,
  Textarea as ATextarea,
} from 'ant-design-vue'
import CitationTextarea from './CitationTextarea.vue'
import type { DraftContent, Citation } from '../../api/clinicalDocuments'

const props = defineProps<{
  draft: DraftContent
  citations: Citation[]
  readonly?: boolean
}>()
const emit = defineEmits(['update:draft', 'section-focus'])

const localDraft = ref<DraftContent>(JSON.parse(JSON.stringify(props.draft || {})))

// Watch prop change from parent
watch(
  () => props.draft,
  (newVal) => {
    const localStr = JSON.stringify(localDraft.value)
    const newStr = JSON.stringify(newVal || {})
    if (localStr !== newStr) {
      localDraft.value = JSON.parse(newStr)
    }
  },
  { deep: true, immediate: true }
)

// Watch local changes and emit
watch(
  localDraft,
  (newVal) => {
    const propStr = JSON.stringify(props.draft || {})
    const localStr = JSON.stringify(newVal)
    if (propStr !== localStr) {
      emit('update:draft', JSON.parse(localStr))
    }
  },
  { deep: true }
)

const objectiveLabels: Record<string, string> = {
  vitals: '生命体征',
  labs: '化验',
  drugs: '用药',
  ventilator: '呼吸机',
  alerts: '告警',
}

const trendColor = computed(() => {
  const mapping: Record<string, string> = { '好转': 'green', '平稳': 'blue', '恶化': 'red' }
  return mapping[localDraft.value?.overall_trend || ''] || 'default'
})

const allSystems = ['循环', '呼吸', '肾脏', '感染', '神经', '血液', '代谢', '其他']
const showAddSystem = ref(false)
const newSystemKey = ref('')

const availableSystems = computed(() =>
  allSystems
    .filter((s) => localDraft.value?.assessment && !(s in localDraft.value.assessment))
    .map((s) => ({ value: s, label: s })),
)

function confirmAddSystem() {
  if (newSystemKey.value && localDraft.value?.assessment) {
    localDraft.value.assessment[newSystemKey.value] = ''
    newSystemKey.value = ''
  }
  showAddSystem.value = false
}

function removeSystem(sys: string) {
  if (localDraft.value?.assessment) {
    delete localDraft.value.assessment[sys]
  }
}
</script>

<style scoped>
.progress-note-editor {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.pne-section {
  background: #fff;
  border: 1px solid #f0f0f0;
  border-radius: 8px;
  padding: 14px 16px;
  transition: border-color 0.2s;
}
.pne-section:hover {
  border-color: #d9d9d9;
}

.pne-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.pne-section-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 14px;
  color: #fff;
}
.pne-section-tag--s { background: #722ed1; }
.pne-section-tag--o { background: #1677ff; }
.pne-section-tag--a { background: #fa8c16; }
.pne-section-tag--p { background: #52c41a; }

.pne-section-title {
  font-weight: 600;
  font-size: 14px;
}

.pne-sub-field {
  margin-bottom: 8px;
}
.pne-sub-label-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.pne-sub-label {
  font-size: 12px;
  font-weight: 500;
  color: #595959;
  margin-bottom: 4px;
  display: block;
}

.pne-plan-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 6px;
}
.pne-plan-input {
  flex: 1;
}

.pne-footer {
  padding: 12px 16px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #f0f0f0;
}
.pne-trend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.pne-trend-label, .pne-concerns-label {
  font-weight: 600;
  font-size: 13px;
}
.pne-concerns-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

/* ================= Dark Theme Overrides ================= */
:global(.theme-dark) .pne-section {
  background: #0d1a2b;
  border-color: rgba(125, 167, 214, 0.14);
}
:global(.theme-dark) .pne-section:hover {
  border-color: rgba(125, 167, 214, 0.28);
}
:global(.theme-dark) .pne-section-title {
  color: #d9e6f3;
}
:global(.theme-dark) .pne-sub-label {
  color: #7f93ab;
}
:global(.theme-dark) .pne-footer {
  background: #0d1a2b;
  border-color: rgba(125, 167, 214, 0.14);
}
:global(.theme-dark) .pne-trend-label,
:global(.theme-dark) .pne-concerns-label {
  color: #d9e6f3;
}
</style>
