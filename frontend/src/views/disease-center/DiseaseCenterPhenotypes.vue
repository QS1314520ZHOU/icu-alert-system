<template>
  <div class="phenotypes-page">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar__left">
        <select v-model="selectedDisease" class="filter-select">
          <option value="">全部病种</option>
          <option v-for="d in diseases" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
        <select v-model="selectedStatus" class="filter-select">
          <option value="">全部状态</option>
          <option value="active">已启用</option>
          <option value="draft">草稿</option>
          <option value="disabled">已禁用</option>
        </select>
      </div>
      <div class="toolbar__right">
        <button class="btn btn--outline" @click="loadRules">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
          刷新
        </button>
        <button class="btn btn--primary" @click="createRule">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建规则
        </button>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="content-grid">
      <!-- 左栏：规则列表 -->
      <div class="panel panel--list">
        <div class="panel__header">
          <h3 class="panel__title">表型规则</h3>
          <span class="panel__count">{{ rules.length }} 条</span>
        </div>
        <div class="panel__body">
          <div v-if="loading" class="loading-state">
            <div class="spinner"></div>
            <span>加载中...</span>
          </div>
          <div v-else-if="rules.length === 0" class="empty-state">
            <span class="empty-icon">🧬</span>
            <span class="empty-text">暂无表型规则</span>
          </div>
          <div v-else class="rule-list">
            <div
              v-for="rule in rules"
              :key="rule.id"
              :class="['rule-card', { 'rule-card--active': selectedRule?.id === rule.id }]"
              @click="selectRule(rule)"
            >
              <div class="rule-card__header">
                <span class="rule-card__name">{{ rule.name }}</span>
                <span :class="['status-badge', `status-badge--${rule.status}`]">{{ statusText(rule.status) }}</span>
              </div>
              <div class="rule-card__meta">
                <span v-if="rule.disease_name" class="meta-tag">{{ rule.disease_name }}</span>
                <span class="meta-version">{{ rule.version }}</span>
              </div>
              <div v-if="rule.dsl" class="rule-card__preview">
                <span class="preview-op">{{ rule.dsl.operator }}</span>
                <span class="preview-count">{{ rule.dsl.conditions?.length || 0 }} 个条件</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右栏：规则编辑器 -->
      <div class="panel panel--editor">
        <div class="panel__header">
          <h3 class="panel__title">{{ selectedRule ? '编辑规则' : '新建规则' }}</h3>
          <div v-if="selectedRule" class="header-actions">
            <button class="btn btn--sm btn--outline" @click="testRule">测试</button>
            <button class="btn btn--sm btn--primary" :disabled="saving" @click="saveRule">保存</button>
          </div>
        </div>
        <div class="panel__body">
          <div v-if="!selectedRule && !isCreating" class="empty-state">
            <span class="empty-icon">👈</span>
            <span class="empty-text">选择左侧规则编辑，或点击"新建规则"</span>
          </div>
          <div v-else class="editor-content">
            <!-- 基本信息 -->
            <div class="editor-section">
              <h4 class="section-title">基本信息</h4>
              <div class="form-grid">
                <div class="form-item">
                  <label class="form-label">规则名称</label>
                  <input v-model="editForm.name" class="form-input" type="text" placeholder="输入规则名称" />
                </div>
                <div class="form-item">
                  <label class="form-label">关联病种</label>
                  <select v-model="editForm.disease_id" class="form-select">
                    <option value="">选择病种</option>
                    <option v-for="d in diseases" :key="d.id" :value="d.id">{{ d.name }}</option>
                  </select>
                </div>
                <div class="form-item">
                  <label class="form-label">版本</label>
                  <input v-model="editForm.version" class="form-input" type="text" placeholder="v1.0.0" />
                </div>
                <div class="form-item">
                  <label class="form-label">状态</label>
                  <select v-model="editForm.status" class="form-select">
                    <option value="draft">草稿</option>
                    <option value="active">启用</option>
                    <option value="disabled">禁用</option>
                  </select>
                </div>
              </div>
              <div class="form-item form-item--full">
                <label class="form-label">描述</label>
                <textarea v-model="editForm.description" class="form-textarea" rows="2" placeholder="输入规则描述"></textarea>
              </div>
            </div>

            <!-- 规则逻辑 -->
            <div class="editor-section">
              <h4 class="section-title">规则逻辑</h4>
              <div class="logic-editor">
                <!-- 逻辑运算符 -->
                <div class="logic-operator">
                  <label class="form-label">逻辑关系</label>
                  <div class="operator-tabs">
                    <button
                      v-for="op in ['ALL', 'ANY', 'NOT']"
                      :key="op"
                      :class="['op-tab', { 'op-tab--active': editForm.dsl?.operator === op }]"
                      @click="setOperator(op)"
                    >
                      {{ op }}
                    </button>
                  </div>
                  <span class="operator-hint">{{ operatorHint }}</span>
                </div>

                <!-- 条件列表 -->
                <div class="conditions-list">
                  <div v-for="(cond, index) in editForm.dsl?.conditions || []" :key="index" class="condition-item">
                    <div class="condition-header">
                      <span class="condition-index">#{{ index + 1 }}</span>
                      <select v-model="cond.type" class="condition-type">
                        <option value="vital">生命体征</option>
                        <option value="lab">检验</option>
                        <option value="medication">药物</option>
                        <option value="diagnosis">诊断</option>
                        <option value="device">装置</option>
                        <option value="score">评分</option>
                      </select>
                      <button class="btn-icon btn-icon--danger" @click="removeCondition(index)" title="删除条件">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                      </button>
                    </div>
                    <div class="condition-body">
                      <div class="condition-row">
                        <div class="form-item">
                          <label class="form-label">字段</label>
                          <input v-model="cond.field" class="form-input" type="text" placeholder="如: heart_rate" />
                        </div>
                        <div class="form-item">
                          <label class="form-label">运算符</label>
                          <select v-model="cond.operator" class="form-select">
                            <option value=">">大于</option>
                            <option value=">=">大于等于</option>
                            <option value="<">小于</option>
                            <option value="<=">小于等于</option>
                            <option value="=">等于</option>
                            <option value="!=">不等于</option>
                            <option value="in">包含</option>
                            <option value="between">区间</option>
                          </select>
                        </div>
                        <div class="form-item">
                          <label class="form-label">值</label>
                          <input v-model="cond.value" class="form-input" type="text" placeholder="阈值" />
                        </div>
                      </div>
                      <div class="condition-row">
                        <div class="form-item">
                          <label class="form-label">时间窗口</label>
                          <input v-model="cond.time_window" class="form-input" type="text" placeholder="如: 24h, 6h" />
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 添加条件按钮 -->
                  <button class="btn btn--outline btn--block" @click="addCondition">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    添加条件
                  </button>
                </div>
              </div>
            </div>

            <!-- 自然语言解释 -->
            <div class="editor-section">
              <h4 class="section-title">自然语言解释</h4>
              <div class="nl-explanation">
                <p class="nl-text">{{ generateExplanation() }}</p>
              </div>
            </div>

            <!-- 底部操作栏 -->
            <div class="editor-actions">
              <button class="btn btn--outline" :disabled="validating" @click="validateRule">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                {{ validating ? '检查中...' : 'Schema检查' }}
              </button>
              <button class="btn btn--outline" @click="testRule">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                测试病例
              </button>
              <button class="btn btn--outline" :disabled="aiChecking" @click="aiCheck">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/></svg>
                {{ aiChecking ? '检查中...' : 'AI检查' }}
              </button>
              <div class="actions-right">
                <button class="btn btn--outline" :disabled="saving" @click="saveDraft">保存草稿</button>
                <button class="btn btn--primary" @click="submitReview">提交审核</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  getPhenotypeRules,
  getDiseases,
  createPhenotypeRule,
  updatePhenotypeRule,
  validatePhenotypeRule,
  type PhenotypeRule,
  type Disease,
} from '../../api/diseaseCenter'
import { postAiConsultChat } from '../../api'

