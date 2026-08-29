<template>
  <div class="rule-calc">
    <div v-if="!ruleCalc" class="calc-empty">暂无评分/规则计算数据</div>
    <template v-else>
      <div class="calc-header">
        <span class="calc-type">{{ scoreTypeLabel(ruleCalc.score_type) }}</span>
        <span v-if="ruleCalc.total_score != null" class="calc-total">
          总分：<strong>{{ ruleCalc.total_score }}</strong>
        </span>
        <span v-if="ruleCalc.calc_time" class="calc-time">{{ formatTime(ruleCalc.calc_time) }}</span>
      </div>
      <p v-if="ruleCalc.description" class="calc-desc">{{ ruleCalc.description }}</p>
      <p v-if="ruleCalc.statistical_scope" class="calc-scope">统计口径：{{ ruleCalc.statistical_scope }}</p>

      <!-- 灯号展示（撤机/转出） -->
      <div v-if="ruleCalc.lights?.length" class="calc-lights">
        <div v-for="(light, idx) in ruleCalc.lights" :key="idx" :class="['light-item', light.ok ? 'ok' : 'bad']">
          <i>{{ light.ok ? '✓' : '✗' }}</i>
          <span>{{ light.label }}</span>
        </div>
      </div>

      <!-- 评分明细 -->
      <div v-if="ruleCalc.items?.length" class="calc-items">
        <div v-for="(item, idx) in ruleCalc.items" :key="idx" class="calc-item">
          <span class="item-label">{{ item.label || item.name || `项目${idx + 1}` }}</span>
          <span v-if="item.score != null" class="item-score">{{ item.score }}分</span>
          <span v-if="item.value != null" class="item-value">{{ item.value }}</span>
          <span v-if="item.ok != null" :class="['item-status', item.ok ? 'ok' : 'bad']">{{ item.ok ? '通过' : '未通过' }}</span>
          <span v-if="item.description" class="item-desc">{{ item.description }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { RuleCalculation } from '../../api/clinicalEvidence'

defineProps<{
  ruleCalc: RuleCalculation | null
}>()

function scoreTypeLabel(type: string): string {
  const map: Record<string, string> = {
    sofa: 'SOFA 器官功能评分',
    qsofa: 'qSOFA 感染风险评分',
    apache: 'APACHE II 评分',
    deliric: 'DELIRIC 谵妄风险',
    pre_deliric: 'PRE-DELIRIC 谵妄风险',
    sepsis: '脓毒症评分',
    aki: '急性肾损伤评分',
    ards: 'ARDS 评分',
    weaning: '撤机评估',
    respiratory: '呼吸评估',
    sbt_assessment: 'SBT 自主呼吸试验',
    discharge_readiness: '转出就绪度',
    rule_noise: '规则噪声统计',
    nutrition: '营养评估',
  }
  return map[type] || type
}

function formatTime(t: string): string {
  const d = new Date(t)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.calc-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.calc-type {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #182230);
}
.calc-total {
  font-size: 13px;
  color: var(--text-secondary, #6B7280);
}
.calc-total strong { font-size: 18px; color: var(--color-primary, #2563EB); }
.calc-time { font-size: 11px; color: var(--text-tertiary, #9CA3AF); margin-left: auto; }
.calc-desc { font-size: 12px; color: var(--text-secondary, #6B7280); margin-bottom: 8px; }
.calc-scope { font-size: 12px; color: var(--text-tertiary, #9CA3AF); margin-bottom: 8px; font-style: italic; }

.calc-lights {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.light-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}
.light-item.ok { background: #DCFCE7; color: #166534; }
.light-item.bad { background: #FEF2F2; color: #991B1B; }
.light-item i { font-style: normal; font-weight: 700; }

.calc-items {
  display: grid;
  gap: 6px;
}
.calc-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  background: var(--bg-secondary, #F9FAFB);
  font-size: 12px;
}
.item-label { flex: 1; color: var(--text-primary, #182230); }
.item-score { font-weight: 700; color: var(--color-primary, #2563EB); }
.item-value { color: var(--text-secondary, #6B7280); }
.item-status {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  font-weight: 600;
}
.item-status.ok { background: #DCFCE7; color: #166534; }
.item-status.bad { background: #FEF2F2; color: #991B1B; }
.item-desc { font-size: 11px; color: var(--text-tertiary, #9CA3AF); }
.calc-empty {
  text-align: center;
  padding: 20px;
  color: var(--text-tertiary, #9CA3AF);
  font-size: 13px;
}
</style>
