<template>
  <div class="runtime-page">
    <header class="runtime-header">
      <div>
        <span>Runtime Config Center</span>
        <h1>配置中心</h1>
        <p>配置写入数据库后立即生效，支持版本审计、导出和回滚。</p>
      </div>
      <div class="header-actions">
        <a-button :loading="loading" @click="loadConfig">刷新</a-button>
        <a-button type="primary" @click="downloadSnapshot">导出配置</a-button>
      </div>
    </header>

    <section v-if="loadError" class="error-strip">
      <strong>配置中心暂时不可用</strong>
      <span>{{ loadError }}</span>
      <a-button size="small" type="primary" :loading="loading" @click="loadConfig">重试</a-button>
    </section>

    <nav class="runtime-tabs">
      <button v-for="tab in tabs" :key="tab.key" type="button" :class="{ active: activeTab === tab.key }" @click="activeTab = tab.key">
        <strong>{{ tab.label }}</strong>
        <span>{{ tab.hint }}</span>
      </button>
    </nav>

    <section v-if="activeTab === 'overview'" class="panel overview-panel">
      <div class="metric-grid">
        <div class="metric-card"><span>模块启用</span><strong>{{ enabledModuleCount }}/{{ modules.length }}</strong></div>
        <div class="metric-card"><span>模型供应商</span><strong>{{ enabledProviderCount }}/{{ aiProviders.length }}</strong></div>
        <div class="metric-card"><span>轨迹预测</span><strong>{{ trajectory.enabled === false ? '关闭' : '启用' }}</strong></div>
        <div class="metric-card"><span>启用规则</span><strong>{{ enabledRuleCount }}/{{ alertRules.length }}</strong></div>
        <div class="metric-card"><span>字段映射</span><strong>{{ mappings.length }}</strong></div>
      </div>
      <div class="overview-actions">
        <button v-for="tab in tabs.filter((item) => item.key !== 'overview')" :key="tab.key" type="button" @click="activeTab = tab.key">
          <strong>{{ tab.label }}</strong>
          <span>{{ tab.hint }}</span>
        </button>
      </div>
    </section>

    <section v-if="activeTab === 'modules'" class="panel">
      <div class="panel-toolbar">
        <div><h2>模块开关</h2><span>{{ enabledModuleCount }} 个已启用</span></div>
        <a-button type="primary" :loading="saving.modules" @click="saveModules">保存模块</a-button>
      </div>
      <div class="dense-table module-table">
        <div class="table-row table-head"><span>状态</span><span>模块</span><span>说明</span></div>
        <div v-for="item in modules" :key="item.key" class="table-row">
          <a-switch v-model:checked="item.enabled" />
          <strong>{{ item.name }}</strong>
          <span>{{ item.description }}</span>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'ai'" class="panel">
      <div class="panel-toolbar">
        <div><h2>模型服务</h2><span>{{ ai.enabled === false ? '总开关关闭' : '总开关启用' }}</span></div>
        <div class="toolbar-actions">
          <a-button @click="addProvider">新增 Provider</a-button>
          <a-button type="primary" :loading="saving.ai" @click="saveAi">保存模型服务</a-button>
        </div>
      </div>
      <div class="form-grid compact">
        <label><span>模型服务总开关</span><a-switch v-model:checked="ai.enabled" /></label>
        <label><span>温度</span><a-input-number v-model:value="ai.temperature" :min="0" :max="2" :step="0.1" /></label>
        <label><span>最大输出</span><a-input-number v-model:value="ai.max_tokens" :min="128" :max="8192" /></label>
        <label><span>超时秒数</span><a-input-number v-model:value="ai.timeout" :min="5" :max="180" /></label>
      </div>
      <div class="form-grid routes">
        <label><span>快速摘要</span><a-select v-model:value="ai.routes.fast" :options="providerOptions" allow-clear /></label>
        <label><span>医疗推理</span><a-select v-model:value="ai.routes.medical" :options="providerOptions" allow-clear /></label>
        <label><span>复杂推理</span><a-select v-model:value="ai.routes.reasoning" :options="providerOptions" allow-clear /></label>
        <label><span>长上下文</span><a-select v-model:value="ai.routes.long_context" :options="providerOptions" allow-clear /></label>
        <label><span>兜底模型</span><a-select v-model:value="ai.routes.fallback" :options="providerOptions" allow-clear /></label>
      </div>
      <div class="dense-table provider-table">
        <div class="table-row table-head"><span>启用</span><span>标识/名称</span><span>用途</span><span>模型</span><span>地址</span><span>优先级</span><span>操作</span></div>
        <div v-for="(provider, idx) in aiProviders" :key="provider.id || idx" class="table-row">
          <a-switch v-model:checked="provider.enabled" />
          <div class="stack"><a-input v-model:value="provider.id" placeholder="id" /><a-input v-model:value="provider.name" placeholder="名称" /></div>
          <a-select v-model:value="provider.purpose" :options="purposeOptions" />
          <a-input v-model:value="provider.model" placeholder="模型名" />
          <a-input v-model:value="provider.base_url" placeholder="http://host/v1" />
          <a-input-number v-model:value="provider.priority" :min="1" :max="999" />
          <a-button size="small" danger ghost @click="removeProvider(idx)">删除</a-button>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'trajectory'" class="panel">
      <div class="panel-toolbar">
        <div><h2>轨迹预测</h2><span>版本 {{ trajectory.version || 1 }}</span></div>
        <a-button type="primary" :loading="saving.trajectory" @click="saveTrajectory">保存轨迹配置</a-button>
      </div>
      <div class="form-grid compact">
        <label><span>轨迹预测</span><a-switch v-model:checked="trajectory.enabled" /></label>
        <label><span>前瞻告警</span><a-switch v-model:checked="trajectory.alert_enabled" /></label>
        <label><span>预测窗口(h)</span><a-input-number v-model:value="trajectory.horizon_hours" :min="1" :max="12" /></label>
        <label><span>生效范围</span><a-select v-model:value="trajectory.scope" :options="scopeOptions" /></label>
      </div>
      <div class="split-grid">
        <div class="sub-panel">
          <h3>默认展示指标</h3>
          <div class="chip-grid">
            <button v-for="item in trajectoryCodeOptions" :key="`default-${item.code}`" type="button" :class="{ active: trajectory.default_codes.includes(item.code) }" @click="toggleCode('default_codes', item.code)">
              {{ item.label || item.code }}<small>{{ item.series_type === 'discrete_trend' ? '离散' : item.requires_context?.length ? '需设备' : '连续' }}</small>
            </button>
          </div>
        </div>
        <div class="sub-panel">
          <h3>参与前瞻告警</h3>
          <div class="chip-grid">
            <button v-for="item in trajectoryAlertOptions" :key="`alert-${item.code}`" type="button" :class="{ active: trajectory.alert_codes.includes(item.code) }" @click="toggleCode('alert_codes', item.code)">
              {{ item.label || item.code }}
            </button>
          </div>
        </div>
      </div>
      <div class="panel-toolbar slim">
        <div><h3>阈值突破规则</h3><span>告警指标必须先启用展示</span></div>
        <a-button size="small" @click="addTrajectoryThreshold">新增阈值</a-button>
      </div>
      <div class="dense-table threshold-table">
        <div class="table-row table-head"><span>指标</span><span>方向</span><span>阈值</span><span>窗口</span><span>概率</span><span>级别</span><span>操作</span></div>
        <div v-for="(row, idx) in trajectory.thresholds" :key="`${row.code}-${idx}`" class="table-row">
          <a-select v-model:value="row.code" :options="trajectoryAlertSelectOptions" />
          <a-select v-model:value="row.operator" :options="thresholdOperatorOptions" />
          <a-input-number v-model:value="row.threshold" />
          <a-input-number v-model:value="row.horizon_hours" :min="1" :max="12" />
          <a-input-number v-model:value="row.probability" :min="0.01" :max="0.99" :step="0.05" />
          <a-select v-model:value="row.severity" :options="severityOptions" />
          <a-button size="small" danger ghost @click="removeTrajectoryThreshold(Number(idx))">删除</a-button>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'rules'" class="panel">
      <div class="panel-toolbar">
        <div><h2>预警规则</h2><span>{{ filteredRules.length }} / {{ alertRules.length }} 条</span></div>
      </div>
      <div class="filter-bar">
        <a-input v-model:value="ruleKeyword" allow-clear placeholder="搜索规则/参数/分类" />
        <a-select v-model:value="ruleSeverityFilter" :options="severityFilterOptions" />
        <a-select v-model:value="ruleEnabledFilter" :options="enabledFilterOptions" />
      </div>
      <div class="dense-table rule-table">
        <div class="table-row table-head"><span>启用</span><span>规则</span><span>分类</span><span>参数</span><span>条件</span><span>级别</span><span>操作</span></div>
        <div v-for="rule in filteredRules" :key="rule.rule_id" class="table-row">
          <a-switch v-model:checked="rule.enabled" />
          <a-input v-model:value="rule.name" />
          <a-input v-model:value="rule.category" />
          <a-input v-model:value="rule.parameter" />
          <div class="condition-edit"><a-select v-model:value="rule.condition.operator" :options="operatorOptions" /><a-input-number v-model:value="rule.condition.threshold" /></div>
          <a-select v-model:value="rule.severity" :options="severityOptions" />
          <a-button size="small" :loading="saving.rules[rule.rule_id]" @click="saveRule(rule)">保存</a-button>
        </div>
      </div>
    </section>

    <section v-if="activeTab === 'mapping'" class="panel">
      <div class="panel-toolbar">
        <div><h2>字段映射</h2><span>{{ filteredMappings.length }} / {{ mappings.length }} 项</span></div>
        <a-button type="primary" :loading="saving.mapping" @click="saveMapping(mappingDraft)">保存映射</a-button>
      </div>
      <div class="filter-bar">
        <a-input v-model:value="mappingKeyword" allow-clear placeholder="搜索来源/标准概念/模块" />
        <a-select v-model:value="mappingModuleFilter" :options="mappingModuleOptions" />
        <a-input v-model:value="mappingDraft.source_name" placeholder="来源表" />
        <a-input v-model:value="mappingDraft.source_code" placeholder="来源字段" />
        <a-input v-model:value="mappingDraft.standard_concept" placeholder="标准概念" />
        <a-input v-model:value="mappingDraft.unit" placeholder="单位" />
        <a-input v-model:value="mappingDraft.module" placeholder="模块" />
        <a-switch v-model:checked="mappingDraft.enabled" />
      </div>
      <div class="dense-table mapping-table">
        <div class="table-row table-head"><span>标准概念</span><span>来源</span><span>字段</span><span>单位</span><span>模块</span><span>状态</span></div>
        <button v-for="item in filteredMappings.slice(0, 180)" :key="`${item.source_name}-${item.source_code}`" type="button" class="table-row" @click="editMapping(item)">
          <strong>{{ item.standard_concept || '未命名' }}</strong><span>{{ item.source_name }}</span><span>{{ item.source_code }}</span><span>{{ item.unit || '-' }}</span><span>{{ item.module || '-' }}</span><span>{{ item.enabled === false ? '关闭' : '启用' }}</span>
        </button>
      </div>
    </section>

    <section v-if="activeTab === 'history'" class="panel">
      <div class="panel-toolbar">
        <div><h2>历史审计</h2><span>{{ historyRows.length }} 条版本记录</span></div>
        <div class="toolbar-actions">
          <a-select v-model:value="historyKey" :options="historyKeyOptions" />
          <a-button :loading="loadingHistory" @click="loadHistory">刷新历史</a-button>
          <a-button type="primary" @click="downloadSnapshot">导出当前</a-button>
        </div>
      </div>
      <div class="dense-table history-table">
        <div class="table-row table-head"><span>Key</span><span>版本</span><span>操作</span><span>操作者</span><span>时间</span><span>说明</span><span>回滚</span></div>
        <div v-for="row in historyRows" :key="row._id || `${row.key}-${row.version}`" class="table-row">
          <strong>{{ row.key }}</strong><span>v{{ row.version }}</span><span>{{ row.action || 'update' }}</span><span>{{ row.actor || '-' }}</span><span>{{ formatTime(row.created_at) }}</span><span>{{ row.reason || '-' }}</span>
          <a-button size="small" danger ghost @click="rollbackConfig(row)">回滚</a-button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Button as AButton, Input as AInput, InputNumber as AInputNumber, Select as ASelect, Switch as ASwitch, message, Modal } from 'ant-design-vue'
