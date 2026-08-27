<template>
  <a-drawer
    :open="open"
    :width="drawerWidth"
    :title="patient ? `${patient.bed_no}床 ${patient.name}` : '营养详情'"
    @update:open="$emit('update:open', $event)"
  >
    <template v-if="patient">
      <!-- 关键指标 -->
      <section class="drawer-kpis">
        <article>
          <span>NRS2002</span>
          <strong>{{ patient.nrs2002 ?? '待评' }}</strong>
        </article>
        <article>
          <span>NUTRIC</span>
          <strong>{{ patient.nutric ?? '待评' }}</strong>
        </article>
        <article>
          <span>路径</span>
          <strong>{{ patient.route }}</strong>
        </article>
      </section>

      <!-- 达标 -->
      <section class="target-card">
        <div>
          <span>热量</span>
          <strong>{{ patient.kcal_delivered || 0 }} / {{ patient.kcal_goal || 0 }} kcal</strong>
          <meter min="0" max="100" :value="patient.kcal_achieved_pct || 0"></meter>
        </div>
        <div>
          <span>蛋白</span>
          <strong>{{ patient.protein_delivered || 0 }} / {{ patient.protein_goal || 0 }} g</strong>
          <meter min="0" max="100" :value="patient.protein_achieved_pct || 0"></meter>
        </div>
      </section>

      <!-- 闭环指标 -->
      <section class="loop-grid">
        <article :class="`level-${patient.tolerance?.level || 'unknown'}`">
          <span>EN耐受</span>
          <strong>{{ toleranceText }}</strong>
          <small>{{ patient.tolerance?.event_count || 0 }} 条</small>
        </article>
        <article :class="`level-${patient.pn_safety?.level || 'unknown'}`">
          <span>PN安全</span>
          <strong>{{ patient.pn_safety?.needs_review ? '需复核' : '平稳' }}</strong>
          <small>血糖/TG/肝胆</small>
        </article>
        <article :class="`level-${patient.refeeding?.level || 'unknown'}`">
          <span>再喂养</span>
          <strong>{{ levelText(patient.refeeding?.level) }}</strong>
          <small>P/K/Mg</small>
        </article>
        <article :class="`level-${patient.glucose_trend?.level || 'unknown'}`">
          <span>血糖</span>
          <strong>{{ glucoseRange }}</strong>
          <small>{{ patient.glucose_trend?.points?.length || 0 }} 次</small>
        </article>
        <article :class="`level-${patient.closed_loop?.level || 'unknown'}`">
          <span>闭环</span>
          <strong>{{ patient.closed_loop?.open || 0 }} 待办</strong>
          <small>{{ patient.closed_loop?.closed || 0 }} 已完成</small>
        </article>
        <article :class="`level-${patient.data_quality?.level || 'unknown'}`">
          <span>数据</span>
          <strong>{{ patient.data_quality?.completeness || 0 }}%</strong>
          <small>{{ qualityMissing }}</small>
        </article>
      </section>

      <!-- 处方建议 -->
      <section class="rx-card" :class="`level-${patient.prescription?.level || 'unknown'}`">
        <div>
          <span>今日差额</span>
          <strong>{{ patient.prescription?.kcal_gap || 0 }} kcal</strong>
          <small>蛋白 {{ patient.prescription?.protein_gap || 0 }} g</small>
        </div>
        <div>
          <span>建议路径</span>
          <strong>{{ patient.prescription?.route || patient.route }}</strong>
          <small>{{ patient.prescription?.title || '维持当前' }}</small>
        </div>
        <button
          v-for="item in patient.prescription?.suggestions || []"
          :key="item.title"
          type="button"
          @click="$emit('create-task', { title: item.title, target: item.target, priority: item.priority, task_type: 'nutrition_prescription_gap', payload: item })"
        >
          {{ item.title }}
        </button>
      </section>

      <!-- 趋势图 -->
      <section class="chart-grid">
        <article>
          <div class="chart-head"><span>7日热量</span><strong>{{ patient.kcal_achieved_pct || 0 }}%</strong></div>
          <div class="spark-bars">
            <span v-for="item in patient.trend_7d || []" :key="item.day" :style="{ height: `${Math.max(8, Number(item.pct || 0))}%` }"></span>
          </div>
        </article>
        <article>
          <div class="chart-head"><span>血糖波动</span><strong>{{ glucoseRange }}</strong></div>
          <div class="glucose-line">
            <i v-for="(point, idx) in glucosePoints" :key="`${point.time}-${idx}`" :style="{ left: `${glucoseX(idx)}%`, bottom: `${glucoseY(Number(point.value || 0))}%` }"></i>
          </div>
        </article>
      </section>

      <!-- 风险灯 -->
      <a-divider>风险标签</a-divider>
      <div class="risk-lights">
        <span v-for="tag in patient.risk_tags || []" :key="tag" :class="{ hot: isHotTag(tag) }">{{ tag }}</span>
        <span v-if="!(patient.risk_tags || []).length" class="muted">暂无风险标签</span>
      </div>

      <!-- 关键化验 -->
      <a-divider>关键化验</a-divider>
      <section class="lab-grid">
        <article v-for="lab in labRows" :key="lab.key">
          <span>{{ lab.label }}</span>
          <strong>{{ lab.value }}</strong>
          <small>{{ lab.time }}</small>
        </article>
      </section>

      <!-- 营养医嘱 -->
      <a-divider>最近营养医嘱</a-divider>
      <div class="order-list">
        <article v-for="order in patient.orders || []" :key="`${order.name}-${order.time}`">
          <b>{{ order.route }}</b>
          <span>{{ order.name }}</span>
          <small>{{ order.kcal ? `${order.kcal} kcal` : fmt(order.time) }}</small>
        </article>
        <div v-if="!(patient.orders || []).length" class="drawer-empty">近72小时未识别到营养医嘱</div>
      </div>

      <!-- 任务闭环 -->
      <a-divider>任务闭环</a-divider>
      <div class="task-list">
        <article v-for="task in patient.tasks || []" :key="task.task_id" :class="{ closed: task.status !== 'open' }">
          <div>
            <b>{{ task.title }}</b>
            <span>{{ task.payload?.target || task.outcome || '营养任务' }}</span>
          </div>
          <a-button v-if="task.status === 'open'" size="small" type="primary" @click="$emit('close-task', task)">完成</a-button>
          <small v-else>已完成</small>
        </article>
        <div v-if="!(patient.tasks || []).length" class="drawer-empty">暂无营养任务</div>
      </div>

      <!-- 下一步 -->
      <a-divider>下一步</a-divider>
      <div class="action-list">
        <button type="button" class="ai-action" :disabled="aiLoading" @click="$emit('load-ai', true)">
          <strong>{{ aiLoading ? 'AI分析中...' : 'AI营养建议' }}</strong>
          <span>1句总评 + 可执行动作</span>
        </button>
        <button v-for="action in patient.actions || []" :key="action.title" type="button" @click="$emit('create-task', action)">
          <strong>{{ action.title }}</strong>
          <span>{{ action.target }}</span>
        </button>
        <button type="button" @click="$emit('create-task', { title: '营养会诊复核', target: '营养师/主管医生' })">
          <strong>营养会诊复核</strong>
          <span>生成任务</span>
        </button>
      </div>

      <!-- AI 建议 -->
      <section v-if="aiAdvice" class="ai-card">
        <div class="ai-card__head">
          <strong>AI营养建议</strong>
          <span>{{ aiAdvice.degraded ? '规则兜底' : aiAdvice.model || 'AI' }}</span>
        </div>
        <p>{{ aiAdvice.summary || aiAdvice.text || '暂无建议' }}</p>
        <div v-if="aiAdvice.text && aiAdvice.text !== aiAdvice.summary" class="ai-text">{{ aiAdvice.text }}</div>
        <div class="ai-advice-list">
          <article v-for="item in aiAdvice.advice || []" :key="item.title">
            <b>{{ item.title }}</b>
            <span>{{ item.detail }}</span>
          </article>
        </div>
      </section>
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  Button as AButton,
  Divider as ADivider,
  Drawer as ADrawer,
} from 'ant-design-vue'

