<template>
  <a-card :bordered="false" class="mdt-step-card">
    <div class="step-card__head">
      <div>
        <span class="step-kicker">第四步</span>
        <h2>文书归档</h2>
        <p v-if="isSessionClosed" class="step-hint">已归档，只读查看。</p>
      </div>
      <div class="step-card__head-actions">
        <a-button :loading="savingWorkspace" :disabled="isSessionClosed" @click="$emit('save')">保存</a-button>
        <a-button type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="$emit('close-session')">关闭归档</a-button>
      </div>
    </div>

    <!-- 文书状态 -->
    <section class="doc-status-strip">
      <article v-for="item in documentStatusRows" :key="item.key" class="doc-status-item">
        <span class="doc-status-label">{{ item.label }}</span>
        <span :class="['doc-status-value', item.status === '已生成' || item.status === '已填写' ? 'is-done' : '']">{{ item.status }}</span>
      </article>
    </section>

    <!-- 标签与成员（一行） -->
    <section class="archive-meta-row">
      <div class="meta-field">
        <label>标签</label>
        <input :value="tagsText" class="field-input" :disabled="isSessionClosed" placeholder="脓毒症、感染" @input="$emit('update:tagsText', ($event.target as HTMLInputElement).value)" />
      </div>
      <div class="meta-field">
        <label>参与成员</label>
        <input :value="participantsText" class="field-input" :disabled="isSessionClosed" placeholder="ICU、感染、呼吸" @input="$emit('update:participantsText', ($event.target as HTMLInputElement).value)" />
      </div>
    </section>

    <!-- 最终纪要 -->
    <section class="archive-section">
      <div class="archive-section__head">
        <span class="archive-section-label">最终纪要</span>
        <a-button size="small" :disabled="!autoSessionSummary" @click="$emit('copy-summary')">复制自动摘要</a-button>
      </div>
      <textarea
        :value="finalSummary"
        class="field-textarea"
        :disabled="isSessionClosed"
        rows="4"
        placeholder="主任确认后的最终纪要；留空使用自动摘要。"
        @input="$emit('update:finalSummary', ($event.target as HTMLTextAreaElement).value)"
      ></textarea>
      <div v-if="autoSessionSummary && !finalSummary" class="auto-summary">
        <p>{{ autoSessionSummary }}</p>
      </div>
    </section>

    <!-- 文书生成 -->
    <section class="doc-generate-grid">
      <article class="doc-generate-card">
        <div class="doc-generate-head">
          <strong>MDT 总结</strong>
          <a-button size="small" :loading="generatingDocType === 'mdt_summary'" :disabled="isSessionClosed" @click="$emit('generate-document', 'mdt_summary')">生成</a-button>
        </div>
        <div v-if="mdtSummaryPreview" class="doc-preview">{{ mdtSummaryPreview }}</div>
        <div v-else class="doc-empty">点击生成后查看</div>
      </article>

      <article class="doc-generate-card">
        <div class="doc-generate-head">
          <strong>会诊记录</strong>
          <a-button size="small" :loading="generatingDocType === 'consultation_request'" :disabled="isSessionClosed" @click="$emit('generate-document', 'consultation_request')">生成</a-button>
        </div>
        <textarea
          :value="consultRecord"
          class="field-textarea field-textarea--doc"
          :disabled="isSessionClosed"
          rows="6"
          placeholder="点击生成后查看并编辑。"
          @input="$emit('update:consultRecord', ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </article>

      <article class="doc-generate-card">
        <div class="doc-generate-head">
          <strong>病程记录</strong>
          <a-button size="small" :loading="generatingDocType === 'daily_progress'" :disabled="isSessionClosed" @click="$emit('generate-document', 'daily_progress')">生成</a-button>
        </div>
        <textarea
          :value="progressRecord"
          class="field-textarea field-textarea--doc"
          :disabled="isSessionClosed"
          rows="6"
          placeholder="点击生成后查看并编辑。"
          @input="$emit('update:progressRecord', ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </article>
    </section>

    <!-- 底部操作 -->
    <div class="step-actions">
      <a-button @click="$emit('export-session')">导出会话</a-button>
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { Button as AButton, Card as ACard } from 'ant-design-vue'

defineProps<{
  tagsText: string
  participantsText: string
  finalSummary: string
  consultRecord: string
  progressRecord: string
  documentStatusRows: any[]
  generatingDocType: string
  autoSessionSummary: string
  mdtSummaryPreview: string
  isSessionClosed: boolean
  savingWorkspace: boolean
}>()

defineEmits<{
  (event: 'update:tagsText', value: string): void
  (event: 'update:participantsText', value: string): void
  (event: 'update:finalSummary', value: string): void
  (event: 'update:consultRecord', value: string): void
  (event: 'update:progressRecord', value: string): void
  (event: 'save'): void
  (event: 'generate-document', docType: 'mdt_summary' | 'daily_progress' | 'consultation_request'): void
  (event: 'copy-summary'): void
  (event: 'close-session'): void
  (event: 'export-session'): void
}>()

void AButton
void ACard
</script>

<style scoped>
.mdt-step-card {
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.step-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}
.step-card__head-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.step-kicker {
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
}
h2 {
  margin: 4px 0 0;
  color: var(--text-primary);
  font-size: 18px;
}
.step-hint {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

/* 文书状态条 */
.doc-status-strip {
  display: flex;
  gap: 12px;
  margin-top: 14px;
  padding: 10px 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.doc-status-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.doc-status-label {
  color: var(--text-secondary);
  font-size: 12px;
}
.doc-status-value {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
}
.doc-status-value.is-done {
  color: #10b981;
}

/* 标签与成员 */
.archive-meta-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 12px;
}
.meta-field label {
  display: block;
  margin-bottom: 4px;
  color: var(--text-secondary);
  font-size: 11px;
}
.field-input {
  width: 100%;
  min-height: 32px;
  padding: 4px 8px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: 13px;
}
.field-input:disabled { opacity: 0.6; }

/* 最终纪要 */
.archive-section {
  margin-top: 12px;
}
.archive-section__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.archive-section-label {
  color: var(--brand);
  font-size: 12px;
  font-weight: 700;
}
.field-textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: var(--bg-surface);
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
}
.field-textarea:disabled { opacity: 0.6; }
.auto-summary {
  margin-top: 6px;
  padding: 8px 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface-2);
}
.auto-summary p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
}

/* 文书生成 */
.doc-generate-grid {
  display: grid;
  gap: 12px;
  margin-top: 14px;
}
.doc-generate-card {
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: var(--card-radius);
  background: var(--bg-surface);
}
.doc-generate-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.doc-generate-head strong {
  color: var(--text-primary);
  font-size: 14px;
}
.field-textarea--doc {
  min-height: 140px;
}
.doc-preview {
  max-height: 200px;
  overflow: auto;
  white-space: pre-wrap;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.6;
  padding: 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface-2);
}
.doc-empty {
  color: var(--text-secondary);
  font-size: 12px;
}

.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 14px;
}

@media (max-width: 980px) {
  .archive-meta-row {
    grid-template-columns: 1fr;
  }
  .doc-status-strip {
    flex-wrap: wrap;
  }
}
</style>
