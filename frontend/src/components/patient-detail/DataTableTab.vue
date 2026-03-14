<template>
  <a-table
    :columns="columns"
    :data-source="rows"
    size="small"
    :pagination="{ pageSize }"
    :row-key="rowKey"
  />
</template>

<script setup lang="ts">
import { Table as ATable } from 'ant-design-vue'

withDefaults(defineProps<{
  columns: any[]
  rows: any[]
  rowKey: string | ((row: any) => string)
  pageSize?: number
}>(), {
  pageSize: 8,
})
</script>