// 状态
const loading = ref(false)
const selectedDisease = ref('')
const selectedStatus = ref('')
const selectedRule = ref<PhenotypeRule | null>(null)
const isCreating = ref(false)

// 数据
const rules = ref<PhenotypeRule[]>([])
const diseases = ref<Disease[]>([])

// 编辑表单
const editForm = ref<{
  name: string
  disease_id: string
  version: string
  status: string
  description: string
  dsl: {
    operator: 'ALL' | 'ANY' | 'NOT'
    conditions: Array<{
      type: string
      field: string
      operator: string
      value: any
      time_window?: string
    }>
  }
}>({
  name: '',
  disease_id: '',
  version: 'v1.0.0',
  status: 'draft',
  description: '',
  dsl: {
    operator: 'ALL',
    conditions: [],
  },
})

const error = ref<string | null>(null)

// 运算符提示
const operatorHint = computed(() => {
  const map: Record<string, string> = {
    ALL: '所有条件都满足时触发（AND）',
    ANY: '任一条件满足时触发（OR）',
    NOT: '所有条件都不满足时触发（NOR）',
  }
  return map[editForm.value.dsl?.operator || 'ALL'] || ''
})

// 状态文本
function statusText(status?: string) {
  const map: Record<string, string> = { active: '已启用', draft: '草稿', disabled: '已禁用' }
  return map[status || 'draft'] || '草稿'
}

