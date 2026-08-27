<template>
  <div class="special-treatments">
    <!-- 抗菌药管理 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label info">抗菌药管理</span>
        <span class="section-count">{{ ctx.antibioticSummary.value.today || 0 }}今日新增</span>
      </div>
      <div class="antibiotic-stats">
        <span>增 {{ ctx.antibioticSummary.value.today || 0 }}</span>
        <span>减 {{ ctx.antibioticSummary.value.decrease_today || 0 }}</span>
        <span>净 {{ ctx.antibioticSummary.value.net_today || 0 }}</span>
      </div>
      <div v-if="ctx.antibioticIntensity.value.available && ctx.activeAntibioticBars.value.length" class="antibiotic-chart">
        <button
          v-for="bar in ctx.activeAntibioticBars.value"
          :key="bar.date"
          type="button"
          class="antibiotic-bar"
        >
          <i :style="{ height: `${bar.percent}%` }" />
          <span>{{ bar.date }}</span>
        </button>
      </div>
      <div v-if="ctx.antibioticTasks.value.length" class="antibiotic-tasks">
        <button
          v-for="task in ctx.antibioticTasks.value.slice(0, 4)"
          :key="`${task.hisPid}-${task.title}`"
          type="button"
          :class="['antibiotic-task', `prio-${task.priority}`]"
          @click="ctx.applySignalFilter('antibiotic')"
        >
          <strong>{{ task.patient || '患者' }}</strong>
          <span>{{ task.title }}</span>
        </button>
      </div>
      <div v-if="!ctx.antibioticIntensity.value.available" class="empty-hint">抗菌强度待同步</div>
    </section>

    <!-- 撤机评估 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label stable">撤机评估</span>
        <span class="section-count">{{ ctx.weaningLights.value.length }}人</span>
      </div>
      <div v-if="ctx.weaningLights.value.length" class="light-list">
        <button
          v-for="row in ctx.weaningLights.value"
          :key="`wean-${row.patient_id}`"
          type="button"
          class="light-row"
          @click="ctx.showVisualPatient(row, 'weaning')"
        >
          <strong>{{ row.bed || '--' }}床</strong>
          <i v-for="light in row.lights" :key="light.label" :class="light.ok ? 'ok' : 'bad'" :title="light.label" />
        </button>
      </div>
      <div v-else class="empty-hint">暂无撤机评估数据</div>
    </section>

    <!-- 转出评估 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label stable">转出评估</span>
        <span class="section-count">{{ ctx.dischargeLights.value.length }}人</span>
      </div>
      <div v-if="ctx.dischargeLights.value.length" class="light-list">
        <button
          v-for="row in ctx.dischargeLights.value"
          :key="`discharge-${row.patient_id}`"
          type="button"
          class="light-row"
          @click="ctx.showVisualPatient(row, 'discharge')"
        >
          <strong>{{ row.bed || '--' }}床</strong>
          <span class="light-percent">{{ row.percent || 0 }}%</span>
          <i v-for="light in row.lights" :key="light.label" :class="light.ok ? 'ok' : 'bad'" :title="light.label" />
        </button>
      </div>
      <div v-else class="empty-hint">暂无转出评估数据</div>
    </section>

    <!-- 抢救事件 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label danger">抢救事件</span>
        <span class="section-count">{{ ctx.rescueTimeline.value.length }}条</span>
      </div>
      <div v-if="ctx.rescueTimeline.value.length" class="rescue-list">
        <button
          v-for="item in ctx.rescueTimeline.value"
          :key="`${item.time}-${item.title}`"
          type="button"
          class="rescue-row"
          @click="ctx.applySignalFilter('rescue')"
        >
          <i class="rescue-dot" />
          <span>{{ item.title }}</span>
        </button>
      </div>
      <div v-else class="empty-hint">暂无抢救线索</div>
    </section>

    <!-- 家属沟通 -->
    <section class="task-section">
      <div class="section-header">
        <span class="section-label info">家属沟通</span>
        <span class="section-count">{{ ctx.familyCards.value.length }}张</span>
      </div>
      <div v-if="ctx.familyCards.value.length" class="family-grid">
        <button
          v-for="card in ctx.familyCards.value"
          :key="`family-${card.patient_id}`"
          type="button"
          class="family-card"
          @click="ctx.showVisualPatient(card, 'family')"
        >
          <strong>{{ card.bed || '--' }}床</strong>
          <em>{{ card.readiness || 0 }}%</em>
          <span>{{ card.task || '生成沟通卡' }}</span>
        </button>
      </div>
      <div v-else class="empty-hint">暂无沟通卡</div>
    </section>
  </div>
