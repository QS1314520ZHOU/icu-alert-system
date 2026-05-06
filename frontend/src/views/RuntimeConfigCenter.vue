<template>
  <div class="config-page">
    <section class="config-hero">
      <div>
        <span>运行时配置中心</span>
        <h1>模块与规则配置</h1>
        <p>配置写入数据库，下一轮读取立即生效；不再依赖改 YAML 和重启服务。</p>
      </div>
      <a-button type="primary" :loading="loading" @click="loadConfig">刷新配置</a-button>
    </section>

    <section v-if="loadError" class="config-error">
      <strong>配置中心暂时没有连上后端</strong>
      <span>{{ loadError }}</span>
      <a-button size="small" type="primary" :loading="loading" @click="loadConfig">重新加载</a-button>
    </section>

    <section class="config-grid">
      <article class="config-panel module-panel">
        <div class="panel-head">
          <div>
            <span>模块开关</span>
            <strong>{{ enabledModuleCount }}/{{ modules.length }}</strong>
          </div>
          <a-button size="small" type="primary" :loading="saving.modules" @click="saveModules">保存</a-button>
        </div>
        <div class="module-list">
          <div v-for="item in modules" :key="item.key" class="module-row">
            <div>
              <strong>{{ item.name }}</strong>
              <span>{{ item.description }}</span>
            </div>
            <a-switch v-model:checked="item.enabled" checked-children="启用" un-checked-children="关闭" />
          </div>
        </div>
      </article>

      <article class="config-panel ai-panel">
        <div class="panel-head">
          <div>
          <span>AI 配置</span>
            <strong>{{ ai.enabled === false ? '已关闭' : '已启用' }}</strong>
          </div>
          <a-button size="small" type="primary" :loading="saving.ai" @click="saveAi">保存</a-button>
        </div>
        <div class="ai-form">
          <label><span>AI总开关</span><a-switch v-model:checked="ai.enabled" checked-children="启用" un-checked-children="关闭" /></label>
          <label><span>温度</span><a-input-number v-model:value="ai.temperature" :min="0" :max="2" :step="0.1" /></label>
          <label><span>最大输出长度</span><a-input-number v-model:value="ai.max_tokens" :min="128" :max="8192" /></label>
          <label><span>超时秒数</span><a-input-number v-model:value="ai.timeout" :min="5" :max="180" /></label>
        </div>
        <div class="route-form">
          <label><span>快速摘要</span><a-select v-model:value="ai.routes.fast" :options="providerOptions" allow-clear /></label>
          <label><span>医疗推理</span><a-select v-model:value="ai.routes.medical" :options="providerOptions" allow-clear /></label>
          <label><span>复杂推理</span><a-select v-model:value="ai.routes.reasoning" :options="providerOptions" allow-clear /></label>
          <label><span>长上下文</span><a-select v-model:value="ai.routes.long_context" :options="providerOptions" allow-clear /></label>
          <label><span>兜底模型</span><a-select v-model:value="ai.routes.fallback" :options="providerOptions" allow-clear /></label>
        </div>
      </article>
    </section>

    <section class="config-panel">
      <div class="panel-head">
        <div>
          <span>模型供应商池</span>
          <strong>{{ aiProviders.length }}个</strong>
        </div>
        <a-button size="small" type="primary" @click="addProvider">新增模型地址</a-button>
      </div>
      <div class="provider-list">
        <article v-for="(provider, idx) in aiProviders" :key="provider.id || idx" class="provider-card">
          <div class="provider-head">
            <a-switch v-model:checked="provider.enabled" checked-children="启用" un-checked-children="关闭" />
            <a-button size="small" danger ghost @click="removeProvider(idx)">删除</a-button>
          </div>
          <div class="provider-grid">
            <label><span>标识</span><a-input v-model:value="provider.id" placeholder="如 fast-main" /></label>
            <label><span>名称</span><a-input v-model:value="provider.name" placeholder="如 内网Qwen" /></label>
            <label><span>用途</span><a-select v-model:value="provider.purpose" :options="purposeOptions" /></label>
            <label><span>优先级</span><a-input-number v-model:value="provider.priority" :min="1" :max="999" /></label>
            <label class="wide"><span>接口地址</span><a-input v-model:value="provider.base_url" placeholder="http://host:port/v1" /></label>
            <label><span>模型名</span><a-input v-model:value="provider.model" placeholder="模型ID" /></label>
            <label class="wide"><span>接口密钥</span><a-input-password v-model:value="provider.api_key" placeholder="可留空或填密钥" /></label>
            <label><span>超时</span><a-input-number v-model:value="provider.timeout" :min="5" :max="180" /></label>
          </div>
        </article>
      </div>
    </section>

    <section class="config-panel">
      <div class="panel-head">
        <div>
          <span>预警阈值</span>
          <strong>{{ alertRules.length }}条</strong>
        </div>
        <a-input v-model:value="ruleKeyword" allow-clear placeholder="搜索规则/参数/分类" class="search-input" />
      </div>
      <div class="rule-table">
        <div class="rule-row rule-head">
          <span>启用</span><span>规则</span><span>分类</span><span>参数</span><span>条件</span><span>级别</span><span>操作</span>
        </div>
        <div v-for="rule in filteredRules" :key="rule.rule_id" class="rule-row">
          <a-switch v-model:checked="rule.enabled" />
          <a-input v-model:value="rule.name" />
          <a-input v-model:value="rule.category" />
          <a-input v-model:value="rule.parameter" />
          <div class="condition-edit">
            <a-select v-model:value="rule.condition.operator" :options="operatorOptions" />
            <a-input-number v-model:value="rule.condition.threshold" />
          </div>
          <a-select v-model:value="rule.severity" :options="severityOptions" />
          <a-button size="small" :loading="saving.rules[rule.rule_id]" @click="saveRule(rule)">保存</a-button>
        </div>
      </div>
    </section>

    <section class="config-panel">
      <div class="panel-head">
        <div>
          <span>字段映射</span>
          <strong>{{ mappings.length }}项</strong>
        </div>
        <a-button size="small" type="primary" :loading="saving.mapping" @click="saveMapping(mappingDraft)">新增/保存映射</a-button>
      </div>
      <div class="mapping-editor">
        <a-input v-model:value="mappingDraft.source_name" placeholder="来源表/来源系统，例如 bloodSugar" />
        <a-input v-model:value="mappingDraft.source_code" placeholder="来源字段/项目代码，例如 result" />
        <a-input v-model:value="mappingDraft.standard_concept" placeholder="标准概念，例如 glucose" />
        <a-input v-model:value="mappingDraft.unit" placeholder="单位，例如 mmol/L" />
        <a-input v-model:value="mappingDraft.module" placeholder="所属模块，例如 nutrition" />
        <a-switch v-model:checked="mappingDraft.enabled" checked-children="启用" un-checked-children="关闭" />
      </div>
      <div class="mapping-list">
        <button v-for="item in mappings.slice(0, 80)" :key="`${item.source_name}-${item.source_code}`" type="button" @click="editMapping(item)">
          <strong>{{ item.standard_concept || '未命名概念' }}</strong>
          <span>{{ item.source_name }} · {{ item.source_code }} · {{ item.unit || '无单位' }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Button as AButton, Input as AInput, InputNumber as AInputNumber, Select as ASelect, Switch as ASwitch, message } from 'ant-design-vue'
