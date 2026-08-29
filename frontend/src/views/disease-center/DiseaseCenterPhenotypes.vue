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
            <button class="btn btn--sm btn--primary" @click="saveRule">保存</button>
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
              <button class="btn btn--outline" @click="validateRule">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                Schema检查
              </button>
              <button class="btn btn--outline" @click="testRule">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                测试病例
              </button>
              <button class="btn btn--outline" @click="aiCheck">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.9 5.8a2 2 0 0 0 1.3 1.3L21 12l-5.8 1.9a2 2 0 0 0-1.3 1.3L12 21l-1.9-5.8a2 2 0 0 0-1.3-1.3L3 12l5.8-1.9a2 2 0 0 0 1.3-1.3z"/></svg>
                AI检查
              </button>
              <div class="actions-right">
                <button class="btn btn--outline" @click="saveDraft">保存草稿</button>
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
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { getPhenotypeRules, getDiseases, type PhenotypeRule, type Disease } from '../../api/diseaseCenter'

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

// 保存规则
function saveRule() {
  // TODO: 实现保存逻辑
  message.info('保存功能开发中')
}

// 保存草稿
function saveDraft() {
  // TODO: 实现保存草稿逻辑
  message.success('草稿已保存')
}

// 提交审核
function submitReview() {
  // TODO: 实现提交审核逻辑
  message.success('已提交审核')
}

// 测试规则
function testRule() {
  // TODO: 实现测试逻辑
  message.info('测试功能开发中')
}

// Schema检查
function validateRule() {
  // TODO: 实现Schema检查逻辑
  message.success('Schema检查通过')
}

// AI检查
function aiCheck() {
  // TODO: 实现AI检查逻辑
  message.info('AI检查功能开发中')
}

