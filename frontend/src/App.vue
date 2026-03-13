<template>
  <a-config-provider :theme="{ algorithm: darkAlgorithm }">
    <a-layout class="root">
      <a-layout-header class="hdr">
        <div class="hdr-l">
          <span class="hdr-icon">🏥</span>
          <div>
            <div class="hdr-title">ICU 智能预警系统</div>
            <div class="hdr-sub">Intelligent Early Warning System</div>
          </div>
        </div>
        <a-menu mode="horizontal" :selected-keys="[navKey]" theme="dark" class="hdr-menu"
                @click="({ key }: any) => $router.push(key === 'overview' ? '/' : '/bigscreen')">
          <a-menu-item key="overview">📋 患者总览</a-menu-item>
          <a-menu-item key="bigscreen">🖥 护士站大屏</a-menu-item>
        </a-menu>
        <span class="hdr-clock">{{ now }}</span>
      </a-layout-header>
      <a-layout-content class="body"><router-view /></a-layout-content>
    </a-layout>
  </a-config-provider>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { theme } from 'ant-design-vue'

const { darkAlgorithm } = theme
const route = useRoute()
const now = ref('')
let t: any

const navKey = computed(() => route.path.startsWith('/bigscreen') ? 'bigscreen' : 'overview')

function tick() {
  now.value = new Date().toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
onMounted(() => { tick(); t = setInterval(tick, 1000) })
onUnmounted(() => clearInterval(t))
</script>

<style scoped>
.root { min-height: 100vh; background: #0a0a14; }
.hdr {
  display: flex; align-items: center; gap: 20px;
  background: #0e0e1a !important;
  padding: 0 20px; height: 48px;
  border-bottom: 1px solid #161625;
}
.hdr-l { display: flex; align-items: center; gap: 8px; }
.hdr-icon { font-size: 20px; }
.hdr-title { font-size: 15px; font-weight: 700; color: #ddd; letter-spacing: 0.5px; line-height: 1.2; }
.hdr-sub { font-size: 9px; color: #444; letter-spacing: 0.3px; }
.hdr-menu { flex: 1; }
.hdr-clock { font-family: 'SF Mono','Consolas',monospace; color: #444; font-size: 12px; white-space: nowrap; }
.body { background: #0a0a14; min-height: calc(100vh - 48px); }
</style>