import { getRuntimeConfig, getRuntimeConfigExport, getRuntimeConfigHistory, postRuntimeAi, postRuntimeAlertRule, postRuntimeConfigRollback, postRuntimeFieldMapping, postRuntimeModules, postRuntimeTrajectoryForecast } from '../api'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const loading = ref(false)
const loadingHistory = ref(false)
const loadError = ref('')
const activeTab = ref('overview')
const modules = ref<any[]>([])
const ai = reactive<any>({ enabled: true, temperature: 0.1, max_tokens: 1024, timeout: 30, routes: {}, providers: [] })
const trajectory = reactive<any>({ enabled: true, default_codes: ['HR', 'MAP', 'SBP', 'DBP', 'SpO2', 'RR', 'Temp', 'EtCO2'], alert_enabled: false, alert_codes: ['MAP', 'SpO2', 'RR', 'Temp', 'EtCO2'], horizon_hours: 6, scope: 'global', version: 1, thresholds: [] })
const trajectoryCodeOptions = ref<any[]>([])
const alertRules = ref<any[]>([])
const mappings = ref<any[]>([])
const historyRows = ref<any[]>([])
const ruleKeyword = ref('')
const ruleSeverityFilter = ref('all')
const ruleEnabledFilter = ref('all')
const mappingKeyword = ref('')
const mappingModuleFilter = ref('respiratory')
const historyKey = ref('all')
const saving = reactive<any>({ modules: false, ai: false, trajectory: false, mapping: false, rules: {} })
const mappingDraft = reactive<any>({ source_name: '', source_code: '', standard_concept: '', unit: '', module: '', enabled: true })

