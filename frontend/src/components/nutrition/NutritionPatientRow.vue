<template>
  <button
    type="button"
    :class="['nutr-row', `tone-${tone}`, { selected }]"
    @click="$emit('click')"
  >
    <div class="nutr-row__rail" />
    <div class="nutr-row__bed">
      <span class="nutr-row__bed-no">{{ patient.bed_no || '--' }}</span>
    </div>
    <div class="nutr-row__info">
      <strong class="nutr-row__name">{{ patient.name || '患者' }}</strong>
      <span class="nutr-row__route">{{ patient.route || '未开始' }}</span>
    </div>
    <div class="nutr-row__progress">
      <span class="nutr-row__metric">
        <i>热量</i>
        <strong>{{ patient.kcal_achieved_pct ?? '—' }}{{ patient.kcal_achieved_pct != null ? '%' : '' }}</strong>
      </span>
      <span class="nutr-row__metric">
        <i>蛋白</i>
        <strong>{{ patient.protein_achieved_pct ?? '—' }}{{ patient.protein_achieved_pct != null ? '%' : '' }}</strong>
      </span>
    </div>
    <div class="nutr-row__tolerance">
      <span :class="['nutr-row__tag', toleranceClass]">{{ toleranceLabel }}</span>
    </div>
    <div class="nutr-row__refeeding">
      <span :class="['nutr-row__tag', refeedingClass]">{{ refeedingLabel }}</span>
    </div>
    <div class="nutr-row__issue">
      <span :class="['nutr-row__issue-text', `issue-${tone}`]">{{ issue }}</span>
    </div>
    <div class="nutr-row__action">
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
  toleranceLabel?: string
  toleranceClass?: string
  refeedingLabel?: string
  refeedingClass?: string
  issue?: string
  actionLabel?: string
  tone?: 'danger' | 'warn' | 'stable'
}>()

defineEmits<{ click: [] }>()

const tone = computed(() => props.tone || 'stable')
</script>

<style scoped>
.nutr-row {
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
.nutr-row:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}
.nutr-row.selected {
  border-color: var(--color-primary, #2563EB);
  background: var(--color-primary-bg, rgba(37,99,235,0.08));
}

/* 状态色条 */
.nutr-row__rail {
  width: 3px;
  align-self: stretch;
  border-radius: 2px;
  flex-shrink: 0;
  background: var(--color-border, #E3E7EC);
}
.nutr-row.tone-danger .nutr-row__rail { background: var(--color-danger, #D92D20); }
.nutr-row.tone-warn .nutr-row__rail { background: var(--color-warning, #B54708); }
.nutr-row.tone-stable .nutr-row__rail { background: var(--color-success, #16845B); }

/* 床号 */
.nutr-row__bed {
  flex-shrink: 0;
  width: 44px;
}
.nutr-row__bed-no {
  display: block;
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 18px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  line-height: 1.2;
}

/* 患者信息 */
.nutr-row__info {
  flex-shrink: 0;
  width: 100px;
  min-width: 0;
}
.nutr-row__name {
  display: block;
  font-size: var(--text-body, 14px);
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nutr-row__route {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

/* 达标率 */
.nutr-row__progress {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.nutr-row__metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 4px 8px;
  border-radius: var(--radius-sm, 4px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  min-width: 48px;
}
.nutr-row__metric i {
  font-size: 11px;
  font-style: normal;
  color: var(--color-text-secondary, #667085);
  line-height: 1.3;
}
.nutr-row__metric strong {
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
  line-height: 1.2;
}

/* 状态标签 */
.nutr-row__tolerance,
.nutr-row__refeeding {
  flex-shrink: 0;
  width: 72px;
  text-align: center;
}
.nutr-row__tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: var(--radius-tag, 4px);
  font-size: var(--text-label, 12px);
  font-weight: 500;
  line-height: 1.5;
}
.nutr-row__tag.tag-stable {
  background: var(--color-success-bg, rgba(22,132,91,0.08));
  color: var(--color-success, #16845B);
}
.nutr-row__tag.tag-warn {
  background: var(--color-warning-bg, rgba(181,71,8,0.08));
  color: var(--color-warning, #B54708);
}
.nutr-row__tag.tag-danger {
  background: var(--color-danger-bg, rgba(217,45,32,0.08));
  color: var(--color-danger, #D92D20);
}
.nutr-row__tag.tag-muted {
  background: var(--color-bg-surface-secondary, #F1F3F5);
  color: var(--color-text-secondary, #667085);
}

/* 当前问题 */
.nutr-row__issue {
  flex: 1;
  min-width: 0;
}
.nutr-row__issue-text {
  display: block;
  font-size: var(--text-caption, 12px);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nutr-row__issue-text.issue-danger { color: var(--color-danger, #D92D20); }
.nutr-row__issue-text.issue-warn { color: var(--color-warning, #B54708); }
.nutr-row__issue-text.issue-stable { color: var(--color-text-secondary, #667085); }

/* 动作按钮 */
.nutr-row__action {
  flex-shrink: 0;
}

@media (max-width: 1024px) {
  .nutr-row__progress { gap: 4px; }
  .nutr-row__metric { min-width: 40px; padding: 3px 6px; }
  .nutr-row__tolerance,
  .nutr-row__refeeding { width: 56px; }
}
@media (max-width: 768px) {
  .nutr-row {
    flex-wrap: wrap;
    gap: 8px;
  }
  .nutr-row__progress { flex-wrap: wrap; }
  .nutr-row__issue { width: 100%; order: 10; }
  .nutr-row__action { order: 11; }
}
</style>