// 设置运算符
function setOperator(op: string) {
  if (!editForm.value.dsl) {
    editForm.value.dsl = { operator: op as any, conditions: [] }
  } else {
    editForm.value.dsl.operator = op as any
  }
}

// 添加条件
function addCondition() {
  if (!editForm.value.dsl) {
    editForm.value.dsl = { operator: 'ALL', conditions: [] }
  }
  editForm.value.dsl.conditions.push({
    type: 'vital',
    field: '',
    operator: '>',
    value: null,
    time_window: '',
  })
}

// 删除条件
function removeCondition(index: number) {
  editForm.value.dsl?.conditions.splice(index, 1)
}

// 生成自然语言解释
function generateExplanation() {
  const dsl = editForm.value.dsl
  if (!dsl?.conditions?.length) return '请添加条件'

  const opMap: Record<string, string> = { ALL: '且', ANY: '或', NOT: '非' }
  const opText = opMap[dsl.operator] || '且'

  const parts = dsl.conditions.map((c) => {
    const field = c.field || '???'
    const opMap: Record<string, string> = { '>': '大于', '>=': '大于等于', '<': '小于', '<=': '小于等于', '=': '等于', '!=': '不等于', in: '包含', between: '在...之间' }
    const opText = opMap[c.operator] || c.operator
    const value = c.value ?? '???'
    const time = c.time_window ? `（${c.time_window}内）` : ''
    return `${field} ${opText} ${value}${time}`
  })

  return `当 ${parts.join(` ${opText} `)} 时，识别为该表型`
}

// 选择规则
function selectRule(rule: PhenotypeRule) {
  selectedRule.value = rule
  isCreating.value = false
  editForm.value = {
    name: rule.name,
    disease_id: rule.disease_id || '',
    version: rule.version || 'v1.0.0',
    status: rule.status || 'draft',
    description: rule.description || '',
    dsl: rule.dsl || { operator: 'ALL', conditions: [] },
  }
}

// 新建规则
function createRule() {
  selectedRule.value = null
  isCreating.value = true
  editForm.value = {
    name: '',
    disease_id: '',
    version: 'v1.0.0',
    status: 'draft',
    description: '',
    dsl: { operator: 'ALL', conditions: [] },
  }
}

// 保存状态
const saving = ref(false)
const validating = ref(false)
const aiChecking = ref(false)

function buildPayload(statusOverride?: string): Partial<PhenotypeRule> {
  return {
    name: editForm.value.name,
    disease_id: editForm.value.disease_id,
    version: editForm.value.version,
    status: statusOverride || editForm.value.status,
    description: editForm.value.description,
    dsl: editForm.value.dsl,
  }
}

// 保存规则（新建或更新）
async function persistRule(statusOverride?: string) {
  if (!editForm.value.name.trim()) {
    message.warning('请填写规则名称')
    return
  }
  saving.value = true
  try {
    const payload = buildPayload(statusOverride)
    const res = selectedRule.value
      ? await updatePhenotypeRule(selectedRule.value.id, payload)
      : await createPhenotypeRule(payload)
    if (statusOverride) editForm.value.status = statusOverride
    message.success(
      statusOverride === 'draft' ? '草稿已保存' : selectedRule.value ? '规则已保存' : '规则已创建'
    )
    await loadRules()
    const savedId = res.data?.id || selectedRule.value?.id
    const target = savedId ? rules.value.find((r) => r.id === savedId) : undefined
    if (target) {
      selectRule(target)
    } else if (!selectedRule.value) {
      isCreating.value = true
    }
  } catch (e: any) {
    message.error(e?.message || '保存失败，请稍后重试')
  } finally {
    saving.value = false
  }
}

// 保存规则
function saveRule() {
  persistRule()
}

// 保存草稿
function saveDraft() {
  persistRule('draft')
}

// 提交审核
function submitReview() {
  message.info('后端暂未提供表型规则提交审核接口')
}

// 测试规则
function testRule() {
  message.info('后端暂未提供表型规则测试接口')
}

