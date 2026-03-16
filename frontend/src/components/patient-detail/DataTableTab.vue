<template>
  <div class="data-table-tab">
    <a-table
      :columns="columns"
      :data-source="rows"
      size="small"
      :pagination="{ pageSize }"
      :row-key="rowKey"
    />
  </div>
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

<style scoped>
.data-table-tab :deep(.ant-table) {
  background: transparent;
  color: #dffbff;
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 12px;
  overflow: hidden;
}
.data-table-tab :deep(.ant-table-thead > tr > th) {
  background: rgba(8,28,44,.82);
  color: #7ccfe4;
  border-bottom-color: rgba(80,199,255,.1);
  font-size: 12px;
  font-weight: 700;
}
.data-table-tab :deep(.ant-table-tbody > tr > td) {
  background: rgba(7,20,34,.6);
  color: #e3fbff;
  border-bottom-color: rgba(80,199,255,.08);
  font-size: 12px;
}
.data-table-tab :deep(.ant-table-tbody > tr:hover > td) {
  background: rgba(11,42,63,.42) !important;
}
.data-table-tab :deep(.ant-pagination .ant-pagination-item),
.data-table-tab :deep(.ant-pagination .ant-pagination-prev),
.data-table-tab :deep(.ant-pagination .ant-pagination-next) {
  background: rgba(8,28,44,.78);
  border-color: rgba(80,199,255,.14);
}
.data-table-tab :deep(.ant-pagination .ant-pagination-item-active) {
  background: linear-gradient(180deg, rgba(11,107,137,.96) 0%, rgba(7,63,86,.98) 100%);
  border-color: rgba(110,231,249,.28);
}
.data-table-tab :deep(.ant-pagination .ant-pagination-item a),
.data-table-tab :deep(.ant-pagination .ant-pagination-prev button),
.data-table-tab :deep(.ant-pagination .ant-pagination-next button) {
  color: #dffbff;
}
.data-table-tab :deep(.ant-pagination .ant-pagination-item-active a) {
  color: #effcff;
}
</style>
