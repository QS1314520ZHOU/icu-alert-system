<template>
  <button
    type="button"
    :class="['resp-row', `tone-${tone}`, { selected }]"
    @click="$emit('click')"
  >
    <div class="resp-row__rail" />
    <div class="resp-row__bed">
      <span class="resp-row__bed-no">{{ patient.bed_no || '--' }}</span>
    </div>
    <div class="resp-row__info">
      <strong class="resp-row__name">{{ patient.name || '患者' }}</strong>
      <span class="resp-row__mode">{{ patient.ventilator_mode || '模式未记载' }}</span>
    </div>
    <div class="resp-row__vitals">
      <span class="resp-row__vital">
        <i>FiO₂</i><strong>{{ fio2 }}</strong>
      </span>
      <span class="resp-row__vital">
        <i>PEEP</i><strong>{{ peep }}</strong>
      </span>
      <span class="resp-row__vital">
        <i>P/F</i><strong>{{ pf }}</strong>
      </span>
    </div>
    <div class="resp-row__status">
      <span :class="['resp-row__tag', sbtClass]">{{ sbtLabel }}</span>
    </div>
    <div class="resp-row__issue">
      <span :class="['resp-row__issue-text', `issue-${tone}`]">{{ issue }}</span>
    </div>
    <div class="resp-row__action">
      <a-button size="small" @click.stop="$emit('click')">{{ actionLabel }}</a-button>
    </div>
  </button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Button as AButton } from 'ant-design-vue'

const props = defineProps<{
  patient: any
  selected?: boolean
  fio2?: string
  peep?: string
  pf?: string
  sbtLabel?: string
  sbtClass?: string
  issue?: string
  actionLabel?: string
  tone?: 'danger' | 'warn' | 'stable'
}>()

defineEmits<{ click: [] }>()

const tone = computed(() => props.tone || 'stable')
</script>

<style scoped>
.resp-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  font-family: inherit;
  color: inherit;
}
.resp-row:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}
.resp-row.selected {
  border-color: var(--color-primary, #2563EB);
  background: var(--color-primary-bg, rgba(37,99,235,0.08));
}

/* 状态色条 */
.resp-row__rail {
  width: 3px;
  align-self: stretch;
  border-radius: 2px;
  flex-shrink: 0;
  background: var(--color-border, #E3E7EC);
}
.resp-row.tone-danger .resp-row__rail { background: var(--color-danger, #D92D20); }
.resp-row.tone-warn .resp-row__rail { background: var(--color-warning, #B54708); }
.resp-row.tone-stable .resp-row__rail { background: var(--color-success, #16845B); }

/* 床号 */
.resp-row__bed {
  flex-shrink: 0;
  width: 44px;
}
.resp-row__bed-no {
  display: block;
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  line-height: 1.2;
}

/* 患者信息 */
.resp-row__info {
  flex-shrink: 0;
  width: 100px;
  min-width: 0;
}
.resp-row__name {
  display: block;
  font-size: var(--text-body, 14px);
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.resp-row__mode {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 生命体征 */
.resp-row__vitals {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.resp-row__vital {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 8px;
  border-radius: var(--radius-sm, 4px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  min-width: 48px;
}
.resp-row__vital i {
  font-size: 11px;
  font-style: normal;
  color: var(--color-text-secondary, #667085);
  line-height: 1.3;
}
.resp-row__vital strong {
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  line-height: 1.2;
}

/* SBT 状态 */
.resp-row__status {
  flex-shrink: 0;
  width: 80px;
  text-align: center;
}
.resp-row__tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-tag, 4px);
  font-size: var(--text-label, 12px);
  font-weight: 500;
  line-height: 1.5;
}
.resp-row__tag.sbt-ok {
  background: var(--color-success-bg, rgba(22,132,91,0.08));
  color: var(--color-success, #16845B);
}
.resp-row__tag.sbt-no {
  background: var(--color-bg-surface-secondary, #F1F3F5);
  color: var(--color-text-secondary, #667085);
}

/* 当前问题 */
.resp-row__issue {
  flex: 1;
  min-width: 0;
}
.resp-row__issue-text {
  display: block;
  font-size: var(--text-caption, 12px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.resp-row__issue-text.issue-danger { color: var(--color-danger, #D92D20); }
.resp-row__issue-text.issue-warn { color: var(--color-warning, #B54708); }
.resp-row__issue-text.issue-stable { color: var(--color-text-secondary, #667085); }

/* 动作按钮 */
.resp-row__action {
  flex-shrink: 0;
}

@media (max-width: 1024px) {
  .resp-row__vitals { gap: 4px; }
  .resp-row__vital { min-width: 40px; padding: 3px 6px; }
  .resp-row__status { width: 64px; }
}
@media (max-width: 768px) {
  .resp-row {
    flex-wrap: wrap;
    gap: 8px;
  }
  .resp-row__vitals { flex-wrap: wrap; }
  .resp-row__issue { width: 100%; order: 10; }
  .resp-row__action { order: 11; }
}
</style>
