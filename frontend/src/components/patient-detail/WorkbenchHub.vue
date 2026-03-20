<template>
  <section class="workbench-shell">
    <div class="workbench-head">
      <div>
        <div class="workbench-kicker">患者工作台</div>
        <h3 class="workbench-title">专题工作台</h3>
        <p class="workbench-sub">把 eCASH、ICU 获得性衰弱、肺栓塞、阈值审核、相似病例和智能运行状态都放到一个可见入口里。</p>
      </div>
      <div :class="['runtime-pill', `runtime-pill--${runtime.level}`]">
        <span class="runtime-pill-dot"></span>
        <strong>{{ runtime.text }}</strong>
      </div>
    </div>

    <div class="workbench-grid">
      <button
        v-for="topic in topics"
        :key="topic.key"
        type="button"
        :class="['topic-card', `topic-card--${topic.tone || 'neutral'}`]"
        @click="onOpen(topic.tabKey)"
      >
        <div class="topic-card-head">
          <div>
            <div class="topic-card-title">{{ topic.title }}</div>
            <div class="topic-card-sub">{{ topic.subtitle }}</div>
          </div>
          <span class="topic-card-count">{{ topic.countText || '专题' }}</span>
        </div>
        <div class="topic-card-main">{{ topic.status }}</div>
        <div class="topic-card-meta">{{ topic.meta }}</div>
        <div v-if="topic.items?.length" class="topic-chip-row">
          <span v-for="(item, idx) in topic.items" :key="`${topic.key}-${idx}`" class="topic-chip">{{ item }}</span>
        </div>
      </button>
    </div>

    <div class="ops-grid">
      <article class="ops-card ops-card--runtime">
        <div class="ops-title-row">
          <span class="ops-kicker">智能运行态</span>
          <strong>大模型运行态</strong>
        </div>
        <div class="ops-main">{{ runtime.detail || '当前智能服务运行平稳。' }}</div>
        <div v-if="runtime.pills?.length" class="ops-chip-row">
          <span v-for="(pill, idx) in runtime.pills" :key="`runtime-${idx}`" class="ops-chip">{{ pill }}</span>
        </div>
      </article>

      <article class="ops-card ops-card--similar">
        <div class="ops-title-row">
          <span class="ops-kicker">相似病例</span>
          <strong>{{ similar.title }}</strong>
        </div>
        <div class="ops-main">{{ similar.detail }}</div>
        <div v-if="similar.bullets?.length" class="ops-bullet-row">
          <span v-for="(item, idx) in similar.bullets" :key="`similar-${idx}`" class="ops-bullet">{{ item }}</span>
        </div>
        <button type="button" class="ops-link" @click="onOpen('similar')">查看相似病例复盘</button>
      </article>

      <article class="ops-card ops-card--threshold">
        <div class="ops-title-row">
          <span class="ops-kicker">阈值审核</span>
          <strong>{{ threshold.title }}</strong>
        </div>
        <div class="ops-main">{{ threshold.detail }}</div>
        <div class="ops-chip-row">
          <span class="ops-chip">状态 {{ threshold.status || '待生成' }}</span>
          <span v-if="threshold.reviewer" class="ops-chip">审核人 {{ threshold.reviewer }}</span>
        </div>
        <div v-if="threshold.comment" class="ops-foot">{{ threshold.comment }}</div>
        <button type="button" class="ops-link" @click="onOpen('alerts')">查看预警与审核</button>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  topics: Array<any>
  runtime: any
  similar: any
  threshold: any
  onOpen: (tabKey: string) => void
}>()
</script>

