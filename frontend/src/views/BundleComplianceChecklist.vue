<template>
  <section class="bundle-compliance">
    <div class="bundle-header">
      <div>
        <strong>Bundle 合规核查</strong>
        <span>{{ summary?.date || '--' }} · {{ summary?.patient_count || 0 }} 名患者</span>
      </div>
      <div class="header-right">
        <span class="overall-score" :class="summary?.overall_tone || 'red'">
          综合 {{ summary?.overall_score || 0 }}%
        </span>
        <button type="button" @click="load" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div v-if="loading && !summary" class="loading">正在计算 Bundle 合规评分...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="summary">
      <!-- Bundle 概览卡片 -->
      <div class="bundle-cards">
        <div
          v-for="bundle in bundleList"
          :key="bundle.code"
          class="bundle-card"
          :class="bundle.tone"
          @click="selectedBundle = selectedBundle === bundle.code ? null : bundle.code"
        >
          <div class="card-top">
            <strong>{{ bundle.name }}</strong>
            <span class="score" :class="bundle.tone">{{ bundle.avg_compliance }}%</span>
          </div>
          <div class="card-bottom">
            <span>{{ bundle.fully_compliant }}/{{ bundle.applicable_patients }} 全合规</span>
            <span class="expand-icon">{{ selectedBundle === bundle.code ? '▲' : '▼' }}</span>
          </div>
        </div>
      </div>

      <!-- 展开的条目明细 -->
      <div v-if="selectedBundle && selectedBundleData" class="bundle-detail">
        <div class="detail-header">
          <strong>{{ selectedBundleData.name }} 条目明细</strong>
        </div>
        <div class="item-list">
          <div
            v-for="(item, idx) in selectedBundleData.items"
            :key="idx"
            class="item-row"
            :class="itemTone(item)"
          >
            <div class="item-name">{{ item.name }}</div>
            <div class="item-bar">
              <div class="bar-track">
                <div class="bar-fill" :class="itemTone(item)" :style="{ width: `${item.rate || 0}%` }"></div>
              </div>
            </div>
            <div class="item-stats">
              <span class="rate" :class="itemTone(item)">{{ item.rate || 0 }}%</span>
              <span class="detail">{{ item.compliant || 0 }}/{{ item.applicable || 0 }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 趋势说明 -->
      <div class="bundle-note">
        <span>基于评估提醒、床旁评分、护理记录、用药执行和告警记录综合判定</span>
        <span>数据每小时自动更新</span>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { getBundleCompliance } from '../api'

const props = defineProps<{
  deptCode?: string
  dept?: string
}>()

const loading = ref(false)
const error = ref('')
const summary = ref<any>(null)
const selectedBundle = ref<string | null>(null)

const bundleList = computed(() => {
  const bundles = summary.value?.bundles || {}
  return ['abcdef', 'vap', 'clabsi', 'cauti']
    .map(code => bundles[code])
    .filter(Boolean)
})

const selectedBundleData = computed(() => {
  if (!selectedBundle.value) return null
  return summary.value?.bundles?.[selectedBundle.value] || null
})

function itemTone(item: any) {
  const rate = item.rate || 0
  if (rate >= 80) return 'green'
  if (rate >= 60) return 'yellow'
  return 'red'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const params: any = {}
    if (props.deptCode) params.dept_code = props.deptCode
    else if (props.dept) params.dept = props.dept
    const { data } = await getBundleCompliance(params)
    summary.value = data?.data || {}
  } catch (err: any) {
    error.value = err?.message || 'Bundle 合规数据加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => { void load() })
watch(() => [props.deptCode, props.dept], () => { void load() })
</script>

<style scoped>
.bundle-compliance {
  display: grid;
  gap: 12px;
}

.bundle-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.bundle-header strong {
  color: var(--text-primary);
  font-size: 15px;
}

.bundle-header span {
  color: var(--text-secondary);
  font-size: 12px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.overall-score {
  font-size: 18px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: var(--card-radius);
}

.overall-score.green { color: var(--chart-2); background: rgba(52, 211, 153, .15); }
.overall-score.yellow { color: var(--warning); background: rgba(251, 191, 36, .15); }
.overall-score.red { color: var(--danger); background: rgba(239, 68, 68, .15); }

button {
  min-height: 32px;
  padding: 0 10px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(125, 211, 252, .2);
  background: var(--bg-surface), .78);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 12px;
}

button:disabled { opacity: .6; cursor: not-allowed; }

.loading, .error {
  padding: 16px;
  text-align: center;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .58);
  color: var(--text-secondary);
}

.error { color: var(--danger-soft); }

.bundle-cards {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.bundle-card {
  padding: 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .74);
  border: 1px solid rgba(125, 211, 252, .14);
  cursor: pointer;
  transition: border-color .2s;
}

.bundle-card.green { border-color: rgba(52, 211, 153, .34); }
.bundle-card.yellow { border-color: rgba(245, 158, 11, .42); }
.bundle-card.red { border-color: rgba(239, 68, 68, .42); }

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.card-top strong {
  color: var(--text-primary);
  font-size: 13px;
}

.score {
  font-size: 20px;
  font-weight: 700;
}

.score.green { color: var(--chart-2); }
.score.yellow { color: var(--warning); }
.score.red { color: var(--danger); }

.card-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-bottom span {
  color: var(--text-secondary);
  font-size: 11px;
}

.expand-icon {
  color: var(--text-secondary);
  font-size: 10px;
}

.bundle-detail {
  background: var(--bg-surface), .74);
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: var(--card-radius);
  padding: 12px;
}

