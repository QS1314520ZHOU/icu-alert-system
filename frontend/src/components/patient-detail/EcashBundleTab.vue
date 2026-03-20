<template>
  <section class="bundle-tab">
    <div class="bundle-hero">
      <div>
        <div class="bundle-title">eCASH / ABCDEF 解放束</div>
        <div class="bundle-sub">围绕镇痛、镇静、谵妄与自主唤醒试验形成床旁可执行视图。</div>
      </div>
      <div class="bundle-score-box">
        <span>解放束状态</span>
        <strong>{{ bundleScore }}</strong>
      </div>
    </div>

    <div v-if="bundleLights.length" class="bundle-light-row">
      <div v-for="light in bundleLights" :key="light.key" :class="['bundle-light', `bundle-light--${light.state}`]">
        <span class="bundle-light-key">{{ light.key }}</span>
        <div>
          <strong>{{ light.name }}</strong>
          <div>{{ light.status }}</div>
        </div>
      </div>
    </div>

    <div class="domain-grid">
      <article class="domain-card">
        <div class="domain-title">镇痛</div>
        <div class="domain-main">{{ analgesiaCard.main }}</div>
        <div class="domain-meta">{{ analgesiaCard.meta }}</div>
        <div v-if="analgesiaCard.chips.length" class="domain-chip-row">
          <span v-for="(chip, idx) in analgesiaCard.chips" :key="`an-${idx}`" class="domain-chip">{{ chip }}</span>
        </div>
      </article>
      <article class="domain-card">
        <div class="domain-title">镇静 / 自主唤醒试验</div>
        <div class="domain-main">{{ sedationCard.main }}</div>
        <div class="domain-meta">{{ sedationCard.meta }}</div>
        <div v-if="sedationCard.chips.length" class="domain-chip-row">
          <span v-for="(chip, idx) in sedationCard.chips" :key="`se-${idx}`" class="domain-chip">{{ chip }}</span>
        </div>
      </article>
      <article class="domain-card">
        <div class="domain-title">谵妄</div>
        <div class="domain-main">{{ deliriumCard.main }}</div>
        <div class="domain-meta">{{ deliriumCard.meta }}</div>
        <div v-if="deliriumCard.chips.length" class="domain-chip-row">
          <span v-for="(chip, idx) in deliriumCard.chips" :key="`de-${idx}`" class="domain-chip">{{ chip }}</span>
        </div>
      </article>
    </div>

    <div class="bundle-list-head">
      <div>
        <div class="bundle-list-title">相关预警</div>
        <div class="bundle-list-sub">最近与解放束相关的镇痛、镇静、谵妄和自主唤醒试验提示</div>
      </div>
      <div class="bundle-list-count">{{ alerts.length }} 条</div>
    </div>

    <div v-if="alerts.length" class="bundle-alert-list">
      <article v-for="(item, idx) in alerts.slice(0, 8)" :key="item._id || idx" class="bundle-alert-card">
        <div class="bundle-alert-head">
          <strong>{{ item.name || alertTypeText(item.alert_type) || '解放束预警' }}</strong>
          <span>{{ fmtTime(item.created_at) || '时间未知' }}</span>
        </div>
        <div class="bundle-alert-main">{{ item.explanation?.summary || item.explanation?.text || item.extra?.suggestion || '暂无结构化说明' }}</div>
        <div v-if="item.explanation?.suggestion || item.extra?.suggestion" class="bundle-alert-foot">
          建议：{{ item.explanation?.suggestion || item.extra?.suggestion }}
        </div>
      </article>
    </div>
    <div v-else class="bundle-empty">暂无 eCASH / ABCDEF 解放束相关预警</div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ alerts: Array<any>; bundleAlert: any; fmtTime: (v: any) => string; alertTypeText: (v: any) => string }>()
