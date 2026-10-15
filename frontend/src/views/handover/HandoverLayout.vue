<template>
  <div class="handover-layout">
    <router-view />
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.handover-layout {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-page);
}
</style>