<style scoped>
.workbench-shell { display: grid; gap: 14px; padding: 18px; border-radius: 22px; border: 1px solid rgba(71, 145, 191, 0.18); background: radial-gradient(circle at top right, rgba(32, 86, 129, 0.24), transparent 36%), linear-gradient(160deg, rgba(8, 24, 39, 0.98) 0%, rgba(6, 17, 30, 0.98) 58%, rgba(4, 12, 24, 0.99) 100%); box-shadow: inset 0 1px 0 rgba(194, 236, 255, 0.05); }
.workbench-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; flex-wrap: wrap; }
.workbench-kicker,.ops-kicker { color: #6ee7f9; font-size: 11px; letter-spacing: 0.22em; text-transform: uppercase; }
.workbench-title { margin: 6px 0 0; color: #effcff; font-size: 22px; font-weight: 800; }
.workbench-sub { margin: 8px 0 0; color: #8ab5ca; font-size: 13px; max-width: 720px; }
.runtime-pill { display: inline-flex; align-items: center; gap: 10px; padding: 10px 14px; border-radius: 999px; border: 1px solid rgba(93, 226, 231, 0.2); color: #dffcff; background: rgba(7, 42, 58, 0.54); }
.runtime-pill-dot { width: 9px; height: 9px; border-radius: 50%; background: currentColor; box-shadow: 0 0 16px currentColor; }
.runtime-pill--green { color: #34d399; }
.runtime-pill--yellow { color: #fbbf24; }
.runtime-pill--red { color: #fb7185; }
.runtime-pill--cyan { color: #67e8f9; }
.workbench-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.topic-card { padding: 16px; border-radius: 18px; border: 1px solid rgba(110, 231, 249, 0.12); background: linear-gradient(180deg, rgba(10, 31, 50, 0.92), rgba(8, 21, 36, 0.98)); text-align: left; color: inherit; cursor: pointer; transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease; }
.topic-card:hover { transform: translateY(-2px); border-color: rgba(125, 211, 252, 0.34); box-shadow: 0 10px 24px rgba(3, 10, 20, 0.22); }
.topic-card--emerald { border-color: rgba(52, 211, 153, 0.2); }
.topic-card--amber { border-color: rgba(251, 191, 36, 0.2); }
.topic-card--rose { border-color: rgba(251, 113, 133, 0.2); }
.topic-card--cyan { border-color: rgba(103, 232, 249, 0.2); }
.topic-card--violet { border-color: rgba(167, 139, 250, 0.22); }
.topic-card--neutral { border-color: rgba(148, 163, 184, 0.18); }
.topic-card-head,.ops-title-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.topic-card-title { color: #effcff; font-size: 16px; font-weight: 800; }
.topic-card-sub,.topic-card-meta,.ops-foot { color: #86aabd; font-size: 12px; }
.topic-card-main,.ops-main { margin-top: 10px; color: #e8fbff; font-size: 14px; line-height: 1.75; }
.topic-card-count { padding: 4px 8px; border-radius: 999px; background: rgba(10, 61, 87, 0.54); color: #9be7ff; font-size: 11px; white-space: nowrap; }
.topic-chip-row,.ops-chip-row,.ops-bullet-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.topic-chip,.ops-chip,.ops-bullet { min-height: 30px; padding: 0 12px; border-radius: 999px; border: 1px solid rgba(125, 211, 252, 0.14); color: #d8f5ff; background: rgba(13, 35, 54, 0.92); font-size: 12px; line-height: 1.4; display: inline-flex; align-items: center; }
.ops-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.ops-card { padding: 16px; border-radius: 18px; border: 1px solid rgba(93, 226, 231, 0.12); background: linear-gradient(180deg, rgba(8, 28, 43, 0.94), rgba(5, 19, 32, 0.98)); }
.ops-card strong { color: #effcff; font-size: 15px; }
.ops-link { margin-top: 14px; border: none; background: transparent; color: #7dd3fc; cursor: pointer; padding: 0; font-size: 13px; letter-spacing: .04em; }
@media (max-width: 1100px) { .workbench-grid,.ops-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 720px) { .workbench-grid,.ops-grid { grid-template-columns: 1fr; } .workbench-shell { padding: 14px; } }
</style>