const bundleExtra = computed(() => props.bundleAlert?.extra || {})
const bundleScore = computed(() => { const compliance = bundleExtra.value?.compliance; return compliance != null ? `${compliance}/6` : '待评估' })
const bundleLights = computed(() => { const lights = bundleExtra.value?.lights || {}; const map: Record<string, string> = { green: '通过', yellow: '提醒', red: '未完成' }; return ['A', 'B', 'C', 'D', 'E', 'F'].map((key) => ({ key, name: ({ A: '镇痛', B: '呼吸', C: '镇静选择', D: '谵妄', E: '早期活动', F: '家属参与' } as Record<string, string>)[key], state: lights?.[key] || 'neutral', status: map[lights?.[key]] || '未记录' })) })
function pickCard(keywords: string[], fallbackTitle: string) { const match = props.alerts.find((row) => { const text = `${String(row?.alert_type || '')} ${String(row?.name || '')}`.toLowerCase(); return keywords.some((key) => text.includes(key)) }); return { main: match?.name || `${fallbackTitle} 暂无异常提醒`, meta: match ? (props.fmtTime(match.created_at) || '最近一条') : '当前无相关活跃提示', chips: Array.isArray(match?.explanation?.evidence) ? match.explanation.evidence.slice(0, 3) : (match?.extra?.current_sedatives || match?.extra?.current_analgesics || []).slice(0, 3) } }
const analgesiaCard = computed(() => pickCard(['pain', 'analges', 'opioid'], '镇痛评估'))
const sedationCard = computed(() => pickCard(['rass', 'sat', 'sedation'], '镇静与自主唤醒试验'))
const deliriumCard = computed(() => pickCard(['delirium'], '谵妄筛查'))
</script>

<style scoped>
.bundle-tab { display: grid; gap: 14px; }
.bundle-hero,.bundle-list-head { display: flex; justify-content: space-between; gap: 14px; align-items: flex-start; flex-wrap: wrap; }
.bundle-title { color: #effcff; font-size: 22px; font-weight: 800; }
.bundle-sub,.bundle-list-sub,.domain-meta,.bundle-alert-head span { color: #8bb2c4; font-size: 12px; }
.bundle-score-box { min-width: 110px; padding: 12px 14px; border-radius: 16px; border: 1px solid rgba(52, 211, 153, 0.22); background: rgba(6, 34, 32, 0.82); color: #bbf7d0; }
.bundle-score-box span { display: block; font-size: 11px; }
.bundle-score-box strong { font-size: 22px; }
.bundle-light-row,.domain-grid,.bundle-alert-list { display: grid; gap: 12px; }
.bundle-light-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.domain-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.bundle-alert-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.bundle-light,.domain-card,.bundle-alert-card { padding: 14px; border-radius: 16px; border: 1px solid rgba(125, 211, 252, 0.12); background: linear-gradient(180deg, rgba(10, 28, 43, 0.94), rgba(7, 18, 32, 0.98)); }
.bundle-light { display: flex; gap: 12px; align-items: center; }
.bundle-light-key { width: 34px; height: 34px; border-radius: 12px; display: grid; place-items: center; font-weight: 800; background: rgba(14, 47, 67, 0.8); color: #d8f5ff; }
.bundle-light--green { border-color: rgba(52, 211, 153, 0.22); }
.bundle-light--yellow { border-color: rgba(251, 191, 36, 0.22); }
.bundle-light--red { border-color: rgba(251, 113, 133, 0.22); }
.domain-title,.bundle-list-title { color: #dffbff; font-size: 15px; font-weight: 800; }
.domain-main,.bundle-alert-main { margin-top: 10px; color: #f2fbff; line-height: 1.6; }
.domain-chip-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.domain-chip,.bundle-list-count { padding: 6px 10px; border-radius: 999px; background: rgba(12, 36, 56, 0.92); color: #bcecff; font-size: 12px; border: 1px solid rgba(125, 211, 252, 0.12); }
.bundle-alert-head { display: flex; justify-content: space-between; gap: 12px; }
.bundle-alert-head strong { color: #effcff; }
.bundle-alert-foot { margin-top: 10px; color: #7dd3fc; font-size: 12px; }
.bundle-empty { padding: 24px; border-radius: 16px; text-align: center; color: #8bb2c4; border: 1px dashed rgba(125, 211, 252, 0.2); }
@media (max-width: 960px) { .bundle-light-row,.domain-grid,.bundle-alert-list { grid-template-columns: 1fr; } }
</style>


