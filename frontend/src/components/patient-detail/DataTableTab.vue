<template>
  <section class="data-table-tab">
    <header class="table-head">
      <div>
        <div class="table-title">{{ resolvedTitle }}</div>
        <div class="table-sub">{{ resolvedSubtitle }}</div>
      </div>
      <div class="table-actions">
        <label v-if="enableSearch" class="table-search">
          <span>检索</span>
          <input v-model.trim="searchText" type="text" :placeholder="searchPlaceholderText" />
        </label>
      </div>
    </header>

    <div class="table-kpis">
      <article class="table-kpi">
        <span>总记录</span>
        <strong>{{ rows.length }}</strong>
        <small>当前数据集</small>
      </article>
      <article class="table-kpi">
        <span>筛选后</span>
        <strong>{{ filteredRows.length }}</strong>
        <small>{{ searchText ? '匹配结果' : '未筛减' }}</small>
      </article>
      <article class="table-kpi">
        <span>列数</span>
        <strong>{{ normalizedColumns.length }}</strong>
        <small>结构字段</small>
      </article>
    </div>

    <div v-if="!filteredRows.length" class="table-empty">
      <strong>{{ searchText ? '没有匹配结果' : '暂无可展示数据' }}</strong>
      <span>{{ searchText ? '试试更短的关键词，或清空筛选条件。' : '上游接口返回后，这里会自动展示结构化明细。' }}</span>
    </div>

    <div v-else class="table-wrap">
      <a-table
        :columns="normalizedColumns"
        :data-source="filteredRows"
        size="small"
        :pagination="{ pageSize }"
        :row-key="rowKey"
        :scroll="{ x: true }"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Table as ATable } from 'ant-design-vue'

const props = withDefaults(defineProps<{
  columns: any[]
  rows: any[]
  rowKey: string | ((row: any) => string)
  pageSize?: number
  title?: string
  subtitle?: string
  enableSearch?: boolean
  searchPlaceholder?: string
}>(), {
  pageSize: 8,
  title: '',
  subtitle: '',
  enableSearch: true,
  searchPlaceholder: '',
})

const searchText = ref('')

const normalizedColumns = computed(() => Array.isArray(props.columns) ? props.columns : [])
const resolvedTitle = computed(() => props.title || '结构化明细表')
const resolvedSubtitle = computed(() => props.subtitle || '支持快速检索当前页字段和值，便于临床回看与质控。')
const searchPlaceholderText = computed(() => props.searchPlaceholder || '搜索任意列内容')

const searchableKeys = computed(() => normalizedColumns.value
  .map((col: any) => String(col?.dataIndex || col?.key || '').trim())
  .filter(Boolean))

const filteredRows = computed(() => {
  const rows = Array.isArray(props.rows) ? props.rows : []
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return rows
  return rows.filter((row: any) => searchableKeys.value.some((key) => String(row?.[key] ?? '').toLowerCase().includes(keyword)))
})
</script>

<style scoped>
.data-table-tab {
  display: grid;
  gap: 12px;
}
.table-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}
.table-title {
  color: var(--text-primary);
  font-size: 17px;
  font-weight: 800;
}
.table-sub {
  margin-top: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}
