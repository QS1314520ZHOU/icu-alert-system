<template>
  <a-card :bordered="false" class="mdt-step-card">
    <div class="step-card__head">
      <div>
        <span class="step-kicker">第四步</span>
        <h2>文书生成与归档</h2>
        <p v-if="isSessionClosed">该 MDT 会话已归档，只读查看。</p>
        <p v-else>把决议、复评计划和最终纪要写入会诊记录，完成后关闭归档。</p>
      </div>
      <a-button type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="$emit('save')">保存文书</a-button>
    </div>

    <section class="archive-grid">
      <article class="archive-card">
        <span>标签</span>
        <input :value="tagsText" class="field-input" :disabled="isSessionClosed" placeholder="脓毒症、撤机、高乳酸" @input="$emit('update:tagsText', ($event.target as HTMLInputElement).value)" />
      </article>
      <article class="archive-card">
        <span>参与成员</span>
        <input :value="participantsText" class="field-input" :disabled="isSessionClosed" placeholder="ICU、感染、呼吸、药学" @input="$emit('update:participantsText', ($event.target as HTMLInputElement).value)" />
      </article>
    </section>

    <section class="archive-card archive-card--summary">
      <span>最终纪要</span>
      <textarea :value="finalSummary" class="field-textarea" :disabled="isSessionClosed" rows="6" placeholder="可填写主任确认后的最终纪要；留空时可使用自动摘要。" @input="$emit('update:finalSummary', ($event.target as HTMLTextAreaElement).value)"></textarea>
      <div v-if="autoSessionSummary" class="auto-summary">
        <strong>自动摘要</strong>
        <p>{{ autoSessionSummary }}</p>
      </div>
    </section>

    <section class="document-grid">
      <article v-for="item in documentStatusRows" :key="item.key">
        <span>{{ item.label }}</span>
        <strong>{{ item.status }}</strong>
        <small>{{ item.detail }}</small>
      </article>
    </section>

    <section class="generated-docs">
      <article class="archive-card">
        <div class="doc-head">
          <span>MDT 总结</span>
          <a-button size="small" :loading="generatingDocType === 'mdt_summary'" :disabled="isSessionClosed" @click="$emit('generate-document', 'mdt_summary')">重新生成</a-button>
        </div>
        <div v-if="mdtSummaryPreview" class="doc-preview">{{ mdtSummaryPreview }}</div>
        <div v-else class="doc-empty">点击“生成 MDT 总结”后在这里查看结果。</div>
      </article>

      <article class="archive-card">
        <div class="doc-head">
          <span>会诊记录</span>
          <a-button size="small" :loading="generatingDocType === 'consultation_request'" :disabled="isSessionClosed" @click="$emit('generate-document', 'consultation_request')">重新生成</a-button>
        </div>
        <textarea
          :value="consultRecord"
          class="field-textarea field-textarea--document"
          :disabled="isSessionClosed"
          rows="8"
          placeholder="点击“生成会诊记录”后在这里查看并编辑。"
          @input="$emit('update:consultRecord', ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </article>

      <article class="archive-card">
        <div class="doc-head">
          <span>病程记录</span>
          <a-button size="small" :loading="generatingDocType === 'daily_progress'" :disabled="isSessionClosed" @click="$emit('generate-document', 'daily_progress')">重新生成</a-button>
        </div>
        <textarea
          :value="progressRecord"
          class="field-textarea field-textarea--document"
          :disabled="isSessionClosed"
          rows="8"
          placeholder="点击“生成病程”后在这里查看并编辑。"
          @input="$emit('update:progressRecord', ($event.target as HTMLTextAreaElement).value)"
        ></textarea>
      </article>
    </section>

    <div class="step-actions">
      <a-button :disabled="!autoSessionSummary" @click="$emit('copy-summary')">复制摘要</a-button>
      <a-button :loading="generatingDocType === 'mdt_summary'" :disabled="isSessionClosed" @click="$emit('generate-document', 'mdt_summary')">生成 MDT 总结</a-button>
      <a-button :loading="generatingDocType === 'consultation_request'" :disabled="isSessionClosed" @click="$emit('generate-document', 'consultation_request')">生成会诊记录</a-button>
      <a-button :loading="generatingDocType === 'daily_progress'" :disabled="isSessionClosed" @click="$emit('generate-document', 'daily_progress')">生成病程</a-button>
      <a-button @click="$emit('export-session')">导出会话</a-button>
      <a-button type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="$emit('close-session')">关闭归档</a-button>
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
.mdt-step-card,
.archive-card {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.66);
}
.step-card__head,
.step-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.step-kicker,
.archive-card span,
.document-grid span {
  color: rgba(125, 211, 252, 0.86);
  font-size: 12px;
  font-weight: 700;
}
h2 {
  margin: 4px 0 6px;
  color: #f8fafc;
}
p {
  margin: 0;
  color: rgba(203, 213, 225, 0.74);
  line-height: 1.6;
  white-space: pre-wrap;
}
.archive-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.archive-card {
  padding: 14px;
}
.archive-card--summary {
  margin-top: 12px;
}
.field-input,
.field-textarea {
  width: 100%;
  margin-top: 8px;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 4px;
  padding: 10px 12px;
  color: #f8fafc;
  background: rgba(15, 23, 42, 0.92);
}
.field-textarea--document {
  min-height: 180px;
  line-height: 1.65;
}
.auto-summary {
  margin-top: 12px;
  padding: 12px;
  border-radius: 4px;
  background: rgba(2, 6, 23, 0.3);
}
.auto-summary strong,
.document-grid strong {
  display: block;
  color: #f8fafc;
}
.document-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.generated-docs {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}
.doc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.doc-preview {
  margin-top: 10px;
  max-height: 280px;
  overflow: auto;
  white-space: pre-wrap;
  color: rgba(226, 232, 240, 0.86);
  line-height: 1.7;
  padding: 12px;
  border-radius: 4px;
  background: rgba(2, 6, 23, 0.3);
}
.doc-empty {
  margin-top: 10px;
  color: rgba(148, 163, 184, 0.82);
}
.document-grid article {
  padding: 12px;
  border-radius: 4px;
  background: rgba(2, 6, 23, 0.3);
}
.document-grid small {
  color: rgba(148, 163, 184, 0.82);
}
.step-actions {
  justify-content: flex-end;
  flex-wrap: wrap;
  margin-top: 16px;
}
@media (max-width: 980px) {
  .archive-grid,
  .document-grid {
    grid-template-columns: 1fr;
  }
}

