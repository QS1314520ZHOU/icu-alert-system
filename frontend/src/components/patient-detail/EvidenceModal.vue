<template>
  <a-modal
    :open="open"
    :title="modal.title || '离线指南证据'"
    width="860px"
    :footer="null"
    @update:open="emit('update:open', $event)"
  >
    <div class="evidence-modal">
      <p><strong>来源:</strong> {{ modal.source || '本地知识库' }}</p>
      <p v-if="modal.package_name"><strong>知识包:</strong> {{ modal.package_name }} <span v-if="modal.package_version">v{{ modal.package_version }}</span></p>
      <p v-if="modal.category"><strong>类型:</strong> {{ modal.category }}</p>
      <p v-if="modal.owner"><strong>维护方:</strong> {{ modal.owner }}</p>
      <p v-if="modal.updated_at"><strong>更新时间:</strong> {{ modal.updated_at }}</p>
      <p v-if="modal.priority != null"><strong>优先级:</strong> {{ modal.priority }}</p>
      <p v-if="modal.local_ref"><strong>离线路径:</strong> <code>{{ modal.local_ref }}</code></p>
      <p v-if="modal.recommendation"><strong>推荐:</strong> {{ modal.recommendation }}</p>
      <p v-if="modal.recommendation_grade"><strong>等级:</strong> {{ modal.recommendation_grade }}</p>
      <p v-if="modal.section_title"><strong>章节:</strong> {{ modal.section_title }}</p>
      <p v-if="modal.tags?.length"><strong>标签:</strong> {{ modal.tags.join('、') }}</p>
      <div class="evidence-modal-content">{{ modal.content || '暂无内容' }}</div>
      <div v-if="modal.related_chunks?.length" class="evidence-modal-related">
        <div class="ai-risk-section-title">同来源离线片段</div>
        <ul class="ai-risk-evidence-list">
          <li v-for="(chunk, idx) in modal.related_chunks" :key="chunk.chunk_id || idx">
            <a class="ai-evidence-link" @click.prevent="openEvidence(chunk)">{{ chunk.recommendation || chunk.title || chunk.chunk_id }}</a>
          </li>
        </ul>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { Modal as AModal } from 'ant-design-vue'

defineProps<{
  open: boolean
  modal: any
  openEvidence: (evidence: any) => void | Promise<void>
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()
</script>

<style scoped>
.evidence-modal {
  display: grid;
  gap: 10px;
}
.evidence-modal p {
  margin: 0;
  color: #334155;
}
.evidence-modal-content {
  white-space: pre-wrap;
  line-height: 1.7;
  max-height: 52vh;
  overflow: auto;
  background: #f8fbff;
  border: 1px solid #dce7f5;
  border-radius: 8px;
  padding: 12px;
  color: #334155;
}
.evidence-modal-related {
  margin-top: 4px;
}
.ai-risk-section-title {
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}
.ai-risk-evidence-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}
.ai-evidence-link {
  color: #2563eb;
  cursor: pointer;
}
.ai-evidence-link:hover {
  color: #1d4ed8;
}
</style>