.table-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.table-search {
  display: grid;
  gap: 6px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.table-search input {
  min-width: 220px;
  min-height: 36px;
  padding: 0 12px;
  border-radius: var(--card-radius);
  border: 1px solid rgba(80,199,255,.16);
  background: var(--bg-surface),.78);
  color: var(--text-primary);
  outline: none;
}
.table-kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.table-kpi {
  padding: 12px;
  border-radius: var(--card-radius);
  background: var(--bg-surface), var(--bg-surface));
  border: 1px solid rgba(80,199,255,.12);
}
.table-kpi span,
.table-kpi small,
.table-empty span {
  color: var(--text-secondary);
  font-size: 12px;
}
.table-kpi strong,
.table-empty strong {
  display: block;
  margin-top: 6px;
  color: var(--text-primary);
  font-size: 22px;
  font-weight: 800;
}
.table-kpi small {
  display: block;
  margin-top: 6px;
}
.table-empty {
  display: grid;
  gap: 6px;
  padding: 22px;
  border-radius: var(--card-radius);
  border: 1px dashed rgba(80,199,255,.18);
  background: var(--bg-surface),.52);
}
.table-wrap :deep(.ant-table) {
  background: transparent;
  color: var(--text-primary);
  border: 1px solid rgba(80,199,255,.12);
  border-radius: var(--card-radius);
  overflow: hidden;
}
.table-wrap :deep(.ant-table-thead > tr > th) {
  background: var(--bg-surface),.82);
  color: var(--accent);
  border-bottom-color: rgba(80,199,255,.1);
  font-size: 12px;
  font-weight: 700;
}
.table-wrap :deep(.ant-table-tbody > tr > td) {
  background: var(--bg-surface),.6);
  color: var(--text-primary);
  border-bottom-color: rgba(80,199,255,.08);
  font-size: 12px;
}
.table-wrap :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--bg-surface),.42) !important;
}
.table-wrap :deep(.ant-pagination .ant-pagination-item),
.table-wrap :deep(.ant-pagination .ant-pagination-prev),
.table-wrap :deep(.ant-pagination .ant-pagination-next) {
  background: var(--bg-surface),.78);
  border-color: rgba(80,199,255,.14);
}
.table-wrap :deep(.ant-pagination .ant-pagination-item-active) {
  background: var(--bg-surface) 0%, rgba(7,63,86,.98) 100%);
  border-color: rgba(110,231,249,.28);
}
.table-wrap :deep(.ant-pagination .ant-pagination-item a),
.table-wrap :deep(.ant-pagination .ant-pagination-prev button),
.table-wrap :deep(.ant-pagination .ant-pagination-next button) {
  color: var(--text-primary);
}
.table-wrap :deep(.ant-pagination .ant-pagination-item-active a) {
  color: var(--text-primary);
}
@media (max-width: 920px) {
  .table-kpis {
    grid-template-columns: 1fr;
  }
  .table-search input {
    min-width: 0;
    width: 100%;
  }
}

html[data-theme='light'] .table-title { color: var(--text-secondary); }
html[data-theme='light'] .table-sub,
html[data-theme='light'] .table-kpi span,
html[data-theme='light'] .table-kpi small,
html[data-theme='light'] .table-empty span,
html[data-theme='light'] .table-search { color: var(--text-secondary); }
html[data-theme='light'] .table-search input {
  background: var(--bg-surface), rgba(247,250,253,0.98));
  color: var(--text-secondary);
  border-color: rgba(187,204,220,0.72);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .table-search input::placeholder { color: #93a5b7; }
html[data-theme='light'] .table-search input:focus {
  border-color: rgba(59,130,246,0.4);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .table-kpi,
html[data-theme='light'] .table-empty {
  background:
    var(--bg-surface), rgba(96,165,250,0) 42%),
    var(--bg-surface), rgba(243,248,253,.98));
  border-color: rgba(187,204,220,0.72);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .table-kpi strong,
html[data-theme='light'] .table-empty strong { color: var(--text-secondary); }
html[data-theme='light'] .table-wrap :deep(.ant-table) {
  color: var(--text-secondary);
  border-color: rgba(187,204,220,0.72);
  background: var(--bg-surface), rgba(248,251,255,0.98));
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .table-wrap :deep(.ant-table-container) {
  border-radius: var(--card-radius);
}
html[data-theme='light'] .table-wrap :deep(.ant-table-thead > tr > th) {
  background: var(--bg-surface);
  color: var(--text-secondary);
  border-bottom-color: rgba(187,204,220,0.72);
}
html[data-theme='light'] .table-wrap :deep(.ant-table-tbody > tr > td) { background: var(--bg-surface); color: var(--text-secondary); border-bottom-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .table-wrap :deep(.ant-table-tbody > tr:nth-child(even) > td) { background: rgba(248,251,255,0.92); }
html[data-theme='light'] .table-wrap :deep(.ant-table-tbody > tr:hover > td) { background: rgba(231,241,249,0.96) !important; }
html[data-theme='light'] .table-wrap :deep(.ant-pagination .ant-pagination-item),
html[data-theme='light'] .table-wrap :deep(.ant-pagination .ant-pagination-prev),
html[data-theme='light'] .table-wrap :deep(.ant-pagination .ant-pagination-next) {
  background: var(--bg-surface), rgba(243,248,252,0.98));
  border-color: rgba(187,204,220,0.72);
  box-shadow: var(--card-shadow);
}
html[data-theme='light'] .table-wrap :deep(.ant-pagination .ant-pagination-item-active) { background: var(--bg-surface), rgba(29,78,216,.98)); border-color: rgba(59,130,246,0.28); }
html[data-theme='light'] .table-wrap :deep(.ant-pagination .ant-pagination-item a),
html[data-theme='light'] .table-wrap :deep(.ant-pagination .ant-pagination-prev button),
html[data-theme='light'] .table-wrap :deep(.ant-pagination .ant-pagination-next button) { color: var(--text-secondary); }
html[data-theme='light'] .table-wrap :deep(.ant-pagination .ant-pagination-item-active a) { color: var(--text-primary); }
</style>