// Schema检查
async function validateRule() {
  if (!editForm.value.name.trim()) {
    message.warning('请填写规则名称后再检查')
    return
  }
  validating.value = true
  try {
    const { data } = await validatePhenotypeRule(buildPayload())
    if (data.valid) {
      if (data.warnings?.length) {
        message.warning(`Schema检查通过，但有警告：${data.warnings.join('；')}`)
      } else {
        message.success('Schema检查通过')
      }
    } else {
      message.error(`Schema检查未通过：${(data.errors || []).join('；')}`)
    }
  } catch (e: any) {
    message.error(e?.message || 'Schema检查失败，请稍后重试')
  } finally {
    validating.value = false
  }
}

// AI检查
async function aiCheck() {
  aiChecking.value = true
  try {
    const { data } = await postAiConsultChat({
      message:
        `请检查以下表型规则是否存在逻辑冲突或缺失：\n` +
        `规则名称：${editForm.value.name || '(未命名)'}\n` +
        `逻辑说明：${generateExplanation()}\n` +
        `DSL：${JSON.stringify(editForm.value.dsl)}`,
      mode: 'clinical',
      history: [],
    })
    const reply = data.reply || data.message || 'AI 未返回检查结果'
    Modal.info({
      title: 'AI 检查结果',
      content: () => h('div', { innerHTML: reply, style: 'max-height:60vh;overflow:auto;' }),
      okText: '知道了',
      width: 560,
    })
  } catch (e: any) {
    message.error(e?.message || 'AI检查失败，请稍后重试')
  } finally {
    aiChecking.value = false
  }
}

// 加载规则
async function loadRules() {
  loading.value = true
  error.value = null

  try {
    const { data } = await getPhenotypeRules({
      disease_id: selectedDisease.value || undefined,
      status: selectedStatus.value || undefined,
    })
    rules.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    error.value = e?.message || '获取表型规则失败，请稍后重试'
    rules.value = []
  } finally {
    loading.value = false
  }
}

// 初始化
onMounted(async () => {
  // 加载病种列表
  try {
    const { data } = await getDiseases()
    diseases.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    message.error(e?.message || '获取病种列表失败')
  }

  await loadRules()
})

// 筛选变化时自动重载
watch([selectedDisease, selectedStatus], () => {
  loadRules()
})
</script>

<style scoped>.phenotypes-page { display: flex; flex-direction: column; gap: 16px }

/* 工具栏 */ .toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 16px; background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB) }
.toolbar__left, .toolbar__right { display: flex; align-items: center; gap: 8px }
.filter-select { padding: 8px 12px; font-size: var(--text-body, 13px); border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); cursor: pointer; min-width: 120px }

/* 内容区 */ .content-grid { display: grid; grid-template-columns: 300px 1fr; gap: 16px; min-height: 600px }

