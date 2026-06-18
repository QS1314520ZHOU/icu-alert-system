<template>
  <a-collapse v-model:activeKey="activeKey" class="ai-panel">
    <a-collapse-panel key="ai" header="AI 辅助撰写">
      <a-space class="mb8">
        <a-radio-group
          :value="state.lang"
          size="small"
          @update:value="onLangChange"
        >
          <a-radio-button value="zh">中文</a-radio-button>
          <a-radio-button value="en">English</a-radio-button>
        </a-radio-group>
        <a-button size="small" :loading="state.loading" @click="emit('generate', { analysisType, force: true, lang: state.lang })">
          重新生成
        </a-button>
        <a-button size="small" @click="emit('copy', { analysisType, part: state.part, lang: state.lang })">复制</a-button>
      </a-space>
      <a-tabs
        :active-key="state.part"
        size="small"
        @update:activeKey="onPartChange"
      >
        <a-tab-pane key="interpretation" tab="结果解读" />
        <a-tab-pane key="methods_text" tab="Methods 段落" />
        <a-tab-pane key="results_text" tab="Results 段落" />
      </a-tabs>
      <a-textarea
        :value="currentText"
        :rows="6"
        @update:value="onTextChange"
      />
    </a-collapse-panel>
  </a-collapse>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Button as AButton,
  Collapse as ACollapse,
  Radio as ARadio,
  Space as ASpace,
  Tabs as ATabs,
  Input as AInput,
} from 'ant-design-vue'

type LangKey = 'zh' | 'en'
type PartKey = 'interpretation' | 'methods_text' | 'results_text'

interface AiState {
  open: boolean
  loading: boolean
  lang: LangKey
  part: PartKey
  content: Record<LangKey, Record<PartKey, string>>
}

const props = defineProps<{
  analysisType: string
  result: Record<string, any> | null
  state: AiState
}>()

const emit = defineEmits<{
  (e: 'generate', payload: { analysisType: string; force?: boolean; lang?: LangKey }): void
  (e: 'copy', payload: { analysisType: string; part: PartKey; lang: LangKey }): void
  (e: 'updateLang', payload: { analysisType: string; lang: LangKey }): void
  (e: 'updatePart', payload: { analysisType: string; part: PartKey }): void
  (e: 'updateText', payload: { analysisType: string; part: PartKey; lang: LangKey; value: string }): void
}>()

const ATextarea = AInput.TextArea
const ARadioGroup = ARadio.Group
const ARadioButton = ARadio.Button
const activeKey = ref<string[]>([])

watch(
  () => props.state.open,
  (open) => {
    activeKey.value = open ? ['ai'] : []
  },
  { immediate: true }
)

const currentText = computed(() => props.state.content[props.state.lang]?.[props.state.part] || '')

function onLangChange(val: LangKey): void {
  emit('updateLang', { analysisType: props.analysisType, lang: val })
}

function onPartChange(val: string | number): void {
  emit('updatePart', { analysisType: props.analysisType, part: String(val) as PartKey })
}

function onTextChange(val: string): void {
  emit('updateText', { analysisType: props.analysisType, part: props.state.part, lang: props.state.lang, value: val })
}
</script>

<style scoped>
.ai-panel {
  margin-top: 10px;
}
.mb8 {
  margin-bottom: 8px;
}
</style>