:global(html[data-theme='light']) .mdt-step-card,
:global(html[data-theme='light']) .archive-card {
  border-color: rgba(15, 23, 42, 0.1);
  background: #FFFFFF;
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}
:global(html[data-theme='light']) h2,
:global(html[data-theme='light']) .auto-summary strong,
:global(html[data-theme='light']) .document-grid strong {
  color: #1D2129;
}
:global(html[data-theme='light']) p,
:global(html[data-theme='light']) .doc-preview {
  color: #1D2129;
}
:global(html[data-theme='light']) .step-kicker,
:global(html[data-theme='light']) .archive-card span,
:global(html[data-theme='light']) .document-grid span {
  color: #0369a1;
}
:global(html[data-theme='light']) .field-input,
:global(html[data-theme='light']) .field-textarea {
  border-color: rgba(15, 23, 42, 0.14);
  color: #1D2129;
  background: #f8fafc;
}
:global(html[data-theme='light']) .field-input::placeholder,
:global(html[data-theme='light']) .field-textarea::placeholder {
  color: #4E5969;
}
:global(html[data-theme='light']) .auto-summary,
:global(html[data-theme='light']) .document-grid article,
:global(html[data-theme='light']) .doc-preview {
  background: #f1f5f9;
}
:global(html[data-theme='light']) .document-grid small,
:global(html[data-theme='light']) .doc-empty {
  color: #4E5969;
}
</style>