// 加载规则
async function loadRules() {
  loading.value = true
  error.value = null

  try {
    const { data } = await getPhenotypeRules({ disease_id: selectedDisease.value || undefined })
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
</script>

<style scoped>
.phenotypes-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
}

.toolbar__left, .toolbar__right { display: flex; align-items: center; gap: 8px; }

.filter-select { padding: 8px 12px; font-size: 13px; border: 1px solid var(--color-border, #D0D5DD); border-radius: 6px; background: #fff; color: var(--color-text-primary, #18212B); cursor: pointer; min-width: 120px; }

/* 内容区 */
.content-grid {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 16px;
  min-height: 600px;
}

/* 面板 */
.panel { background: #fff; border-radius: 8px; border: 1px solid var(--color-border, #E3E7EC); display: flex; flex-direction: column; overflow: hidden; }
.panel__header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid #f0f0f0; }
.panel__title { font-size: 14px; font-weight: 600; color: var(--color-text-primary, #18212B); margin: 0; }
.panel__count { font-size: 12px; color: var(--color-text-secondary, #667085); }
.panel__body { flex: 1; overflow-y: auto; padding: 12px; }

.header-actions { display: flex; gap: 8px; }

/* 规则列表 */
.rule-list { display: flex; flex-direction: column; gap: 8px; }
.rule-card { padding: 12px; border-radius: 6px; border: 1px solid var(--color-border, #E3E7EC); cursor: pointer; transition: all 0.15s; }
.rule-card:hover { border-color: var(--color-primary, #2563EB); background: rgba(37, 99, 235, 0.02); }
.rule-card--active { border-color: var(--color-primary, #2563EB); background: rgba(37, 99, 235, 0.06); }
.rule-card__header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.rule-card__name { font-size: 13px; font-weight: 600; color: var(--color-text-primary, #18212B); }
.rule-card__meta { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.meta-tag { font-size: 11px; padding: 1px 6px; border-radius: 3px; background: rgba(37, 99, 235, 0.08); color: var(--color-primary, #2563EB); }
.meta-version { font-size: 11px; font-family: 'SF Mono', 'Consolas', monospace; color: var(--color-text-secondary, #667085); }
.rule-card__preview { display: flex; align-items: center; gap: 8px; }
.preview-op { font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 3px; background: var(--color-bg-surface-secondary, #F1F3F5); color: var(--color-text-primary, #18212B); }
.preview-count { font-size: 11px; color: var(--color-text-tertiary, #98A2B3); }

/* 状态徽章 */
.status-badge { display: inline-flex; padding: 2px 8px; font-size: 11px; font-weight: 500; border-radius: 4px; }
.status-badge--active { color: var(--color-success, #16845B); background: rgba(22, 132, 91, 0.1); }
.status-badge--draft { color: var(--color-warning, #B54708); background: rgba(181, 71, 8, 0.1); }
.status-badge--disabled { color: var(--color-text-secondary, #667085); background: var(--color-bg-surface-secondary, #F1F3F5); }

/* 编辑器 */
.editor-content { display: flex; flex-direction: column; gap: 20px; }
.editor-section { display: flex; flex-direction: column; gap: 12px; }
.section-title { font-size: 13px; font-weight: 600; color: var(--color-text-primary, #18212B); margin: 0; padding-bottom: 6px; border-bottom: 1px solid #f0f0f0; }

/* 表单 */
.form-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.form-item { display: flex; flex-direction: column; gap: 4px; }
.form-item--full { grid-column: 1 / -1; }
.form-label { font-size: 12px; color: var(--color-text-secondary, #667085); font-weight: 500; }
.form-input, .form-select, .form-textarea { padding: 8px 12px; font-size: 13px; border: 1px solid var(--color-border, #D0D5DD); border-radius: 6px; background: #fff; color: var(--color-text-primary, #18212B); outline: none; transition: border-color 0.15s; }
.form-input:focus, .form-select:focus, .form-textarea:focus { border-color: var(--color-primary, #2563EB); }
.form-textarea { resize: vertical; min-height: 60px; }

/* 逻辑编辑器 */
.logic-editor { display: flex; flex-direction: column; gap: 16px; }
.logic-operator { display: flex; flex-direction: column; gap: 8px; }
.operator-tabs { display: flex; gap: 4px; }
.op-tab { padding: 6px 16px; font-size: 13px; font-weight: 500; border: 1px solid var(--color-border, #D0D5DD); border-radius: 4px; background: #fff; color: var(--color-text-primary, #18212B); cursor: pointer; transition: all 0.15s; }
.op-tab:hover { border-color: var(--color-primary, #2563EB); }
.op-tab--active { background: var(--color-primary, #2563EB); color: #fff; border-color: var(--color-primary, #2563EB); }
.operator-hint { font-size: 12px; color: var(--color-text-secondary, #667085); }

/* 条件列表 */
.conditions-list { display: flex; flex-direction: column; gap: 12px; }
.condition-item { border: 1px solid var(--color-border, #E3E7EC); border-radius: 6px; overflow: hidden; }
.condition-header { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: var(--color-bg-surface-secondary, #F9FAFB); border-bottom: 1px solid var(--color-border, #E3E7EC); }
.condition-index { font-size: 12px; font-weight: 600; color: var(--color-text-secondary, #667085); min-width: 24px; }
.condition-type { flex: 1; padding: 4px 8px; font-size: 12px; border: 1px solid var(--color-border, #D0D5DD); border-radius: 4px; background: #fff; }
.condition-body { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.condition-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }

.btn-icon { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border: none; border-radius: 4px; cursor: pointer; transition: all 0.15s; background: transparent; color: var(--color-text-secondary, #667085); }
.btn-icon:hover { background: var(--color-bg-surface-secondary, #F1F3F5); }
.btn-icon--danger:hover { color: var(--color-danger, #D92D20); background: rgba(217, 45, 32, 0.08); }

/* 自然语言解释 */
.nl-explanation { padding: 12px; background: var(--color-bg-surface-secondary, #F9FAFB); border-radius: 6px; border: 1px solid var(--color-border, #E3E7EC); }
.nl-text { font-size: 13px; color: var(--color-text-primary, #18212B); margin: 0; line-height: 1.6; }

/* 操作栏 */
.editor-actions { display: flex; align-items: center; gap: 8px; padding-top: 16px; border-top: 1px solid #f0f0f0; }
.actions-right { margin-left: auto; display: flex; gap: 8px; }

/* 按钮 */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 14px; font-size: 13px; font-weight: 500; border-radius: 6px; cursor: pointer; transition: all 0.15s; border: 1px solid transparent; white-space: nowrap; }
.btn--sm { padding: 4px 10px; font-size: 12px; }
.btn--outline { background: #fff; color: var(--color-text-primary, #18212B); border-color: var(--color-border, #D0D5DD); }
.btn--outline:hover { background: var(--color-bg-surface-secondary, #F9FAFB); border-color: #B0B8C4; }
.btn--primary { background: var(--color-primary, #2563EB); color: #fff; border-color: var(--color-primary, #2563EB); }
.btn--primary:hover { background: #1D4FD8; }
.btn--block { width: 100%; }

/* 加载和空状态 */
.loading-state, .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 40px 20px; text-align: center; }
.spinner { width: 24px; height: 24px; border: 2px solid var(--color-border, #E3E7EC); border-top-color: var(--color-primary, #2563EB); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.empty-icon { font-size: 32px; opacity: 0.6; }
.empty-text { font-size: 14px; font-weight: 500; color: var(--color-text-primary, #18212B); }

/* 响应式 */
@media (max-width: 1024px) {
  .content-grid { grid-template-columns: 1fr; }
  .panel--list { max-height: 300px; }
}
</style>
