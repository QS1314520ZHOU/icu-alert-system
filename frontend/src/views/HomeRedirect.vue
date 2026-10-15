<template>
  <section class="home-redirect">
    <div class="redirect-panel">
      <PageHeader title="ICU 上班第一屏" :subtitle="hint">
        <template #actions>
          <span class="redirect-status">{{ resolving ? '正在识别角色' : '从这里开始' }}</span>
        </template>
      </PageHeader>
      <div class="quick-start-grid">
        <button type="button" class="quick-card primary" @click="goDoctor">
          <b>我是医生</b>
          <span>看今日重点患者、待办和病历文书</span>
        </button>
        <button type="button" class="quick-card primary" @click="goNurse">
          <b>我是护士</b>
          <span>看本班床位、提醒和交班单</span>
        </button>
        <button type="button" class="quick-card" @click="goOverview">
          <b>查看床位总览</b>
          <span>先从全科患者列表进入详情</span>
        </button>
        <button type="button" class="quick-card" @click="goBigscreen">
          <b>护士站大屏</b>
          <span>适合交班、巡视和全科风险展示</span>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getClinicalAccount } from '../api'
import { useAuthStore } from '../stores/auth'
import { PageHeader } from '../components/common/design-system'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const resolving = ref(false)
const userId = computed(() => String(auth.effectiveUserId || '').trim())
const hint = computed(() =>
  userId.value
    ? `当前账号：${userId.value}。识别成功后会自动进入对应首页。`
    : '未带账号参数，请直接选择角色或查看床位总览。',
)

function push(path: string, extraQuery: Record<string, any> = {}) {
  router.replace({ path, query: { ...auth.cleanIdentityQuery(route.query), ...extraQuery } })
}
function goDoctor() { push('/doctor-home', { role: route.query.role || 'doctor' }) }
function goNurse() { push('/nurse-home', { role: route.query.role || 'nurse' }) }
function goOverview() { push('/patients') }
function goBigscreen() { push('/bigscreen') }

onMounted(async () => {
  auth.hydrateFromQuery(route.query)
  if (!userId.value) return
  resolving.value = true
  try {
    const deptCode = String(route.query.deptCode || route.query.dept_code || auth.deptCode || '').trim()
    const dept = String(route.query.dept || route.query.department || auth.dept || '').trim()
    const role = String(route.query.role || route.query.userRole || auth.role || '').trim()
    const { data } = await getClinicalAccount({
      userName: userId.value,
      deptCode: deptCode || undefined,
      dept_code: deptCode || undefined,
      dept: dept || undefined,
      role: role || undefined,
    })
    auth.updateAccount(data?.account)
    const resolvedRole = String(data?.account?.role || role || '').toLowerCase()
    if (['head_nurse', 'charge_nurse'].includes(resolvedRole)) push('/head-nurse-home')
    else if (resolvedRole === 'director') push('/director-home')
    else if (resolvedRole === 'nurse') push('/nurse-home')
    else if (resolvedRole === 'doctor') push('/doctor-home')
  } catch {
    // Keep quick-start choices visible.
  } finally {
    resolving.value = false
  }
})
</script>

<style scoped>
.home-redirect {
  min-height: calc(100vh - 128px);
  display: grid;
  place-items: center;
  padding: var(--space-6, 24px);
  background: var(--color-bg-page);
}

.redirect-panel {
  width: min(780px, 100%);
  display: grid;
  gap: 0;
  padding: var(--space-6, 24px);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
}

.redirect-status {
  font-size: var(--text-caption);
  font-weight: var(--weight-medium);
  color: var(--color-text-secondary);
}

.quick-start-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--element-gap-lg, 12px);
}

.quick-card {
  min-height: 112px;
  display: grid;
  align-content: center;
  gap: var(--space-2, 8px);
  text-align: left;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-bg-surface);
  color: var(--color-text-primary);
  padding: var(--space-4, 16px);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.quick-card:hover {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.quick-card.primary {
  border-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.quick-card b {
  font-size: var(--text-section-title);
  font-weight: var(--weight-semibold);
  color: var(--color-text-primary);
}

.quick-card span {
  color: var(--color-text-secondary);
  font-size: var(--text-body);
  line-height: var(--text-body-line-height);
}

@media (max-width: 700px) {
  .quick-start-grid {
    grid-template-columns: 1fr;
  }
}
</style>
