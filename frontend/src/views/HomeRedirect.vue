<template>
  <section class="home-redirect">
    <div class="redirect-panel">
      <span>正在识别角色</span>
      <strong>准备进入专属首页</strong>
      <p>{{ hint }}</p>
      <div class="actions">
        <button type="button" @click="goDoctor">医生首页</button>
        <button type="button" @click="goNurse">护士首页</button>
        <button type="button" @click="goOverview">床位总览</button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getClinicalAccount } from '../api'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const userId = computed(() => String(auth.effectiveUserId || '').trim())
const hint = computed(() => userId.value ? `当前账号：${userId.value}` : '未带账号参数，保留手动入口。')

function push(path: string) {
  router.replace({ path, query: auth.cleanIdentityQuery(route.query) })
}
function goDoctor() { push('/doctor-home') }
function goNurse() { push('/nurse-home') }
function goOverview() { push('/patients') }

onMounted(async () => {
  auth.hydrateFromQuery(route.query)
  if (!userId.value) return
  try {
    const { data } = await getClinicalAccount({ userName: userId.value })
    auth.updateAccount(data?.account)
    const role = String(data?.account?.role || route.query.role || '').toLowerCase()
    if (['nurse', 'head_nurse', 'charge_nurse'].includes(role)) {
      push('/nurse-home')
    } else if (['doctor', 'director'].includes(role)) {
      push('/doctor-home')
    }
  } catch {
    // keep manual role choices visible
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
  width: min(520px, 100%);
  display: grid;
  gap: 10px;
  padding: 18px;
  border: 1px solid rgba(125, 211, 252, 0.16);
  border-radius: 8px;
  background: rgba(8, 24, 40, 0.76);
}
.redirect-panel span,
.redirect-panel p { color: #93adc0; margin: 0; }
.redirect-panel strong { color: #f8fbff; font-size: 20px; }
.actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
.actions button {
  min-height: 44px;
  border: 1px solid rgba(125, 211, 252, 0.22);
  border-radius: 8px;
  background: rgba(19, 56, 80, 0.78);
  color: #e9fbff;
  padding: 0 14px;
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
html[data-theme='light'] .redirect-panel span,
html[data-theme='light'] .redirect-panel p {
  color: #64748b;
}
html[data-theme='light'] .redirect-panel strong {
  color: #0f172a;
}
html[data-theme='light'] .actions button {
  background: #eff6ff;
  border-color: rgba(37, 99, 235, 0.2);
  color: #1d4ed8;
}
html[data-theme='light'] .actions button:hover {
  background: #dbeafe;
  border-color: rgba(37, 99, 235, 0.32);
}
</style>
