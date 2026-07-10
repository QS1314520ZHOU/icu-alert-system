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
  border: 1px solid rgba(80,199,255,.12);
  border-radius: var(--card-radius);
  background: var(--bg-surface) 0%, var(--bg-surface) 100%);
  padding: 14px;
  box-shadow: var(--card-shadow);
}
.evidence-panel--overview {
  background:
    var(--bg-surface), rgba(34,211,238,0) 32%),
    var(--bg-surface) 0%, rgba(6,17,29,.88) 100%);
}
.panel-title {
  margin-bottom: 10px;
  color: var(--accent);
  font-size: 12px;
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
  border: 1px solid rgba(80,199,255,.14);
  background: var(--bg-surface),.86);
  color: var(--accent);
  font-size: 11px;
  letter-spacing: .08em;
}
.evidence-chip--soft {
  color: var(--text-primary);
}
.evidence-chip--accent {
  color: var(--accent);
  background: rgba(8,90,110,.24);
}
.evidence-chip--warn {
  color: var(--warning);
  background: var(--bg-surface),.5);
  border-color: rgba(245,158,11,.22);
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
  font-size: 11px;
  letter-spacing: .08em;
}
.meta-value {
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
}
.meta-code {
  display: inline-block;
  padding: 6px 8px;
  border-radius: var(--card-radius);
  background: var(--bg-surface),.9);
  border: 1px solid rgba(80,199,255,.12);
  color: #c6f6ff;
  font-size: 11px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
}
.evidence-modal-content {
  white-space: pre-wrap;
  line-height: 1.75;
  max-height: 52vh;
  overflow: auto;
  background: var(--bg-surface),.9);
  border: 1px solid rgba(80,199,255,.12);
  border-radius: var(--card-radius);
  padding: 16px;
  color: #dceeff;
  font-size: 12px;
}
.evidence-modal-related {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: var(--card-radius);
  background: var(--bg-surface) 0%, var(--bg-surface) 100%);
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
  font-size: 12px;
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
html[data-theme='light'] .evidence-panel { background: rgba(243,248,252,0.96); border-color: rgba(187,204,220,0.72); box-shadow: var(--card-shadow); }
html[data-theme='light'] .evidence-panel--overview { background: var(--bg-surface) 0%, rgba(242,247,252,0.98) 100%); }
html[data-theme='light'] .panel-title { color: var(--brand); }
html[data-theme='light'] .evidence-chip { background: var(--bg-surface); border-color: rgba(187,204,220,0.72); color: var(--text-secondary); }
html[data-theme='light'] .evidence-chip--soft { color: var(--text-secondary); }
html[data-theme='light'] .evidence-chip--accent { background: rgba(59,130,246,0.1); color: var(--brand); }
html[data-theme='light'] .evidence-chip--warn { background: rgba(254,243,199,0.96); border-color: rgba(245,158,11,0.28); color: var(--warning); }
html[data-theme='light'] .meta-label { color: var(--brand); }
html[data-theme='light'] .meta-value { color: var(--text-secondary); }
html[data-theme='light'] .meta-code { background: rgba(231,241,249,0.96); border-color: rgba(187,204,220,0.72); color: var(--text-secondary); }
html[data-theme='light'] .evidence-modal-content { background: rgba(243,248,252,0.96); border-color: rgba(187,204,220,0.72); color: var(--text-secondary); }
html[data-theme='light'] .evidence-modal-related { background: var(--bg-surface); border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .ai-evidence-link { color: var(--brand); }
html[data-theme='light'] .ai-evidence-link:hover { color: var(--brand); }
</style>