import { getRuntimeConfig, postRuntimeAi, postRuntimeAlertRule, postRuntimeFieldMapping, postRuntimeModules } from '../api'

const loading = ref(false)
const loadError = ref('')
const modules = ref<any[]>([])
const ai = reactive<any>({
  enabled: true,
  temperature: 0.1,
  max_tokens: 1024,
  timeout: 30,
  routes: {},
  providers: [],
})
const alertRules = ref<any[]>([])
const mappings = ref<any[]>([])
const ruleKeyword = ref('')
const saving = reactive<any>({ modules: false, ai: false, mapping: false, rules: {} })
const mappingDraft = reactive<any>({ source_name: '', source_code: '', standard_concept: '', unit: '', module: '', enabled: true })
const operatorOptions = ['>', '>=', '<', '<=', '==', '!='].map((value) => ({ label: value, value }))
const severityOptions = [
  { label: '危急', value: 'critical' },
  { label: '高危', value: 'high' },
  { label: '警告', value: 'warning' },
  { label: '信息', value: 'info' },
]
const purposeOptions = [
  { label: '快速摘要', value: 'fast' },
  { label: '医疗推理', value: 'medical' },
  { label: '复杂推理', value: 'reasoning' },
  { label: '长上下文', value: 'long_context' },
  { label: '兜底', value: 'fallback' },
]
const enabledModuleCount = computed(() => modules.value.filter((item) => item.enabled).length)
const aiProviders = computed<any[]>({
  get() {
    if (!Array.isArray(ai.providers)) ai.providers = []
    return ai.providers
  },
  set(value) {
    ai.providers = value
  },
})
const providerOptions = computed(() => aiProviders.value.map((item) => ({
  label: `${item.name || item.id || item.model || '未命名'} · ${item.model || '未填模型'}`,
  value: item.id,
})))
const filteredRules = computed(() => {
  const q = ruleKeyword.value.trim().toLowerCase()
  const rows = alertRules.value
  if (!q) return rows
  return rows.filter((rule) => JSON.stringify(rule).toLowerCase().includes(q))
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
    alertRules.value = (data.alert_rules || []).map((rule: any) => ({ ...rule, condition: rule.condition || {} }))
    mappings.value = data.field_mappings || []
  } catch (error: any) {
    const status = error?.response?.status
    if (status === 404) {
      loadError.value = '后端还没有加载配置中心接口。请重启一次后端服务，然后刷新页面。'
    } else if (status === 503) {
      loadError.value = '数据库运行时还没有就绪，请稍后重试或检查后端数据库连接。'
    } else {
      loadError.value = error?.message || '加载失败，请检查后端服务和浏览器缓存。'
    }
    message.error(loadError.value)
  } finally {
    loading.value = false
  }
}

