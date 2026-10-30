<template>
  <div class="scores-page">
    <!-- 三栏布局 -->
    <div class="content-grid">
      <!-- 左栏：评分体系列表 -->
      <div class="panel panel--left">
        <div class="panel__header">
          <h3 class="panel__title">评分体系</h3>
        </div>
        <div class="panel__body">
          <div class="score-tree">
            <div
              v-for="system in scoreGroups"
              :key="system.name"
              :class="['tree-item', { 'tree-item--active': selectedRule?.score_system === system.name }]"
              @click="selectRule(system)"
            >
              <span class="tree-item__name">{{ system.name }}</span>
              <span class="tree-item__version">{{ system.variants?.length ? system.variants.length + ' 个变体' : '' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 中栏：评分详情 -->
      <div class="panel panel--center">
        <div class="panel__header">
          <h3 class="panel__title">评分详情</h3>
          <span v-if="selectedRule" class="panel__badge">{{ selectedRule.version }}</span>
        </div>
        <div class="panel__body">
          <div v-if="loading" class="loading-state">
            <div class="spinner"></div>
            <span>加载中...</span>
          </div>
          <div v-else-if="error" class="error-state">
            <span class="error-icon">⚠️</span>
            <span class="error-text">{{ error }}</span>
            <button class="btn btn--sm btn--outline" @click="loadScoringSystems">重试</button>
          </div>
          <div v-else-if="!selectedRule" class="empty-state">
            <span class="empty-icon">📈</span>
            <span class="empty-text">选择左侧评分体系查看详情</span>
          </div>
          <div v-else class="rule-detail">
            <!-- 基本信息 -->
            <div class="detail-section">
              <h4 class="section-title">基本信息</h4>
              <div class="detail-grid">
                <div class="detail-item">
                  <span class="detail-label">评分系统</span>
                  <span class="detail-value">{{ selectedRule.name }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">版本</span>
                  <span class="detail-value detail-value--code">{{ selectedRule.version }}</span>
                </div>
                <div class="detail-item">
                  <span class="detail-label">缺失值策略</span>
                  <span class="detail-value">{{ selectedRule.missing_policy || '默认' }}</span>
                </div>
                <div v-if="selectedRule.time_window" class="detail-item">
                  <span class="detail-label">时间窗</span>
                  <span class="detail-value">{{ selectedRule.time_window }}</span>
                </div>
              </div>
              <p v-if="selectedRule.description" class="detail-desc">{{ selectedRule.description }}</p>
            </div>

            <!-- 输入项 -->
            <div class="detail-section">
              <h4 class="section-title">输入项 ({{ selectedRule.inputs?.length || 0 }})</h4>
              <div class="input-table">
                <div class="input-header">
                  <span class="input-col input-col--name">名称</span>
                  <span class="input-col input-col--label">标签</span>
                  <span class="input-col input-col--type">类型</span>
                  <span class="input-col input-col--unit">单位</span>
                  <span class="input-col input-col--required">必填</span>
                </div>
                <div v-for="input in selectedRule.inputs" :key="input.name" class="input-row">
                  <span class="input-col input-col--name input-col--code">{{ input.name }}</span>
                  <span class="input-col input-col--label">{{ input.label }}</span>
                  <span class="input-col input-col--type">{{ input.type }}</span>
                  <span class="input-col input-col--unit">{{ input.unit || '-' }}</span>
                  <span class="input-col input-col--required">
                    <span :class="['required-dot', input.required ? 'required-dot--yes' : 'required-dot--no']"></span>
                  </span>
                </div>
              </div>
            </div>

            <!-- 阈值表 -->
            <div v-if="selectedRule.thresholds?.length" class="detail-section">
              <h4 class="section-title">阈值表</h4>
              <div class="threshold-list">
                <div v-for="(t, i) in selectedRule.thresholds" :key="i" class="threshold-item">
                  <span class="threshold-range">{{ t.range[0] }} - {{ t.range[1] }}</span>
                  <span class="threshold-label">{{ t.label }}</span>
                  <span v-if="t.severity" :class="['threshold-severity', `threshold-severity--${t.severity}`]">
                    {{ t.severity }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右栏：测试病例 -->
      <div class="panel panel--right">
        <div class="panel__header">
          <h3 class="panel__title">测试病例</h3>
          <button v-if="selectedRule" class="btn btn--sm btn--outline" @click="runTest">
            运行测试
          </button>
        </div>
        <div class="panel__body">
          <div v-if="!selectedRule" class="empty-state">
            <span class="empty-icon">🧪</span>
            <span class="empty-text">选择评分体系后运行测试</span>
          </div>
          <div v-else-if="testRunning" class="loading-state">
            <div class="spinner"></div>
            <span>正在计算...</span>
          </div>
          <div v-else-if="error" class="error-state">
            <span class="error-icon">⚠️</span>
            <span class="error-text">{{ error }}</span>
            <button class="btn btn--sm btn--outline" @click="runTest">重试</button>
          </div>
          <div v-else-if="!testResult" class="empty-state">
            <span class="empty-icon">▶️</span>
            <span class="empty-text">点击"运行测试"查看结果</span>
          </div>
          <div v-else class="test-result">
            <!-- 总分 -->
            <div class="result-total">
              <span class="result-label">总分</span>
              <span class="result-score">{{ testResult.total_score }}</span>
            </div>

            <!-- 总分 -->
            <div class="result-section">
              <h4 class="section-title">总分</h4>
              <div class="total-score">
                <span class="score-value">{{ testResult.total_score }}</span>
              </div>
            </div>

            <!-- 分项得分 -->
            <div class="result-section">
              <h4 class="section-title">分项得分</h4>
              <div class="component-list">
                <div v-for="(score, name) in testResult.component_scores" :key="name" class="component-item">
                  <span class="component-name">{{ name }}</span>
                  <span class="component-score">{{ score }}</span>
                </div>
              </div>
            </div>

            <!-- 元数据 -->
            <div class="result-section">
              <h4 class="section-title">评分元数据</h4>
              <div class="meta-list">
                <div class="meta-item">
                  <span class="meta-label">score_system</span>
                  <span class="meta-value meta-value--code">{{ testResult.score_system }}</span>
                </div>
                <div v-if="testResult.score_variant" class="meta-item">
                  <span class="meta-label">score_variant</span>
                  <span class="meta-value meta-value--code">{{ testResult.score_variant }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">rule_id</span>
                  <span class="meta-value meta-value--code">{{ testResult.rule_id }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">rule_version</span>
                  <span class="meta-value meta-value--code">{{ testResult.rule_version }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">evaluation_time</span>
                  <span class="meta-value">{{ testResult.evaluation_time }}</span>
                </div>
                <div class="meta-item">
                  <span class="meta-label">input_snapshot_hash</span>
                  <span class="meta-value meta-value--code meta-value--small">{{ testResult.input_snapshot_hash }}</span>
                </div>
              </div>
            </div>

            <!-- 缺失输入 -->
            <div v-if="testResult.missing_inputs?.length" class="result-section">
              <h4 class="section-title">缺失输入</h4>
              <div class="missing-list">
                <span v-for="m in testResult.missing_inputs" :key="m" class="missing-tag">{{ m }}</span>
              </div>
            </div>

            <!-- 输入证据 -->
            <div v-if="testResult.evidence?.length" class="result-section">
              <h4 class="section-title">输入证据</h4>
              <div class="evidence-list">
                <div v-for="e in testResult.evidence" :key="e.input" class="evidence-item">
                  <span class="evidence-input">{{ e.input }}</span>
                  <span class="evidence-value">{{ e.value }}</span>
                  <span v-if="e.source" class="evidence-source">{{ e.source }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getScoringSystems,
  getScoringRule,
  evaluateScore,
  type ScoringSystem,
  type ScoringRule,
  type ScoringResult,
} from '../../api/diseaseCenter'

// 状态
const selectedRule = ref<ScoringRule | null>(null)
const testRunning = ref(false)
const testResult = ref<ScoringResult | null>(null)

// 评分体系分组
const scoreGroups = ref<ScoringSystem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

// 选择评分规则
async function selectRule(system: ScoringSystem) {
  loading.value = true
  error.value = null

  try {
    // registry.get 需要注册键（list 返回的 score_name 字段）；
    // name 是显示名（SOFA/SOFA2 共用 "SOFA"），不能当 ID 用
    const ruleId = system.score_name || system.name
    const { data } = await getScoringRule(ruleId)
    selectedRule.value = data
    testResult.value = null
  } catch (e: any) {
    error.value = e?.message || '获取评分规则失败'
  } finally {
    loading.value = false
  }
}

// 运行测试
async function runTest() {
  if (!selectedRule.value) return

  testRunning.value = true
  testResult.value = null
  error.value = null

  try {
    // 示例值：有 required 的用 1，可选用 0，便于跑通计算链路
    const sampleInputs = (selectedRule.value.inputs || []).map((input) => ({
      code: input.name,
      display_name: input.label,
      value: input.required ? 1 : 0,
      unit: input.unit,
    }))

    // 优先用注册键 score_variant（如 SOFA2 / NEWS2），其次 score_system
    const scoreId =
      selectedRule.value.score_variant ||
      selectedRule.value.id ||
      selectedRule.value.score_system ||
      selectedRule.value.name
    const { data } = await evaluateScore(scoreId, sampleInputs)
    testResult.value = data
  } catch (e: any) {
    error.value = e?.message || '评分计算失败，请稍后重试'
  } finally {
    testRunning.value = false
  }
}

// 加载评分系统
async function loadScoringSystems() {
  loading.value = true
  error.value = null

  try {
    const { data } = await getScoringSystems()
    scoreGroups.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    error.value = e?.message || '获取评分体系失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

// 初始化
onMounted(() => {
  loadScoringSystems()
})
</script>

<style scoped>.scores-page { display: flex; flex-direction: column; gap: 16px }

/* 三栏布局 */ .content-grid { display: grid; grid-template-columns: 200px 1fr 360px; gap: 16px; min-height: 600px }

/* 总分 */ .total-score { display: flex; justify-content: center; padding: 24px }
.score-value  {  font-size: var(--text-metric-key, 26px); font-weight: 700; color: var(--color-primary, #2F6FED) ; font-variant-numeric: tabular-nums }

/* 面板 */ .panel { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); display: flex; flex-direction: column; overflow: hidden }
.panel__header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--color-divider, #F0F2F5) }
.panel__title { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 }
.panel__badge { font-size: var(--text-caption, 12px); font-weight: 500; padding: 2px 8px; border-radius: var(--radius-tag, 4px); background: var(--color-primary-bg); color: var(--color-primary, #2F6FED) }
.panel__body { flex: 1; overflow-y: auto; padding: 12px }

/* 评分树 */ .score-tree { display: flex; flex-direction: column; gap: 12px }
.score-group { display: flex; flex-direction: column; gap: 2px }
.group-header { padding: 4px 8px }
.group-name { font-size: var(--text-caption, 12px); font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--color-text-secondary, #4B5563) }
.tree-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: var(--radius-md, 6px); cursor: pointer; transition: all 0.15s }
.tree-item:hover { background: var(--color-bg-surface-secondary, #F1F4F8) }
.tree-item--active { background: var(--color-primary-bg); color: var(--color-primary, #2F6FED) }
.tree-item__name { font-size: var(--text-body, 13px); font-weight: 500 }
.tree-item__version { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); font-family: 'SF Mono', 'Consolas', monospace }
.tree-item--active .tree-item__version { color: var(--color-primary, #2F6FED) }

/* 规则详情 */ .rule-detail { display: flex; flex-direction: column; gap: 20px }
.detail-section { display: flex; flex-direction: column; gap: 10px }
.section-title { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0; padding-bottom: 6px; border-bottom: 1px solid var(--color-divider, #F0F2F5) }
.detail-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px }
.detail-item { display: flex; flex-direction: column; gap: 2px }
.detail-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.detail-value { font-size: var(--text-body, 13px); font-weight: 500; color: var(--color-text-primary, #111827) }
.detail-value--code { font-family: 'SF Mono', 'Consolas', monospace; font-size: var(--text-caption, 12px) }
.detail-desc { font-size: var(--text-body, 13px); color: var(--color-text-secondary, #4B5563); line-height: 1.6; margin: 0; padding: 10px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-md, 6px) }

/* 输入项表格 */ .input-table { display: flex; flex-direction: column; border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); overflow: hidden }
.input-header, .input-row { display: grid; grid-template-columns: 1fr 1fr 80px 80px 50px; gap: 8px; padding: 8px 12px }
.input-header { background: var(--color-bg-surface-secondary, #F1F4F8); font-size: var(--text-caption, 12px); font-weight: 600; color: var(--color-text-secondary, #4B5563); text-transform: uppercase }
.input-row { font-size: var(--text-caption, 12px); border-top: 1px solid var(--color-border, #E5E7EB) }
.input-row:first-of-type { border-top: none }
.input-col--code { font-family: 'SF Mono', 'Consolas', monospace; font-size: var(--text-caption, 12px) }
.required-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50% }
.required-dot--yes { background: var(--color-danger, #D92D20) }
.required-dot--no { background: var(--color-border, #E5E7EB) }

/* 阈值表 */ .threshold-list { display: flex; flex-direction: column; gap: 6px }
.threshold-item { display: flex; align-items: center; gap: 12px; padding: 8px 10px; border-radius: var(--radius-md, 6px); background: var(--color-bg-surface-secondary, #F1F4F8) }
.threshold-range { font-family: 'SF Mono', 'Consolas', monospace; font-size: var(--text-caption, 12px); font-weight: 500; color: var(--color-text-primary, #111827); min-width: 60px }
.threshold-label { flex: 1; font-size: var(--text-body, 13px); color: var(--color-text-primary, #111827) }
.threshold-severity { font-size: var(--text-caption, 12px); font-weight: 500; padding: 1px 6px; border-radius: var(--radius-tag, 4px) }
.threshold-severity--normal { color: var(--color-success, #16845B); background: var(--color-success-bg) }
.threshold-severity--mild { color: var(--color-info, #2E90FA); background: var(--color-primary-bg) }
.threshold-severity--moderate { color: var(--color-warning, #B54708); background: var(--color-warning-bg) }
.threshold-severity--high, .threshold-severity--critical, .threshold-severity--severe { color: var(--color-danger, #D92D20); background: var(--color-danger-bg) }

/* 测试结果 */ .test-result { display: flex; flex-direction: column; gap: 16px }
.result-total { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 16px; background: var(--color-primary-bg, #E8F0FE); border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border) }
.result-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.result-score  {  font-size: var(--text-metric-key, 26px); font-weight: 700; color: var(--color-primary, #2F6FED); line-height: 1 ; font-variant-numeric: tabular-nums }
.result-section { display: flex; flex-direction: column; gap: 8px }

/* 分项得分 */ .component-list { display: grid; grid-template-columns: repeat(2, 1fr); gap: 6px }
.component-item { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border-radius: var(--radius-tag, 4px); background: var(--color-bg-surface-secondary, #F1F4F8) }
.component-name { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.component-score { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827) }

/* 元数据 */ .meta-list { display: flex; flex-direction: column; gap: 6px }
.meta-item { display: flex; align-items: center; gap: 8px }
.meta-label { font-size: var(--text-caption, 12px); font-family: 'SF Mono', 'Consolas', monospace; color: var(--color-text-secondary, #4B5563); min-width: 130px }
.meta-value { font-size: var(--text-caption, 12px); color: var(--color-text-primary, #111827) }
.meta-value--code { font-family: 'SF Mono', 'Consolas', monospace; font-size: var(--text-caption, 12px); padding: 1px 4px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-tag, 4px) }
.meta-value--small { font-size: var(--text-caption, 12px); word-break: break-all }

/* 缺失输入 */ .missing-list { display: flex; flex-wrap: wrap; gap: 6px }
.missing-tag { font-size: var(--text-caption, 12px); padding: 2px 8px; border-radius: var(--radius-tag, 4px); background: var(--color-warning-bg); color: var(--color-warning, #B54708); font-family: 'SF Mono', 'Consolas', monospace }

/* 证据列表 */ .evidence-list { display: flex; flex-direction: column; gap: 4px }
.evidence-item { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border-radius: var(--radius-tag, 4px); background: var(--color-bg-surface-secondary, #F1F4F8) }
.evidence-input { font-size: var(--text-caption, 12px); font-family: 'SF Mono', 'Consolas', monospace; color: var(--color-text-secondary, #4B5563); min-width: 100px }
.evidence-value { flex: 1; font-size: var(--text-caption, 12px); font-weight: 500; color: var(--color-text-primary, #111827) }
.evidence-source { font-size: var(--text-caption, 12px); color: var(--color-text-tertiary, #9CA3AF) }

/* 按钮 */ .btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; font-size: var(--text-caption, 12px); font-weight: 500; border-radius: var(--radius-tag, 4px); cursor: pointer; transition: all 0.15s; border: 1px solid transparent }
.btn--sm { padding: 3px 8px; font-size: var(--text-caption, 12px) }
.btn--outline { background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); border-color: var(--color-border, #E5E7EB) }
.btn--outline:hover { background: var(--color-bg-surface-secondary, #F1F4F8) }

/* 加载和空状态 */ .loading-state, .empty-state, .error-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 40px 20px; text-align: center }
.spinner { width: 24px; height: 24px; border: 2px solid var(--color-border, #E5E7EB); border-top-color: var(--color-primary, #2F6FED); border-radius: 50%; animation: spin 0.8s linear infinite }

@keyframes spin {to { transform: rotate(360deg) }

}
.empty-icon, .error-icon { font-size: 32px; opacity: 0.6 }
.empty-text, .error-text { font-size: var(--text-body, 13px); font-weight: 500; color: var(--color-text-primary, #111827) }
.error-state .error-icon { opacity: 1 }
.error-state .error-text { color: var(--color-danger, #D92D20) }

/* 响应式 */

@media (max-width: 1024px) {.content-grid { grid-template-columns: 1fr 300px }
.panel--left { display: none }

}

@media (max-width: 768px) {.content-grid { grid-template-columns: 1fr }
.panel--right { display: none }

}

</style>