.detail-header {
  margin-bottom: 10px;
}

.detail-header strong {
  color: var(--text-primary);
  font-size: 14px;
}

.item-list {
  display: grid;
  gap: 8px;
}

.item-row {
  display: grid;
  grid-template-columns: 140px 1fr 80px;
  gap: 10px;
  align-items: center;
  padding: 8px 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .72);
}

.item-row.green { border-left: 3px solid #34d399; }
.item-row.yellow { border-left: 3px solid #fbbf24; }
.item-row.red { border-left: 3px solid #ef4444; }

.item-name {
  color: var(--text-primary);
  font-size: 12px;
}

.bar-track {
  height: 8px;
  border-radius: var(--card-radius);
  background: rgba(148, 163, 184, .15);
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: var(--card-radius);
  transition: width .3s ease;
}

.bar-fill.green { background: var(--chart-2); }
.bar-fill.yellow { background: var(--warning); }
.bar-fill.red { background: var(--danger); }

.item-stats {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.rate {
  font-size: 14px;
  font-weight: 600;
}

.rate.green { color: var(--chart-2); }
.rate.yellow { color: var(--warning); }
.rate.red { color: var(--danger); }

.detail {
  color: var(--text-secondary);
  font-size: 10px;
}

.bundle-note {
  display: flex;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), .4);
}

.bundle-note span {
  color: var(--text-secondary);
  font-size: 10px;
}

/* Light theme */
html[data-theme='light'] .bundle-header strong,
html[data-theme='light'] .card-top strong,
html[data-theme='light'] .detail-header strong,
html[data-theme='light'] .item-name {
  color: var(--text-primary);
}

html[data-theme='light'] .bundle-card,
html[data-theme='light'] .bundle-detail {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
}

html[data-theme='light'] .item-row {
  background: var(--bg-surface);
}

html[data-theme='light'] .loading,
html[data-theme='light'] .error {
  background: var(--bg-surface);
  color: var(--text-secondary);
}

html[data-theme='light'] .error { color: var(--danger); }

html[data-theme='light'] button {
  background: var(--bg-surface);
  border-color: rgba(37, 99, 235, 0.18);
  color: var(--brand);
}
</style>