async function saveModules() {
  saving.modules = true
  try {
    await postRuntimeModules({ modules: modules.value })
    message.success('模块开关已保存')
  } finally {
    saving.modules = false
  }
}

async function saveAi() {
  saving.ai = true
  try {
    await postRuntimeAi(ai)
    message.success('AI配置已保存，下一次调用生效')
  } finally {
    saving.ai = false
  }
}

function addProvider() {
  aiProviders.value = [
    ...aiProviders.value,
    {
      id: `model-${Date.now()}`,
      name: '新模型地址',
      purpose: 'fast',
      base_url: '',
      api_key: '',
      model: '',
      priority: 50,
      enabled: true,
      timeout: ai.timeout || 30,
      temperature: ai.temperature || 0.1,
      max_tokens: ai.max_tokens || 1024,
    },
  ]
}

function removeProvider(index: number) {
  aiProviders.value = aiProviders.value.filter((_, idx) => idx !== index)
}

async function saveRule(rule: any) {
  saving.rules[rule.rule_id] = true
  try {
    await postRuntimeAlertRule(rule.rule_id, {
      enabled: rule.enabled,
      name: rule.name,
      category: rule.category,
      parameter: rule.parameter,
      severity: rule.severity,
      condition: rule.condition || {},
    })
    message.success('预警规则已保存，下一轮扫描生效')
  } finally {
    saving.rules[rule.rule_id] = false
  }
}

function editMapping(item: any) {
  Object.assign(mappingDraft, {
    source_name: item.source_name || '',
    source_code: item.source_code || '',
    standard_concept: item.standard_concept || '',
    unit: item.unit || '',
    module: item.module || '',
    enabled: item.enabled !== false,
  })
}

async function saveMapping(payload: any) {
  saving.mapping = true
  try {
    await postRuntimeFieldMapping(payload)
    message.success('字段映射已保存')
    await loadConfig()
  } finally {
    saving.mapping = false
  }
}

onMounted(loadConfig)
</script>

