<template>
  <div class="saki-field-mapping">
    <a-button type="primary" @click="loadMappings" :loading="loading" style="margin-bottom:16px">加载映射</a-button>
    <table class="mapping-table" v-if="mappings.length">
      <thead>
        <tr><th>标准字段</th><th>医院字段</th><th>集合</th><th>单位</th><th>描述</th></tr>
      </thead>
      <tbody>
        <tr v-for="m in mappings" :key="m.standard_name">
          <td><code>{{ m.standard_name }}</code></td>
          <td>
            <a-tag v-for="f in m.hospital_fields" :key="f" style="margin:1px">{{ f }}</a-tag>
          </td>
          <td>{{ m.collection }}</td>
          <td>{{ m.unit_hint || '-' }}</td>
          <td>{{ m.description || '-' }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty-wrap">
      <EmptyState description="点击「加载映射」查看字段映射配置" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { Button as AButton, Tag as ATag } from 'ant-design-vue'
import { ref } from 'vue'
import { getFieldMappings } from '../../api/saki'
import { EmptyState } from '../../components/common/design-system'

const loading = ref(false)
const mappings = ref<any[]>([])

const loadMappings = async () => {
  loading.value = true
  try { const r = await getFieldMappings(); mappings.value = r.data || [] } catch {} finally { loading.value = false }
}
</script>

<style scoped>
.saki-field-mapping { display: flex; flex-direction: column; gap: 16px; }
.mapping-table { width: 100%; border-collapse: collapse; background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); overflow: hidden; }
.mapping-table th, .mapping-table td { border-bottom: 1px solid var(--color-divider); padding: 8px 12px; text-align: left; font-size: var(--text-table); }
.mapping-table th { background: var(--color-bg-surface-secondary); font-size: var(--text-caption); font-weight: var(--text-table-header-weight); color: var(--color-text-secondary); }
.empty-wrap { background: var(--color-bg-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
</style>
