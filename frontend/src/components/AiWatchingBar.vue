<template>
  <div class="ai-watching-shell">
    <div class="ai-watching-bar" @click="toggleExpand">
      <div class="watching-icon">
        <span class="pulse-dot"></span>
        <span>预警</span>
      </div>
      <div class="watching-track">
        <transition name="watching-fade" mode="out-in">
          <div :key="activeSlide" class="watching-text">{{ visibleSlides[activeSlide] }}</div>
        </transition>
      </div>
      <span v-if="!compact && data?.findings?.length" class="watching-badge">{{ data.findings.length }}</span>
    </div>

    <transition name="watching-expand">
      <div v-if="!compact && expanded" class="watching-panel">
        <div class="watching-stats">
          <div v-for="item in statRows" :key="item.label">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <div v-if="data?.findings?.length" class="watching-findings">
          <article v-for="item in data.findings" :key="item.key">
            <div class="finding-headline">{{ item.headline }}</div>
            <button type="button" @click.stop="goDeep(item)">去查看</button>
          </article>
        </div>
        <div class="watching-saved">
          系统累计复核约 <strong>{{ Number(data?.saved_minutes_estimate || 0).toFixed(0) }}</strong> 分钟
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getAiWatching } from '../api'

const props = withDefaults(defineProps<{
  patientId: string
  compact?: boolean
}>(), {
  compact: false,
})

const router = useRouter()
const data = ref<any>(null)
const expanded = ref(false)
const activeSlide = ref(0)
let refreshTimer: number | null = null
let slideTimer: number | null = null

const visibleSlides = computed(() => {
  const stats = data.value?.stats || {}
  const first = `过去 1 小时系统复核 ${stats.labs_reviewed || 0} 项化验、${stats.drugs_reviewed || 0} 条医嘱、${stats.imaging_reports_reviewed || 0} 份影像报告`
  if (props.compact) return [first]
  const slides = [first]
  const findings = data.value?.findings || []
  if (findings.length) {
    slides.push(`发现 ${findings.length} 个值得关注的点：${findings.map((x: any) => x.headline).slice(0, 2).join(' / ')}`)
  }
  slides.push(`为你节省约 ${Number(data.value?.saved_minutes_estimate || 0).toFixed(0)} 分钟`)
  return slides
})

const statRows = computed(() => {
  const s = data.value?.stats || {}
  return [
    { label: 'Scanner', value: s.scanner_runs || 0 },
    { label: '化验', value: s.labs_reviewed || 0 },
    { label: '医嘱', value: s.drugs_reviewed || 0 },
    { label: '影像', value: s.imaging_reports_reviewed || 0 },
    { label: '触发预警', value: s.alerts_triggered || 0 },
    { label: '危急', value: s.alerts_critical || 0 },
  ]
})

function toggleExpand() {
  if (!props.compact) expanded.value = !expanded.value
}

function goDeep(item: any) {
  if (item?.deep_link) router.push(item.deep_link)
}

async function load() {
  if (!props.patientId) return
  try {
    const res = await getAiWatching(props.patientId, 1)
    data.value = res.data || null
    activeSlide.value = 0
  } catch {
    data.value = {
      stats: { scanner_runs: 0, labs_reviewed: 0, drugs_reviewed: 0, imaging_reports_reviewed: 0, alerts_triggered: 0, alerts_critical: 0 },
      findings: [],
      saved_minutes_estimate: 0,
    }
  }
}

function startTimers() {
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (slideTimer) window.clearInterval(slideTimer)
  refreshTimer = window.setInterval(load, 60000)
  slideTimer = window.setInterval(() => {
    const count = visibleSlides.value.length || 1
    activeSlide.value = (activeSlide.value + 1) % count
  }, 4000)
}

watch(() => props.patientId, () => {
  void load()
}, { immediate: true })

onMounted(startTimers)
onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
  if (slideTimer) window.clearInterval(slideTimer)
})
</script>

<style scoped>
.ai-watching-shell {
  position: relative;
  display: grid;
  gap: 8px;
  min-width: 0;
}
.ai-watching-bar {
  min-height: 36px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 6px 10px;
  border-radius: 4px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background: #FFFFFF;
  color: #dffbff;
  cursor: pointer;
}
.watching-icon {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(103, 232, 249, 0.16);
  background: rgba(8, 40, 58, 0.86);
  color: #67e8f9;
  font-size: 11px;
  font-weight: 900;
}
.pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22d3ee;
  box-shadow: 0 0 0 rgba(34, 211, 238, 0.55);
  animation: watching-pulse 1.7s infinite;
}
.watching-track {
  min-width: 0;
  overflow: hidden;
}
.watching-text {
  color: #bfeaf3;
  font-size: 12px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.watching-badge {
  min-width: 22px;
  height: 22px;
  border-radius: 999px;
  background: rgba(251, 90, 122, 0.18);
  border: 1px solid rgba(251, 90, 122, 0.24);
  color: #fda4af;
  text-align: center;
  line-height: 20px;
  font-size: 11px;
  font-weight: 900;
}
.watching-panel {
  border-radius: 4px;
  border: 1px solid rgba(80, 199, 255, 0.14);
  background: #FFFFFF;
  padding: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,.06);
}
.watching-stats {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}
.watching-stats div {
  display: grid;
  gap: 4px;
  padding: 8px;
  border-radius: 9px;
  border: 1px solid rgba(80, 199, 255, 0.1);
  background: rgba(8, 31, 47, 0.72);
}
.watching-stats span {
  color: #7ecce1;
  font-size: 10px;
}
.watching-stats strong {
  color: #effcff;
  font-size: 16px;
}
.watching-findings {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}
.watching-findings article {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  padding: 9px 10px;
  border-radius: 9px;
  background: rgba(8, 31, 47, 0.72);
  border: 1px solid rgba(80, 199, 255, 0.1);
}
.finding-headline {
  color: #dffbff;
  font-size: 12px;
  line-height: 1.5;
}
.watching-findings button {
  min-height: 28px;
  border-radius: 4px;
  border: 1px solid rgba(34, 211, 238, 0.28);
  background: rgba(8, 145, 178, 0.18);
  color: #a5f3fc;
  cursor: pointer;
  white-space: nowrap;
}
.watching-saved {
  margin-top: 10px;
  color: #9cc9d8;
  font-size: 12px;
}
.watching-saved strong {
  color: #67e8f9;
}
.watching-fade-enter-active,
.watching-fade-leave-active,
.watching-expand-enter-active,
.watching-expand-leave-active {
  transition: all 0.2s ease;
}
.watching-fade-enter-from,
.watching-fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
.watching-expand-enter-from,
.watching-expand-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
@keyframes watching-pulse {
  0% { box-shadow: 0 0 0 0 rgba(34, 211, 238, 0.42); }
  70% { box-shadow: 0 0 0 7px rgba(34, 211, 238, 0); }
  100% { box-shadow: 0 0 0 0 rgba(34, 211, 238, 0); }
}
html[data-theme='light'] .ai-watching-bar,
html[data-theme='light'] .watching-panel,
html[data-theme='light'] .watching-stats div,
html[data-theme='light'] .watching-findings article {
  background: #ffffff;
  border-color: rgba(0, 0, 0, 0.06);
  box-shadow: none;
}
html[data-theme='light'] .watching-text,
html[data-theme='light'] .finding-headline,
html[data-theme='light'] .watching-stats strong {
  color: #0f172a;
}
html[data-theme='light'] .watching-icon {
  background: #eff6ff;
  border-color: rgba(37, 99, 235, 0.16);
  color: #15558D;
}
@media (max-width: 860px) {
  .watching-stats {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
