<template>
  <div class="ai-evidence">
    <div v-if="!aiAnalysis" class="ai-empty">尚未生成 AI 分析</div>
    <div v-else-if="isEmpty" class="ai-empty">尚未生成 AI 分析</div>
    <template v-else>
      <!-- 支持证据 -->
      <div class="ai-section">
        <div class="ai-section-header supporting">
          <span class="ai-icon">+</span>
          <span>支持证据</span>
        </div>
        <div v-if="aiAnalysis.supporting_evidence.length" class="ai-list">
          <div v-for="(item, idx) in aiAnalysis.supporting_evidence" :key="idx" class="ai-item supporting">
            {{ item }}
          </div>
        </div>
        <div v-else class="ai-list-empty">暂无支持证据</div>
      </div>

      <!-- 反对证据 -->
      <div class="ai-section">
        <div class="ai-section-header opposing">
          <span class="ai-icon">−</span>
          <span>反对证据</span>
        </div>
        <div v-if="aiAnalysis.opposing_evidence.length" class="ai-list">
          <div v-for="(item, idx) in aiAnalysis.opposing_evidence" :key="idx" class="ai-item opposing">
            {{ item }}
          </div>
        </div>
        <div v-else class="ai-list-empty">暂无反对证据</div>
      </div>

      <!-- 不确定性 -->
      <div class="ai-section">
        <div class="ai-section-header uncertain">
          <span class="ai-icon">?</span>
          <span>不确定性</span>
        </div>
        <div v-if="aiAnalysis.uncertainties.length" class="ai-list">
          <div v-for="(item, idx) in aiAnalysis.uncertainties" :key="idx" class="ai-item uncertain">
            {{ item }}
          </div>
        </div>
        <div v-else class="ai-list-empty">暂无不确定因素</div>
      </div>

      <!-- 免责声明 -->
      <div class="ai-disclaimer">
        <span class="disclaimer-badge">AI</span>
        <span>{{ aiAnalysis.disclaimer || 'AI生成，待临床确认' }}</span>
        <span v-if="aiAnalysis.model" class="ai-model">模型：{{ aiAnalysis.model }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AiAnalysis } from '../../api/clinicalEvidence'

const props = defineProps<{
  aiAnalysis: AiAnalysis | null
}>()

const isEmpty = computed(() => {
  if (!props.aiAnalysis) return true
  const a = props.aiAnalysis
  return !a.supporting_evidence?.length && !a.opposing_evidence?.length && !a.uncertainties?.length
})
</script>

<style scoped>
.ai-section { margin-bottom: 12px; }
.ai-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}
.ai-section-header.supporting { background: var(--color-normal-bg); color: var(--color-success); }
.ai-section-header.opposing { background: var(--color-critical-bg); color: var(--color-critical); }
.ai-section-header.uncertain { background: var(--color-warning-soft-bg); color: var(--color-warning); }
.ai-icon {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-weight: 700;
  font-size: 14px;
}
.ai-list { display: grid; gap: 4px; }
.ai-item {
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.6;
  border-left: 3px solid;
}
.ai-item.supporting { border-color: var(--color-success); background: var(--color-normal-bg); }
.ai-item.opposing { border-color: var(--color-danger); background: var(--color-critical-bg); }
.ai-item.uncertain { border-color: var(--color-warning); background: var(--color-warning-soft-bg); }
.ai-list-empty {
  font-size: 12px;
  color: var(--text-tertiary, #9CA3AF);
  padding: 4px 10px;
}
.ai-disclaimer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--color-bg-inset);
  font-size: 11px;
  color: var(--text-secondary, #6B7280);
  margin-top: 8px;
}
.disclaimer-badge {
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--color-ai);
  color: var(--color-text-inverse);
  font-size: 10px;
  font-weight: 700;
}
.ai-model { margin-left: auto; font-size: 10px; color: var(--text-tertiary, #9CA3AF); }
.ai-empty {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary, #9CA3AF);
  font-size: 13px;
}
</style>
