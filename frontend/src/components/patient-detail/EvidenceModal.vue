<template>
  <a-modal
    :open="open"
    :title="modal.title || '离线指南证据'"
    width="860px"
    :footer="null"
    wrap-class-name="icu-evidence-modal-wrap"
    @update:open="emit('update:open', $event)"
  >
    <div class="evidence-modal">
      <section class="evidence-panel evidence-panel--overview">
        <div class="evidence-chip-row">
          <span class="evidence-chip ds-badge">{{ modal.source || '本地知识库' }}</span>
          <span v-if="modal.category" class="evidence-chip evidence-chip--soft">{{ modal.category }}</span>
          <span v-if="modal.recommendation_grade" class="evidence-chip evidence-chip--accent">{{ modal.recommendation_grade }}</span>
          <span v-if="modal.priority != null" class="evidence-chip evidence-chip--warn">P{{ modal.priority }}</span>
        </div>
        <div class="evidence-meta-grid">
          <div class="meta-item">
            <span class="meta-label">知识包</span>
            <span class="meta-value">
              {{ modal.package_name || '离线知识包' }}
              <span v-if="modal.package_version">v{{ modal.package_version }}</span>
            </span>
          </div>
          <div v-if="modal.owner" class="meta-item">
            <span class="meta-label">维护方</span>
            <span class="meta-value">{{ modal.owner }}</span>
          </div>
          <div v-if="modal.updated_at" class="meta-item">
            <span class="meta-label">更新时间</span>
            <span class="meta-value">{{ modal.updated_at }}</span>
          </div>
          <div v-if="modal.section_title" class="meta-item">
            <span class="meta-label">章节</span>
            <span class="meta-value">{{ modal.section_title }}</span>
          </div>
          <div v-if="modal.recommendation" class="meta-item meta-item--full">
            <span class="meta-label">推荐摘要</span>
            <span class="meta-value">{{ modal.recommendation }}</span>
          </div>
          <div v-if="modal.tags?.length" class="meta-item meta-item--full">
            <span class="meta-label">标签</span>
            <span class="meta-value">{{ modal.tags.join('、') }}</span>
          </div>
          <div v-if="modal.local_ref" class="meta-item meta-item--full">
            <span class="meta-label">离线路径</span>
            <code class="meta-code">{{ modal.local_ref }}</code>
          </div>
        </div>
      </section>

      <section class="evidence-panel">
        <div class="panel-title">证据内容</div>
        <div class="evidence-modal-content">{{ modal.content || '暂无内容' }}</div>
      </section>

      <div v-if="modal.related_chunks?.length" class="evidence-modal-related">
        <div class="panel-title">同源离线片段</div>
        <ul class="ai-risk-evidence-list">
          <li v-for="(chunk, idx) in modal.related_chunks" :key="chunk.chunk_id || idx">
            <a class="ai-evidence-link" @click.prevent="openEvidence(chunk)">
              {{ chunk.recommendation || chunk.title || chunk.chunk_id }}
            </a>
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
  gap: 14px;
}
.evidence-panel {
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  padding: 14px;
  box-shadow: var(--shadow-sm);
}
.evidence-panel--overview {
  background: var(--bg-surface);
}
.panel-title {
  margin-bottom: 10px;
  color: var(--accent);
  font-size: var(--text-caption);
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.evidence-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.evidence-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: var(--card-radius);
  border: 1px solid var(--color-border);
  background: var(--bg-surface);
  color: var(--accent);
  font-size: var(--text-label);
  letter-spacing: .08em;
}
.evidence-chip--soft {
  color: var(--text-primary);
}
.evidence-chip--accent {
  color: var(--accent);
  background: var(--color-info-bg);
}
.evidence-chip--warn {
  color: var(--warning);
  background: var(--bg-surface);
  border-color: var(--color-border);
}
.evidence-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 12px;
}
.meta-item {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.meta-item--full {
  grid-column: 1 / -1;
}
.meta-label {
  color: var(--accent);
  font-size: var(--text-label);
  letter-spacing: .08em;
}
.meta-value {
  color: var(--text-primary);
  font-size: var(--text-caption);
  line-height: 1.6;
  word-break: break-word;
}
.meta-code {
  display: inline-block;
  padding: 6px 8px;
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
  font-size: var(--text-label);
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
}
.evidence-modal-content {
  white-space: pre-wrap;
  line-height: 1.75;
  max-height: 52vh;
  overflow: auto;
  background: var(--bg-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  padding: 16px;
  color: var(--color-text-primary);
  font-size: var(--text-caption);
}
.evidence-modal-related {
  border: 1px solid var(--color-border);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
  padding: 14px;
}
.ai-risk-evidence-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 8px;
}
.ai-evidence-link {
  color: var(--chart-1);
  cursor: pointer;
  transition: color 0.2s ease;
  font-size: var(--text-caption);
  line-height: 1.55;
}
.ai-evidence-link:hover {
  color: var(--chart-1);
}

@media (max-width: 900px) {
  .evidence-meta-grid {
    grid-template-columns: 1fr;
  }
}

/* Light mode overrides */
html[data-theme='light'] .evidence-panel { background: var(--color-bg-surface); border-color: var(--color-border); box-shadow: var(--shadow-sm); }
html[data-theme='light'] .evidence-panel--overview { background: var(--bg-surface); }
html[data-theme='light'] .panel-title { color: var(--brand); }
html[data-theme='light'] .evidence-chip { background: var(--bg-surface); border-color: var(--color-border); color: var(--text-secondary); }
html[data-theme='light'] .evidence-chip--soft { color: var(--text-secondary); }
html[data-theme='light'] .evidence-chip--accent { background: var(--color-primary-bg); color: var(--brand); }
html[data-theme='light'] .evidence-chip--warn { background: var(--color-warning-soft-bg); border-color: var(--color-border); color: var(--warning); }
html[data-theme='light'] .meta-label { color: var(--brand); }
html[data-theme='light'] .meta-value { color: var(--text-secondary); }
html[data-theme='light'] .meta-code { background: var(--color-bg-surface); border-color: var(--color-border); color: var(--text-secondary); }
html[data-theme='light'] .evidence-modal-content { background: var(--color-bg-surface); border-color: var(--color-border); color: var(--text-secondary); }
html[data-theme='light'] .evidence-modal-related { background: var(--bg-surface); border-color: var(--color-border); }
html[data-theme='light'] .ai-evidence-link { color: var(--brand); }
html[data-theme='light'] .ai-evidence-link:hover { color: var(--brand); }
</style>