/* 面板 */ .panel { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); display: flex; flex-direction: column; overflow: hidden }
.panel__header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--color-divider, #F0F2F5) }
.panel__title { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 }
.panel__count { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.panel__body { flex: 1; overflow-y: auto; padding: 12px }
.header-actions { display: flex; gap: 8px }

/* 规则列表 */ .rule-list { display: flex; flex-direction: column; gap: 8px }
.rule-card { padding: 12px; border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB); cursor: pointer; transition: all 0.15s }
.rule-card:hover { border-color: var(--color-primary, #2563EB); background: var(--color-primary-bg) }
.rule-card--active { border-color: var(--color-primary, #2563EB); background: var(--color-primary-bg) }
.rule-card__header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px }
.rule-card__name { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }
.rule-card__meta { display: flex; align-items: center; gap: 8px; margin-bottom: 6px }
.meta-tag { font-size: var(--text-caption, 12px); padding: 1px 6px; border-radius: var(--radius-tag, 4px); background: var(--color-primary-bg); color: var(--color-primary, #2563EB) }
.meta-version { font-size: var(--text-caption, 12px); font-family: 'SF Mono', 'Consolas', monospace; color: var(--color-text-secondary, #4B5563) }
.rule-card__preview { display: flex; align-items: center; gap: 8px }
.preview-op { font-size: var(--text-caption, 12px); font-weight: 600; padding: 1px 6px; border-radius: var(--radius-tag, 4px); background: var(--color-bg-surface-secondary, #F1F4F8); color: var(--color-text-primary, #111827) }
.preview-count { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }

/* 状态徽章 */ .status-badge { display: inline-flex; padding: 2px 8px; font-size: var(--text-caption, 12px); font-weight: 500; border-radius: var(--radius-tag, 4px) }
.status-badge--active { color: var(--color-success, #16845B); background: var(--color-success-bg) }
.status-badge--draft { color: var(--color-warning, #B54708); background: var(--color-warning-bg) }
.status-badge--disabled { color: var(--color-text-secondary, #4B5563); background: var(--color-bg-surface-secondary, #F1F4F8) }

/* 编辑器 */ .editor-content { display: flex; flex-direction: column; gap: 20px }
.editor-section { display: flex; flex-direction: column; gap: 12px }
.section-title { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0; padding-bottom: 6px; border-bottom: 1px solid var(--color-divider, #F0F2F5) }

/* 表单 */ .form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px }
.form-item { display: flex; flex-direction: column; gap: 4px }
.form-item--full { grid-column: 1 / -1 }
.form-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); font-weight: 500 }
.form-input, .form-select, .form-textarea { padding: 8px 12px; font-size: var(--text-body, 13px); border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); outline: none; transition: border-color 0.15s }
.form-input:focus, .form-select:focus, .form-textarea:focus { border-color: var(--color-primary, #2563EB) }
.form-textarea { resize: vertical; min-height: 60px }

/* 逻辑编辑器 */ .logic-editor { display: flex; flex-direction: column; gap: 16px }
.logic-operator { display: flex; flex-direction: column; gap: 8px }
.operator-tabs { display: flex; gap: 4px }
.op-tab { padding: 6px 16px; font-size: var(--text-body, 13px); font-weight: 500; border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-tag, 4px); background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); cursor: pointer; transition: all 0.15s }
.op-tab:hover { border-color: var(--color-primary, #2563EB) }
.op-tab--active { background: var(--color-primary, #2563EB); color: var(--color-text-inverse, #FFFFFF); border-color: var(--color-primary, #2563EB) }
.operator-hint { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }

/* 条件列表 */ .conditions-list { display: flex; flex-direction: column; gap: 12px }
.condition-item { border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); overflow: hidden }
.condition-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--color-bg-surface-secondary, #F1F4F8); border-bottom: 1px solid var(--color-border, #E5E7EB) }
.condition-index { font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-text-secondary, #4B5563); min-width: 24px }
.condition-type { flex: 1; padding: 4px 8px; font-size: var(--text-caption, 12px); border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-tag, 4px); background: var(--color-bg-surface, #FFFFFF) }
.condition-body { padding: 12px; display: flex; flex-direction: column; gap: 10px }
.condition-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px }
.btn-icon { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; border-radius: var(--radius-tag, 4px); cursor: pointer; transition: all 0.15s; background: transparent; color: var(--color-text-secondary, #4B5563) }
.btn-icon:hover { background: var(--color-bg-surface-secondary, #F1F4F8) }
.btn-icon--danger:hover { color: var(--color-danger, #D92D20); background: var(--color-danger-bg) }

/* 自然语言解释 */ .nl-explanation { padding: 12px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB) }
.nl-text { font-size: var(--text-body, 13px); color: var(--color-text-primary, #111827); margin: 0; line-height: 1.6 }

/* 操作栏 */ .editor-actions { display: flex; align-items: center; gap: 8px; padding-top: 16px; border-top: 1px solid var(--color-divider, #F0F2F5) }
.actions-right { margin-left: auto; display: flex; gap: 8px }

/* 按钮 */ .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 14px; font-size: var(--text-body, 13px); font-weight: 500; border-radius: var(--radius-md, 6px); cursor: pointer; transition: all 0.15s; border: 1px solid transparent; white-space: nowrap }
.btn--sm { padding: 4px 10px; font-size: var(--text-caption, 12px) }
.btn--outline { background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); border-color: var(--color-border, #E5E7EB) }
.btn--outline:hover { background: var(--color-bg-surface-secondary, #F1F4F8); border-color: var(--color-border-strong, #D1D5DB) }
.btn--primary { background: var(--color-primary, #2563EB); color: var(--color-text-inverse, #FFFFFF); border-color: var(--color-primary, #2563EB) }
.btn--primary:hover { background: var(--color-primary-hover, #3B82F6) }
.btn--block { width: 100% }

/* 加载和空状态 */ .loading-state, .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 40px 20px; text-align: center }
.spinner { width: 24px; height: 24px; border: 2px solid var(--color-border, #E5E7EB); border-top-color: var(--color-primary, #2563EB); border-radius: 50%; animation: spin 0.8s linear infinite }

@keyframes spin {to { transform: rotate(360deg) }
 }
.empty-icon { font-size: 32px; opacity: 0.6 }
.empty-text { font-size: var(--text-body, 13px); font-weight: 500; color: var(--color-text-primary, #111827) }

/* 响应式 */

@media (max-width: 1024px) {.content-grid { grid-template-columns: 1fr }
.panel--list { max-height: 300px }

}

</style>
