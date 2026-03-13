<template>
  <div class="bigscreen">
    <div class="screen-header">
      <h1>ICU 护士站监控大屏</h1>
      <span class="screen-time">{{ currentTime }}</span>
    </div>
    <div class="screen-body">
      <p style="text-align: center; color: #8899aa; padding-top: 200px; font-size: 24px;">
        大屏模块开发中...
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import dayjs from 'dayjs'

const currentTime = ref(dayjs().format('YYYY-MM-DD HH:mm:ss'))
let timer: number

onMounted(() => {
  timer = window.setInterval(() => {
    currentTime.value = dayjs().format('YYYY-MM-DD HH:mm:ss')
  }, 1000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.bigscreen {
  min-height: 100vh;
  background: #050d1a;
}
.screen-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 32px;
  background: linear-gradient(90deg, #0d2137, #0a1929);
  border-bottom: 2px solid #1890ff;
}
.screen-header h1 {
  color: #1890ff;
  font-size: 24px;
  letter-spacing: 4px;
}
.screen-time {
  color: #8899aa;
  font-family: 'Courier New', monospace;
  font-size: 18px;
}
</style>