const tabs = [
  { key: 'overview', label: '总览', hint: '健康度' },
  { key: 'modules', label: '模块', hint: '功能开关' },
  { key: 'ai', label: '模型服务', hint: '路由与供应商' },
  { key: 'trajectory', label: '轨迹预测', hint: '模型告警' },
  { key: 'rules', label: '预警规则', hint: '阈值' },
  { key: 'mapping', label: '字段映射', hint: '标准化' },
  { key: 'history', label: '历史审计', hint: '回滚' },
]
const operatorOptions = ['>', '>=', '<', '<=', '==', '!='].map((value) => ({ label: value, value }))
const thresholdOperatorOptions = ['<', '<=', '>', '>='].map((value) => ({ label: value, value }))
const severityOptions = [{ label: '危急', value: 'critical' }, { label: '高危', value: 'high' }, { label: '警告', value: 'warning' }, { label: '信息', value: 'info' }]
const severityFilterOptions = [{ label: '全部级别', value: 'all' }, ...severityOptions]
const enabledFilterOptions = [{ label: '全部状态', value: 'all' }, { label: '已启用', value: 'enabled' }, { label: '已关闭', value: 'disabled' }]
const purposeOptions = [{ label: '快速摘要', value: 'fast' }, { label: '医疗推理', value: 'medical' }, { label: '复杂推理', value: 'reasoning' }, { label: '长上下文', value: 'long_context' }, { label: '兜底', value: 'fallback' }]
const scopeOptions = [{ label: '全院默认', value: 'global' }, { label: '科室覆盖', value: 'unit' }, { label: '患者覆盖', value: 'patient' }]
const historyKeyOptions = [{ label: '全部配置', value: 'all' }, { label: '模块', value: 'modules' }, { label: '模型服务', value: 'ai' }, { label: '轨迹预测', value: 'trajectory_forecast' }]
const adminPayload = computed(() => ({ actor: auth.userName || auth.userId || 'admin', role: 'admin' }))
const enabledModuleCount = computed(() => modules.value.filter((item) => item.enabled).length)
const aiProviders = computed<any[]>({ get: () => (Array.isArray(ai.providers) ? ai.providers : (ai.providers = [])), set: (value) => { ai.providers = value } })
const enabledProviderCount = computed(() => aiProviders.value.filter((item) => item.enabled !== false).length)
const enabledRuleCount = computed(() => alertRules.value.filter((item) => item.enabled !== false).length)
const providerOptions = computed(() => aiProviders.value.map((item) => ({ label: `${item.name || item.id || item.model || '未命名'} · ${item.model || '未填模型'}`, value: item.id })))
const trajectoryAlertOptions = computed(() => trajectoryCodeOptions.value.filter((item) => trajectory.default_codes.includes(item.code) && item.series_type !== 'discrete_trend'))
const trajectoryAlertSelectOptions = computed(() => trajectoryAlertOptions.value.map((item) => ({ label: `${item.label || item.code} (${item.code})`, value: item.code })))
const filteredRules = computed(() => {
  const q = ruleKeyword.value.trim().toLowerCase()
  return alertRules.value.filter((rule) => {
    if (q && !JSON.stringify(rule).toLowerCase().includes(q)) return false
    if (ruleSeverityFilter.value !== 'all' && rule.severity !== ruleSeverityFilter.value) return false
    if (ruleEnabledFilter.value === 'enabled' && rule.enabled === false) return false
    if (ruleEnabledFilter.value === 'disabled' && rule.enabled !== false) return false
    return true
  })
})
const filteredMappings = computed(() => {
  const q = mappingKeyword.value.trim().toLowerCase()
  return mappings.value.filter((item) => {
    if (mappingModuleFilter.value !== 'all' && item.module !== mappingModuleFilter.value) return false
    if (q && !JSON.stringify(item).toLowerCase().includes(q)) return false
    return true
  })
})
const mappingModuleOptions = computed(() => {
  const modules = Array.from(new Set(mappings.value.map((item) => item.module).filter(Boolean))).sort()
  return [{ label: '全部模块', value: 'all' }, ...modules.map((item) => ({ label: item === 'respiratory' ? '呼吸/通气参数' : item, value: item }))]
})