<style scoped>
.config-page { display: grid; gap: 16px; padding: 18px; font-family: var(--app-display-font); }
.config-hero, .config-panel {
  border: 1px solid rgba(125,211,252,.14);
  border-radius: 22px;
  background: linear-gradient(180deg, rgba(11,31,50,.94), rgba(7,18,31,.98));
}
.config-hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
}
.config-hero span, .config-hero p, .panel-head span, .module-row span, .mapping-list span { color: #8aa4b8; }
.config-hero h1 { margin: 4px 0; color: #ecfeff; font-size: 32px; }
.config-hero p { margin: 0; }
.config-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid rgba(251,146,60,.28);
  border-radius: 18px;
  background: rgba(124,45,18,.26);
  color: #fed7aa;
}
.config-error strong { color: #fff7ed; }
.config-error span { flex: 1; }
.config-grid { display: grid; grid-template-columns: 1.15fr .85fr; gap: 16px; }
.config-panel { padding: 16px; }
.panel-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.panel-head strong { display: block; color: #ecfeff; font-size: 24px; }
.module-list, .ai-form, .mapping-list, .provider-list { display: grid; gap: 10px; }
.module-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px;
  border-radius: 14px;
  background: rgba(2,8,20,.28);
}
.module-row strong, .mapping-list strong { display: block; color: #ecfeff; }
.ai-form { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.ai-form label, .route-form label, .provider-grid label { display: grid; gap: 6px; color: #8aa4b8; }
.route-form {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(125,211,252,.12);
}
.provider-card {
  padding: 12px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 16px;
  background: rgba(2,8,20,.24);
}
.provider-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}
.provider-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}
.provider-grid .wide { grid-column: span 2; }
.search-input { max-width: 320px; }
.rule-table { display: grid; gap: 8px; overflow-x: auto; }
.rule-row {
  min-width: 980px;
  display: grid;
  grid-template-columns: 70px 1.4fr 1fr 1.1fr 1.4fr 110px 80px;
  gap: 8px;
  align-items: center;
  padding: 8px;
  border-radius: 12px;
  background: rgba(2,8,20,.24);
}
.rule-head { color: #67e8f9; font-weight: 900; background: rgba(8,47,73,.42); }
.condition-edit { display: grid; grid-template-columns: 82px 1fr; gap: 6px; }
.mapping-editor {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr)) 90px;
  gap: 8px;
  margin-bottom: 12px;
}
.mapping-list { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.mapping-list button {
  padding: 12px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 14px;
  background: rgba(2,8,20,.24);
  text-align: left;
  cursor: pointer;
}
html[data-theme='light'] .config-hero,
html[data-theme='light'] .config-panel {
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.06), transparent 34%),
    #ffffff;
  border-color: rgba(148, 163, 184, 0.24);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}
html[data-theme='light'] .config-hero {
  background:
    radial-gradient(circle at top left, rgba(59, 130, 246, 0.12), transparent 34%),
    linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
  border-color: rgba(148, 163, 184, 0.22);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}
html[data-theme='light'] .config-hero h1,
html[data-theme='light'] .panel-head strong,
html[data-theme='light'] .module-row strong,
html[data-theme='light'] .mapping-list strong { color: #0f172a; }
html[data-theme='light'] .config-hero span,
html[data-theme='light'] .config-hero p,
html[data-theme='light'] .panel-head span,
html[data-theme='light'] .module-row span,
html[data-theme='light'] .mapping-list span,
html[data-theme='light'] .ai-form label,
html[data-theme='light'] .route-form label,
html[data-theme='light'] .provider-grid label {
  color: #64748b;
}
html[data-theme='light'] .module-row,
html[data-theme='light'] .provider-card,
html[data-theme='light'] .rule-row,
html[data-theme='light'] .mapping-list button {
  background: #f8fbff;
  border: 1px solid rgba(148, 163, 184, 0.22);
}
html[data-theme='light'] .rule-head {
  color: #1d4ed8;
  background: #eff6ff;
}
html[data-theme='light'] .route-form {
  border-top-color: rgba(148, 163, 184, 0.22);
}
html[data-theme='light'] .config-error {
  background: #fff7ed;
  border-color: rgba(249, 115, 22, 0.24);
  color: #9a3412;
}
html[data-theme='light'] .config-error strong {
  color: #7c2d12;
}
@media (max-width: 1100px) {
  .config-grid, .ai-form, .route-form, .provider-grid, .mapping-editor { grid-template-columns: 1fr; }
  .provider-grid .wide { grid-column: span 1; }
  .config-hero { display: grid; }
}
</style>
