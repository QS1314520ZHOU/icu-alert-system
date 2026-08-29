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
    <div v-else class="empty">点击"加载映射"查看字段映射配置</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { getFieldMappings } from '../../api/saki'

const loading = ref(false)
const mappings = ref<any[]>([])

const loadMappings = async () => {
  loading.value = true
  try { const r = await getFieldMappings(); mappings.value = r.data || [] } catch {} finally { loading.value = false }
}
</script>

<style scoped>
.saki-field-mapping { display: flex; flex-direction: column; gap: 16px; }
.mapping-table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; }
.mapping-table th, .mapping-table td { border: 1px solid #f0f0f0; padding: 8px 12px; text-align: left; font-size: 13px; }
.mapping-table th { background: #fafafa; font-weight: 600; }
.empty { text-align: center; padding: 60px; color: #bbb; background: #fff; border-radius: 8px; }
</style>