async function loadConfig() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await getRuntimeConfig()
    modules.value = data.modules || []
    Object.assign(ai, data.ai || {})
    if (!ai.routes) ai.routes = {}
    if (!Array.isArray(ai.providers)) ai.providers = []
    Object.assign(trajectory, data.trajectory_forecast || {})
    if (!Array.isArray(trajectory.default_codes)) trajectory.default_codes = []
    if (!Array.isArray(trajectory.alert_codes)) trajectory.alert_codes = []
    if (!Array.isArray(trajectory.thresholds)) trajectory.thresholds = []
    trajectoryCodeOptions.value = data.trajectory_code_options || []
    alertRules.value = (data.alert_rules || []).map((rule: any) => ({ ...rule, condition: rule.condition || {} }))
    mappings.value = data.field_mappings || []
    if (activeTab.value === 'history') await loadHistory()
  } catch (error: any) {
    loadError.value = error?.response?.data?.detail || error?.message || '加载失败，请检查后端服务。'
    message.error(loadError.value)
  } finally {
    loading.value = false
  }
}

function toggleCode(field: 'default_codes' | 'alert_codes', code: string) {
  const set = new Set(trajectory[field] || [])
  set.has(code) ? set.delete(code) : set.add(code)
  trajectory[field] = Array.from(set)
  if (field === 'default_codes') {
    trajectory.alert_codes = (trajectory.alert_codes || []).filter((item: string) => trajectory.default_codes.includes(item))
    trajectory.thresholds = (trajectory.thresholds || []).filter((item: any) => trajectory.alert_codes.includes(item.code))
  }
}
function addTrajectoryThreshold() {
  const code = trajectory.alert_codes?.[0] || 'MAP'
  trajectory.thresholds = [...(trajectory.thresholds || []), { code, operator: code === 'SpO2' || code === 'MAP' ? '<' : '>', threshold: code === 'MAP' ? 65 : code === 'SpO2' ? 90 : 30, horizon_hours: 4, probability: 0.7, severity: 'warning' }]
}
function removeTrajectoryThreshold(index: number) { trajectory.thresholds = trajectory.thresholds.filter((_: any, idx: number) => idx !== index) }
async function saveModules() { saving.modules = true; try { await postRuntimeModules({ modules: modules.value, ...adminPayload.value }); message.success('模块开关已保存'); await loadHistory() } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || '保存失败') } finally { saving.modules = false } }
async function saveAi() { saving.ai = true; try { await postRuntimeAi({ ...ai, ...adminPayload.value }); message.success('模型服务配置已保存'); await loadHistory() } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || '保存失败') } finally { saving.ai = false } }
async function saveTrajectory() { saving.trajectory = true; try { const payload = { ...trajectory, ...adminPayload.value, alert_codes: (trajectory.alert_codes || []).filter((code: string) => (trajectory.default_codes || []).includes(code)), thresholds: (trajectory.thresholds || []).filter((row: any) => (trajectory.alert_codes || []).includes(row.code)), expected_version: trajectory.version || 1 }; const { data } = await postRuntimeTrajectoryForecast(payload); Object.assign(trajectory, data.trajectory_forecast || trajectory); message.success(`轨迹配置已保存，版本 ${data.effective_version || trajectory.version}`); await loadHistory() } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || '保存失败') } finally { saving.trajectory = false } }
function addProvider() { aiProviders.value = [...aiProviders.value, { id: `model-${Date.now()}`, name: '新模型地址', purpose: 'fast', base_url: '', api_key: '', model: '', priority: 50, enabled: true, timeout: ai.timeout || 30, temperature: ai.temperature || 0.1, max_tokens: ai.max_tokens || 1024 }] }
function removeProvider(index: number) { aiProviders.value = aiProviders.value.filter((_, idx) => idx !== index) }
async function saveRule(rule: any) { saving.rules[rule.rule_id] = true; try { await postRuntimeAlertRule(rule.rule_id, { enabled: rule.enabled, name: rule.name, category: rule.category, parameter: rule.parameter, severity: rule.severity, condition: rule.condition || {} }); message.success('预警规则已保存') } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || '保存失败') } finally { saving.rules[rule.rule_id] = false } }
function editMapping(item: any) { Object.assign(mappingDraft, { source_name: item.source_name || '', source_code: item.source_code || '', standard_concept: item.standard_concept || '', unit: item.unit || '', module: item.module || '', enabled: item.enabled !== false }) }
async function saveMapping(payload: any) { saving.mapping = true; try { await postRuntimeFieldMapping(payload); message.success('字段映射已保存'); await loadConfig() } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || '保存失败') } finally { saving.mapping = false } }
async function loadHistory() { loadingHistory.value = true; try { const { data } = await getRuntimeConfigHistory({ key: historyKey.value === 'all' ? undefined : historyKey.value, limit: 80 }); historyRows.value = data.items || [] } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || '历史加载失败') } finally { loadingHistory.value = false } }
async function downloadSnapshot() { try { const { data } = await getRuntimeConfigExport(); const text = JSON.stringify(data.snapshot || {}, null, 2); const blob = new Blob([text], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = `runtime-config-${Date.now()}.json`; a.click(); URL.revokeObjectURL(url) } catch (e: any) { message.error(e?.response?.data?.detail || e?.message || '导出失败') } }
function rollbackConfig(row: any) { Modal.confirm({ title: `回滚 ${row.key} 到 v${row.version}?`, content: '回滚会生成新的配置版本，并立即影响后续运行时读取。', okText: '确认回滚', okType: 'danger', cancelText: '取消', async onOk() { await postRuntimeConfigRollback(row.key, { version: row.version, reason: `UI rollback to v${row.version}`, ...adminPayload.value }); message.success('已回滚'); await loadConfig(); await loadHistory() } }) }
function formatTime(value: any) { return value ? new Date(value).toLocaleString() : '-' }

onMounted(() => { Promise.all([loadConfig(), loadHistory()]) })
</script>

<style scoped>
.runtime-page { display: grid; gap: 12px; padding: 14px; font-family: var(--app-display-font); }
.runtime-header, .panel, .runtime-tabs, .error-strip { border: 1px solid rgba(125,211,252,.14); background: rgba(7,18,31,.92); border-radius: 4px; }
.runtime-header { display: flex; justify-content: space-between; gap: 16px; padding: 16px; }
.runtime-header span, .runtime-header p, .panel-toolbar span, .metric-card span, .table-row span, .sub-panel h3 { color: #8aa4b8; }
.runtime-header h1 { margin: 2px 0; color: #ecfeff; font-size: 26px; }
.runtime-header p { margin: 0; }
.header-actions, .toolbar-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.runtime-tabs { display: flex; gap: 6px; padding: 6px; overflow-x: auto; }
.runtime-tabs button { min-width: 120px; border: 1px solid transparent; border-radius: 4px; background: transparent; color: #9cc7d8; padding: 8px 10px; text-align: left; cursor: pointer; }
.runtime-tabs button strong { display: block; color: #dff7ff; }
.runtime-tabs button span { font-size: 11px; }
.runtime-tabs button.active { background: rgba(34,211,238,.16); border-color: rgba(103,232,249,.28); }
.panel { padding: 14px; display: grid; gap: 12px; }
.panel-toolbar { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.panel-toolbar h2, .panel-toolbar h3 { margin: 0; color: #ecfeff; }
.panel-toolbar.slim { margin-top: 4px; }
.metric-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.metric-card, .sub-panel { border: 1px solid rgba(125,211,252,.12); border-radius: 4px; background: rgba(2,8,20,.26); padding: 12px; }
.metric-card strong { display: block; color: #ecfeff; font-size: 24px; }
.overview-actions { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; }
.overview-actions button { text-align: left; border: 1px solid rgba(125,211,252,.12); border-radius: 4px; background: rgba(2,8,20,.22); color: #dff7ff; padding: 12px; cursor: pointer; }
.overview-actions span, .chip-grid small { display: block; color: #8aa4b8; font-size: 11px; }
.dense-table { display: grid; gap: 6px; overflow-x: auto; }
.table-row { display: grid; gap: 8px; align-items: center; min-width: 980px; padding: 8px; border-radius: 4px; background: rgba(2,8,20,.22); border: 1px solid rgba(125,211,252,.08); color: #dff7ff; }
.table-head { color: #67e8f9; font-weight: 900; background: rgba(8,47,73,.45); }
.module-table .table-row { grid-template-columns: 90px 220px 1fr; }
.provider-table .table-row { grid-template-columns: 70px 210px 130px 180px 1fr 90px 80px; }
.threshold-table .table-row { grid-template-columns: 1.2fr .8fr 1fr .8fr 1fr 1fr .8fr; }
.rule-table .table-row { grid-template-columns: 70px 1.4fr 1fr 1fr 1.4fr 110px 80px; }
.mapping-table .table-row { grid-template-columns: 1.2fr 1fr 1fr .7fr .8fr .6fr; text-align: left; cursor: pointer; }
.history-table .table-row { grid-template-columns: 1fr .6fr 1fr 1fr 1.4fr 1.2fr .7fr; }
.form-grid, .filter-bar { display: grid; gap: 8px; }
.form-grid.compact { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.form-grid.routes { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.form-grid label { display: grid; gap: 5px; color: #8aa4b8; }
.filter-bar { grid-template-columns: repeat(6, minmax(0, 1fr)); }
.split-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.chip-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.chip-grid button { min-height: 32px; padding: 0 10px; border-radius: 999px; border: 1px solid rgba(125,211,252,.16); background: rgba(2,8,20,.3); color: #dff7ff; cursor: pointer; }
.chip-grid button.active { background: rgba(34,211,238,.16); border-color: rgba(103,232,249,.38); color: #ecfeff; }
.stack { display: grid; gap: 6px; }
.condition-edit { display: grid; grid-template-columns: 82px 1fr; gap: 6px; }
.error-strip { display: flex; align-items: center; gap: 10px; padding: 10px 12px; color: #fed7aa; border-color: rgba(251,146,60,.28); background: rgba(124,45,18,.24); }
.error-strip span { flex: 1; }
html[data-theme='light'] .runtime-header, html[data-theme='light'] .panel, html[data-theme='light'] .runtime-tabs { background: #FFFFFF; border-color: rgba(148,163,184,.24); }
html[data-theme='light'] .runtime-header h1, html[data-theme='light'] .panel-toolbar h2, html[data-theme='light'] .panel-toolbar h3, html[data-theme='light'] .metric-card strong, html[data-theme='light'] .runtime-tabs button strong { color: #1D2129; }
html[data-theme='light'] .runtime-header span, html[data-theme='light'] .runtime-header p, html[data-theme='light'] .panel-toolbar span, html[data-theme='light'] .metric-card span, html[data-theme='light'] .table-row span, html[data-theme='light'] .sub-panel h3 { color: #4E5969; }
html[data-theme='light'] .table-row, html[data-theme='light'] .metric-card, html[data-theme='light'] .sub-panel, html[data-theme='light'] .overview-actions button, html[data-theme='light'] .chip-grid button { background: #FFFFFF; border-color: rgba(148,163,184,.22); color: #1D2129; }
html[data-theme='light'] .table-head, html[data-theme='light'] .runtime-tabs button.active { background: #eff6ff; color: #15558D; }
@media (max-width: 1100px) {
  .runtime-header, .panel-toolbar { display: grid; }
  .metric-grid, .form-grid.compact, .form-grid.routes, .filter-bar, .split-grid { grid-template-columns: 1fr; }
}
</style>