const drawerWidth = computed(() => {
  if (typeof window !== 'undefined' && window.innerWidth < 768) return '100%'
  if (typeof window !== 'undefined' && window.innerWidth < 1024) return '90%'
  return 720
})

const props = defineProps<{
  open: boolean
  patient: any
  aiAdvice: any
  aiLoading: boolean
  toleranceText: string
  glucoseRange: string
  glucosePoints: any[]
  qualityMissing: string
  deliverySourceLabel: string
  labRows: any[]
  levelText: (level: string) => string
  glucoseX: (idx: any) => number
  glucoseY: (value: any) => number
  isHotTag: (tag: string) => boolean
  fmt: (v: any) => string
}>()

defineEmits<{
  'update:open': [value: boolean]
  'load-ai': [refresh: boolean]
  'create-task': [action: any]
  'close-task': [task: any]
}>()
</script>

<style scoped>
.drawer-kpis {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.drawer-kpis article {
  padding: 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.drawer-kpis span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.drawer-kpis strong {
  display: block;
  margin-top: 4px;
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: var(--text-metric-key, 24px);
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
}

.target-card {
  display: grid;
  gap: 12px;
  margin-bottom: 16px;
  padding: 14px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.target-card span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.target-card strong {
  display: block;
  margin: 4px 0 6px;
  font-size: var(--text-body, 14px);
  color: var(--color-text-primary, #18212B);
}

.loop-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.loop-grid article {
  min-height: 80px;
  padding: 10px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.loop-grid span,
.loop-grid small {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.loop-grid strong {
  display: block;
  margin: 4px 0;
  font-size: var(--text-card-title, 14px);
  font-weight: 650;
  color: var(--color-text-primary, #18212B);
}
.loop-grid .level-danger { border-color: var(--color-danger, #D92D20); border-left: 3px solid var(--color-danger); }
.loop-grid .level-warn { border-color: var(--color-warning, #B54708); border-left: 3px solid var(--color-warning); }
.loop-grid .level-stable { border-left: 3px solid var(--color-success, #16845B); }

.rx-card {
  display: grid;
  grid-template-columns: 1fr 1fr auto;
  gap: 10px;
  align-items: stretch;
  margin-bottom: 16px;
  padding: 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.rx-card.level-danger { border-color: var(--color-danger, #D92D20); }
.rx-card.level-warn { border-color: var(--color-warning, #B54708); }
.rx-card div {
  padding: 10px;
  border-radius: var(--radius-sm, 4px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
}
.rx-card span,
.rx-card small { display: block; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #667085); }
.rx-card strong {
  display: block;
  margin: 4px 0;
  font-size: var(--text-body, 14px);
  font-weight: 650;
  color: var(--color-text-primary, #18212B);
}
.rx-card button {
  min-width: 80px;
  border: 1px solid var(--color-primary, #2563EB);
  border-radius: var(--radius-button, 6px);
  padding: 8px 12px;
  color: var(--color-primary, #2563EB);
  background: var(--color-bg-surface, #fff);
  font-weight: 600;
  font-size: var(--text-body, 14px);
  cursor: pointer;
}
.rx-card button:hover {
  background: var(--color-primary-bg, rgba(37,99,235,0.08));
}

.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  margin-bottom: 16px;
}
.chart-grid article {
  min-height: 120px;
  padding: 12px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.chart-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 10px;
}
.chart-head span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.chart-head strong {
  font-family: var(--font-digit, 'Rajdhani', sans-serif);
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary, #18212B);
}

.spark-bars {
  height: 70px;
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.spark-bars span {
  flex: 1;
  min-height: 6px;
  border-radius: 4px 4px 0 0;
  background: var(--color-primary, #2563EB);
  opacity: 0.7;
}

.glucose-line {
  position: relative;
  height: 70px;
  border-radius: var(--radius-sm, 4px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  overflow: hidden;
}
.glucose-line i {
  position: absolute;
  width: 6px;
  height: 6px;
  margin-left: -3px;
  border-radius: 50%;
  background: var(--color-primary, #2563EB);
}

.risk-lights {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}
.risk-lights span {
  padding: 3px 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-tag, 4px);
  font-size: var(--text-label, 12px);
  color: var(--color-text-secondary, #667085);
  background: var(--color-bg-surface, #fff);
}
.risk-lights span.hot {
  border-color: var(--color-danger, #D92D20);
  color: var(--color-danger, #D92D20);
  background: var(--color-danger-bg, rgba(217,45,32,0.08));
}
.risk-lights span.muted {
  color: var(--color-text-secondary, #667085);
}

.lab-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 8px;
}
.lab-grid article {
  padding: 10px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.lab-grid span {
  display: block;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}
.lab-grid strong {
  display: block;
  margin: 2px 0;
  font-size: var(--text-card-title, 14px);
  font-weight: 650;
  color: var(--color-text-primary, #18212B);
}
.lab-grid small {
  font-size: 11px;
  color: var(--color-text-secondary, #667085);
}

.order-list,
.task-list,
.action-list {
  display: grid;
  gap: 6px;
  margin-bottom: 8px;
}
.order-list article {
  display: grid;
  grid-template-columns: 48px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 8px 10px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.order-list b {
  font-size: var(--text-caption, 12px);
  color: var(--color-primary, #2563EB);
  font-weight: 600;
}
.order-list span {
  font-size: var(--text-body, 14px);
  color: var(--color-text-primary, #18212B);
}
.order-list small {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.task-list article {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.task-list b,
.task-list span { display: block; }
.task-list b { font-size: var(--text-body, 14px); color: var(--color-text-primary, #18212B); }
.task-list span,
.task-list small { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #667085); }
.task-list article.closed { opacity: 0.6; }

.action-list button {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  width: 100%;
  padding: 10px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
  text-align: left;
  cursor: pointer;
  font-family: inherit;
  color: inherit;
}
.action-list button:hover { background: var(--color-bg-surface-secondary, #F1F3F5); }
.action-list .ai-action { border-color: var(--color-primary, #2563EB); }
.action-list strong {
  font-size: var(--text-body, 14px);
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}
.action-list span {
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

.ai-card {
  display: grid;
  gap: 10px;
  margin-top: 16px;
  padding: 14px;
  border: 1px solid var(--color-primary, #2563EB);
  border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff);
}
.ai-card__head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.ai-card__head strong { font-size: var(--text-card-title, 14px); color: var(--color-primary, #2563EB); }
.ai-card__head span { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #667085); }
.ai-card p { margin: 0; font-size: var(--text-body, 14px); color: var(--color-text-primary, #18212B); }
.ai-text { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #667085); white-space: pre-wrap; line-height: 1.5; }
.ai-advice-list { display: grid; gap: 6px; }
.ai-advice-list article { padding: 8px; border: 1px solid var(--color-border, #E3E7EC); border-radius: var(--radius-sm, 4px); background: var(--color-bg-surface-secondary, #F1F3F5); }
.ai-advice-list b { display: block; margin-bottom: 2px; font-size: var(--text-body, 14px); color: var(--color-primary, #2563EB); }
.ai-advice-list span { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #667085); }

.drawer-empty {
  padding: 20px;
  text-align: center;
  font-size: var(--text-caption, 12px);
  color: var(--color-text-secondary, #667085);
}

@media (max-width: 1024px) {
  .lab-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 768px) {
  .drawer-kpis,
  .loop-grid,
  .lab-grid { grid-template-columns: 1fr; }
  .chart-grid,
  .rx-card { grid-template-columns: 1fr; }
}
</style>
