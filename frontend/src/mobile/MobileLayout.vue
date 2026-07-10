<template>
  <section class="mobile-shell">
    <header class="mobile-topbar">
      <div class="mobile-topbar__title">
        <span class="mobile-kicker">{{ containerLabel }}</span>
        <strong>{{ title }}</strong>
      </div>
      <div class="mobile-topbar__meta">
        <select :value="selectedDeptKey" aria-label="切换科室" @change="onDeptChange">
          <option v-if="!departments.length" value="current">{{ shell.deptLabel.value }}</option>
          <option v-for="dept in departments" :key="deptKey(dept)" :value="deptKey(dept)">
            {{ deptName(dept) }}
          </option>
        </select>
        <button type="button" @click="refreshPage">刷新</button>
      </div>
    </header>

    <main class="mobile-main">
      <router-view />
    </main>

    <nav class="mobile-tabbar" aria-label="移动端导航">
      <button
        v-for="item in navItems"
        :key="item.key"
        type="button"
        :class="['mobile-tab', { active: activeKey === item.key }]"
        @click="go(item.path)"
      >
        <span>{{ item.icon }}</span>
        <b>{{ item.label }}</b>
      </button>
    </nav>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { completeMobileReviewReminder, postAlertAcknowledge, postMobileAlertSbar, postMobileOrderStubs, postMobileReviewReminder } from '../api'
import { useMobileShell } from '../composables/useMobileShell'
import { createMobileQueueReplayer, registerMobileNotifications } from './mobileOfflineQueue'
import { visibleMobileNavItems, type MobileNavItem } from './mobileNav'
import type { MobileNavKey } from './types'

const route = useRoute()
const router = useRouter()
const shell = useMobileShell()
let stopReplay: (() => void) | null = null

const title = computed(() => String(route.meta?.title || 'ICU移动工作台'))
const navItems = computed<MobileNavItem[]>(() => visibleMobileNavItems(shell.role.value))
const departments = computed(() => shell.departments.value)
const selectedDeptKey = computed(() => {
  const code = shell.deptCode.value
  const dept = shell.deptLabel.value
  if (!code && (!dept || dept === '全院')) return 'current'
  return code || dept
})
const containerLabel = computed(() => {
  const map: Record<string, string> = { browser: 'H5', pwa: 'PWA', wechat: '企业微信', dingtalk: '钉钉' }
  return map[shell.container.value] || 'H5'
})
const activeKey = computed<MobileNavKey>(() => {
  if (route.path.startsWith('/m/patients') || route.path.startsWith('/m/patient/')) return 'patients'
  if (route.path.startsWith('/m/alerts')) return 'alerts'
  if (route.path.startsWith('/m/tasks')) return 'tasks'
  if (route.path.startsWith('/m/consult')) return 'consult'
  if (route.path.startsWith('/m/me')) return 'me'
  return 'home'
})

function go(path: string) {
  router.push({ path, query: shell.identityQuery() })
}

function refreshPage() {
  window.dispatchEvent(new CustomEvent('mobile:refresh'))
}

function deptKey(dept: any) {
  return String(dept?.deptCode || dept?.code || dept?.dept || dept?.name || '').trim()
}

function deptName(dept: any) {
  return String(dept?.dept || dept?.name || '未命名科室').trim()
}

function onDeptChange(event: Event) {
  const value = String((event.target as HTMLSelectElement).value || '')
  if (value === 'current') return
  const hit = departments.value.find((item: any) => deptKey(item) === value)
  if (!hit) return
  router.replace({ path: route.path, query: shell.setDepartment(hit) })
}

async function replayQueuedAction(item: any) {
  const payload = item.payload || {}
  const alertId = payload.alertId || payload.alert_id
  if (item.type === 'alert_ack' && alertId) await postAlertAcknowledge(alertId, payload.body || payload)
  else if (item.type === 'mobile_sbar' && alertId) await postMobileAlertSbar(alertId, payload.body || payload)
  else if (item.type === 'order_stub' && alertId) await postMobileOrderStubs(alertId, payload.body || payload)
  else if (item.type === 'review_reminder' && alertId) await postMobileReviewReminder(alertId, payload.body || payload)
  else if (item.type === 'review_complete' && payload.id) await completeMobileReviewReminder(payload.id, payload.body || payload)
}

onMounted(() => {
  registerMobileNotifications()
  stopReplay = createMobileQueueReplayer(replayQueuedAction)
})

onUnmounted(() => {
  stopReplay?.()
})
</script>