</template>

<script setup lang="ts">
defineProps<{ ctx: ReturnType<typeof import('../../composables/useClinicalWorkflow').useClinicalWorkflow> }>()
</script>

<style scoped>
.special-treatments {
  display: grid;
  gap: 16px;
}
.task-section {
  padding: 16px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(125, 211, 252, .14);
  background: var(--bg-surface);
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  padding: 3px 10px;
  border-radius: var(--card-radius);
}
.section-label.info { background: rgba(21,85,141,.15); color: #15558D; }
.section-label.stable { background: rgba(26,156,91,.15); color: #1A9C5B; }
.section-label.danger { background: rgba(217,52,43,.15); color: #D9342B; }
.section-count { font-size: 13px; color: var(--text-secondary); font-weight: 700; }

.antibiotic-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 12px;
}
.antibiotic-stats span {
  padding: 6px 8px;
  border-radius: var(--card-radius);
  color: var(--text-primary);
  background: rgba(14,116,144,.1);
  text-align: center;
  font-size: 12px;
  font-weight: 700;
}

.antibiotic-chart {
  height: 100px;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  align-items: end;
}
.antibiotic-bar {
  height: 100%;
  display: grid;
  align-items: end;
  gap: 4px;
  border: 0;
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
}
.antibiotic-bar i {
  width: 100%;
  min-height: 6px;
  align-self: end;
  border-radius: 999px 999px 4px 4px;
  background: var(--accent);
}
.antibiotic-bar span { font-size: 10px; }

.antibiotic-tasks { display: grid; gap: 6px; margin-top: 10px; }
.antibiotic-task {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: var(--card-radius);
  background: rgba(14,116,144,.06);
  cursor: pointer;
}
.antibiotic-task.prio-high { border-color: rgba(251,113,133,.34); }
.antibiotic-task strong, .antibiotic-task span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.antibiotic-task strong { color: var(--text-primary); }
.antibiotic-task span { color: #1A9C5B; }

.light-list { display: grid; gap: 6px; }
.light-row {
  width: 100%;
  display: grid;
  grid-template-columns: 54px repeat(5, 1fr);
  gap: 7px;
  align-items: center;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: var(--card-radius);
  padding: 9px;
  color: var(--text-primary);
  background: rgba(14,116,144,.06);
  cursor: pointer;
}
.light-row:hover { border-color: rgba(103,232,249,.32); }
.light-row strong { font-size: 12px; }
.light-percent { color: #1A9C5B; font-size: 12px; font-weight: 700; text-align: center; }
.light-row i {
  height: 14px;
  border-radius: var(--card-radius);
  background: var(--text-secondary);
}
.light-row i.ok { background: #1A9C5B; }
.light-row i.bad { background: #D9342B; }

.rescue-list { display: grid; gap: 6px; }
.rescue-row {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  padding: 6px 0;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  cursor: pointer;
  text-align: left;
}
.rescue-dot {
  width: 10px;
  height: 10px;
  border-radius: var(--card-radius);
  background: var(--accent);
}
.rescue-row span { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.family-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.family-card {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 6px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: var(--card-radius);
  padding: 10px;
  color: var(--text-primary);
  background: rgba(14,116,144,.06);
  cursor: pointer;
  text-align: left;
}
.family-card:hover { border-color: rgba(103,232,249,.32); }
.family-card strong {
  grid-column: 1 / -1;
  color: var(--text-primary);
  font-size: 12px;
}
.family-card em {
  display: grid;
  place-items: center;
  border-radius: var(--card-radius);
  color: #052e24;
  background: #1A9C5B;
  font-style: normal;
  font-size: 12px;
  font-weight: 700;
}
.family-card span {
  padding: 4px 6px;
  border-radius: var(--card-radius);
  text-align: center;
  background: rgba(14,116,144,.12);
  font-size: 11px;
}

.empty-hint {
  padding: 24px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 1024px) {
  .light-row {
    grid-template-columns: 44px repeat(5, 1fr);
    gap: 4px;
    padding: 7px;
  }
  .family-grid { grid-template-columns: 1fr; }
}
</style>
