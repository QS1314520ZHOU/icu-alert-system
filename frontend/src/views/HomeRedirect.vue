<template>
  <section class="home-redirect">
    <div class="redirect-panel">
      <div class="redirect-copy">
        <span>{{ resolving ? '正在识别角色' : '从这里开始' }}</span>
        <strong>ICU 上班第一屏</strong>
        <p>{{ hint }}</p>
      </div>
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
  padding: 24px;
}
.redirect-panel {
  width: min(780px, 100%);
  display: grid;
  gap: 18px;
  padding: 22px;
  border: 1px solid rgba(125, 211, 252, 0.16);
  border-radius: 8px;
  background: rgba(8, 24, 40, 0.82);
}
.redirect-copy {
  display: grid;
  gap: 8px;
}
.redirect-copy span,
.redirect-copy p {
  color: #93adc0;
  margin: 0;
}
.redirect-copy strong {
  color: #f8fbff;
  font-size: 26px;
}
.quick-start-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.quick-card {
  min-height: 112px;
  display: grid;
  align-content: center;
  gap: 8px;
  text-align: left;
  border: 1px solid rgba(125, 211, 252, 0.18);
  border-radius: 8px;
  background: rgba(19, 56, 80, 0.78);
  color: #e9fbff;
  padding: 16px;
  cursor: pointer;
}
.quick-card.primary {
  border-color: rgba(34, 211, 238, 0.42);
  background: linear-gradient(135deg, rgba(8, 82, 112, 0.88), rgba(19, 56, 80, 0.78));
}
.quick-card b {
  font-size: 18px;
}
.quick-card span {
  color: #a8c7d8;
  font-size: 13px;
  line-height: 1.55;
}

html[data-theme='light'] .home-redirect {
  background:
    radial-gradient(circle at 18% 6%, rgba(59, 130, 246, 0.08), transparent 28%),
    radial-gradient(circle at 86% 18%, rgba(20, 184, 166, 0.07), transparent 30%);
}
html[data-theme='light'] .redirect-panel {
  background: rgba(255, 255, 255, 0.96);
  border-color: rgba(145, 176, 199, 0.32);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.08), 0 1px 3px rgba(15, 23, 42, 0.04);
}
html[data-theme='light'] .redirect-copy span,
html[data-theme='light'] .redirect-copy p,
html[data-theme='light'] .quick-card span {
  color: #64748b;
}
html[data-theme='light'] .redirect-copy strong,
html[data-theme='light'] .quick-card b {
  color: #0f172a;
}
html[data-theme='light'] .quick-card {
  background: #f8fafc;
  border-color: rgba(37, 99, 235, 0.14);
  color: #1d4ed8;
}
html[data-theme='light'] .quick-card.primary {
  background: #eff6ff;
  border-color: rgba(37, 99, 235, 0.24);
}
@media (max-width: 700px) {
  .quick-start-grid {
    grid-template-columns: 1fr;
  }
}
</style>
