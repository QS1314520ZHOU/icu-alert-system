<template>
  <div class="filter-bar">
    <div class="filter-bar__search">
      <slot name="search" />
    </div>
    <div class="filter-bar__filters">
      <slot />
    </div>
    <div v-if="$slots.actions" class="filter-bar__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
// FilterBar 用于搜索和筛选区域
</script>

<style scoped>
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 0;
  flex-wrap: wrap;
}

.filter-bar__search {
  flex: 1;
  min-width: 200px;
  max-width: 400px;
}

.filter-bar__filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-bar__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

@media (max-width: 768px) {
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-bar__search {
    max-width: none;
  }

  .filter-bar__filters {
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 8px;
  }

  .filter-bar__actions {
    margin-left: 0;
    justify-content: flex-end;
  }
}
</style>
