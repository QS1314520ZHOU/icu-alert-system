<template>
  <div class="diseases-page">
    <!-- 筛选栏 -->
    <div class="filter-bar">
      <div class="search-box">
        <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input v-model="searchQuery" class="search-input" type="text" placeholder="搜索病种名称、ICD编码..." @input="onSearch" />
      </div>
      <div class="filter-group">
        <select v-model="selectedStatus" class="filter-select" @change="onSearch">
          <option value="">全部状态</option>
          <option value="draft">草稿</option>
          <option value="published">已发布</option>
          <option value="review_pending">待审核</option>
          <option value="approved">已批准</option>
        </select>
        <select v-model="selectedVersion" class="filter-select" @change="onSearch">
          <option value="">全部版本</option>
          <option value="v1">v1.x</option>
          <option value="v2">v2.x</option>
        </select>
      </div>
    </div>

    <!-- 三栏布局 -->
    <div class="content-grid">
      <!-- 左栏：分类树 -->
      <div class="panel panel--left">
        <div class="panel__header">
          <h3 class="panel__title">ICU专科分类</h3>
        </div>
        <div class="panel__body">
          <div class="category-tree">
            <div
              v-for="cat in categories"
              :key="cat.id"
              :class="['tree-item', { 'tree-item--active': selectedCategory === cat.id }]"
              @click="selectCategory(cat.id)"
            >
              <span class="tree-item__icon">{{ cat.icon }}</span>
              <span class="tree-item__name">{{ cat.name }}</span>
              <span class="tree-item__count">{{ getCategoryCount(cat.id) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 中栏：病种列表 -->
      <div class="panel panel--center">
        <div class="panel__header">
          <h3 class="panel__title">病种列表</h3>
          <span class="panel__count">{{ filteredDiseases.length }} 个</span>
        </div>
        <div class="panel__body">
          <div v-if="loading" class="loading-state">
            <div class="spinner"></div>
            <span>加载中...</span>
          </div>
          <div v-else-if="error" class="error-state">
            <span class="error-icon">⚠️</span>
            <span class="error-text">{{ error }}</span>
            <button class="btn btn--sm btn--outline" @click="onSearch">重试</button>
          </div>
          <div v-else-if="filteredDiseases.length === 0" class="empty-state">
            <span class="empty-icon">📁</span>
            <span class="empty-text">暂无病种数据</span>
          </div>
          <div v-else class="disease-list">
            <div
              v-for="disease in filteredDiseases"
              :key="disease.id"
              :class="['disease-item', { 'disease-item--active': selectedDisease?.id === disease.id }]"
              @click="selectDisease(disease)"
            >
              <div class="disease-item__main">
                <div class="disease-item__name">{{ disease.name }}</div>
                <div class="disease-item__codes">
                  <span v-for="code in disease.icd10_codes" :key="code" class="code-tag">ICD-10: {{ code }}</span>
                  <span v-for="code in disease.icd11_codes" :key="code" class="code-tag">ICD-11: {{ code }}</span>
                </div>
              </div>
              <div class="disease-item__meta">
                <span :class="['status-badge', `status-badge--${disease.status}`]">{{ statusText(disease.status) }}</span>
                <span class="meta-version">{{ disease.version }}</span>
                <span class="meta-rules">{{ disease.rules_count || 0 }} 条规则</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右栏：病种详情 -->
      <div class="panel panel--right">
        <div class="panel__header">
          <h3 class="panel__title">病种详情</h3>
          <button v-if="selectedDisease" class="btn btn--sm btn--primary" @click="editDisease">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
            编辑
          </button>
        </div>
        <div class="panel__body">
          <div v-if="!selectedDisease" class="empty-state">
            <span class="empty-icon">👈</span>
            <span class="empty-text">选择左侧病种查看详情</span>
          </div>
          <div v-else class="disease-detail">
            <!-- 基本信息 -->
            <div class="detail-section">
              <h4 class="section-title">基本信息</h4>
              <div class="detail-row">
                <span class="detail-label">病种名称</span>
                <span class="detail-value detail-value--name">{{ selectedDisease.name }}</span>
              </div>
              <div v-if="selectedDisease.english_name" class="detail-row">
                <span class="detail-label">英文名称</span>
                <span class="detail-value">{{ selectedDisease.english_name }}</span>
              </div>
              <div v-if="selectedDisease.icd10_codes?.length" class="detail-row">
                <span class="detail-label">ICD-10</span>
                <span class="detail-value detail-value--code">{{ selectedDisease.icd10_codes.join(', ') }}</span>
              </div>
              <div v-if="selectedDisease.icd11_codes?.length" class="detail-row">
                <span class="detail-label">ICD-11</span>
                <span class="detail-value detail-value--code">{{ selectedDisease.icd11_codes.join(', ') }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">分类</span>
                <span class="detail-value">{{ selectedDisease.category_id }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">当前版本</span>
                <span class="detail-value detail-value--code">{{ selectedDisease.version }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">发布状态</span>
                <span :class="['status-badge', `status-badge--${selectedDisease.status}`]">{{ statusText(selectedDisease.status) }}</span>
              </div>
            </div>

            <!-- 定义 -->
            <div v-if="selectedDisease.description" class="detail-section">
              <h4 class="section-title">定义</h4>
              <p class="detail-desc">{{ selectedDisease.description }}</p>
            </div>

            <!-- 诊断标准 -->
            <div v-if="selectedDisease.diagnostic_criteria" class="detail-section">
              <h4 class="section-title">诊断标准</h4>
              <p class="detail-desc">{{ selectedDisease.diagnostic_criteria }}</p>
            </div>

            <!-- 分型分期 -->
            <div v-if="selectedDisease.stages?.length" class="detail-section">
              <h4 class="section-title">分型分期 ({{ selectedDisease.stages.length }})</h4>
              <div class="stage-list">
                <div v-for="stage in selectedDisease.stages" :key="stage.name" class="stage-item">
                  <span class="stage-name">{{ stage.name }}</span>
                  <span class="stage-desc">{{ stage.description }}</span>
                </div>
              </div>
            </div>

            <!-- 治疗原则 -->
            <div v-if="selectedDisease.treatment_principles" class="detail-section">
              <h4 class="section-title">治疗原则</h4>
              <p class="detail-desc">{{ selectedDisease.treatment_principles }}</p>
            </div>

            <!-- 并发症 -->
            <div v-if="selectedDisease.complications?.length" class="detail-section">
              <h4 class="section-title">并发症 ({{ selectedDisease.complications.length }})</h4>
              <div class="synonym-list">
                <span v-for="comp in selectedDisease.complications" :key="comp" class="synonym-tag">{{ comp }}</span>
              </div>
            </div>

            <!-- 推荐检查 -->
            <div v-if="selectedDisease.recommended_tests?.length" class="detail-section">
              <h4 class="section-title">推荐检查 ({{ selectedDisease.recommended_tests.length }})</h4>
              <div class="synonym-list">
                <span v-for="test in selectedDisease.recommended_tests" :key="test" class="synonym-tag">{{ test }}</span>
              </div>
            </div>

            <!-- 影响范围 -->
            <div class="detail-section">
              <h4 class="section-title">影响范围</h4>
              <div class="detail-row">
                <span class="detail-label">关联规则数</span>
                <span class="detail-value">{{ selectedDisease.rules_count || 0 }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">影响患者数</span>
                <span class="detail-value">{{ selectedDisease.patients_count || 0 }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">最后更新</span>
                <span class="detail-value">{{ selectedDisease.updated_at }}</span>
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
import { getDiseases, type Disease } from '../../api/diseaseCenter'

// 扩展病种类型
interface DiseaseExtended extends Disease {
  definition?: string
  diagnostic_criteria?: string
  differential_diagnoses?: string[]
  stages?: Array<{ name: string; description: string }>
  complications?: string[]
  recommended_tests?: string[]
  treatment_principles?: string
  guidelines?: Array<{ id: string; name: string }>
  rules_count?: number
  patients_count?: number
}

// 状态
const loading = ref(false)
const searchQuery = ref('')
const selectedCategory = ref('')
const selectedStatus = ref('')
const selectedVersion = ref('')
const selectedDisease = ref<DiseaseExtended | null>(null)

// 分类数据
const categories = ref([
  { id: 'infection', name: '感染', icon: '🦠' },
  { id: 'respiratory', name: '呼吸', icon: '🫁' },
  { id: 'circulation', name: '循环', icon: '❤️' },
  { id: 'neurology', name: '神经', icon: '🧠' },
  { id: 'nephrology', name: '肾脏', icon: '🫘' },
  { id: 'coagulation', name: '凝血', icon: '🩸' },
  { id: 'digestive', name: '消化', icon: '🏥' },
  { id: 'nutrition', name: '营养', icon: '🍎' },
])

// 计算分类数量
function getCategoryCount(catId: string) {
  return diseases.value.filter(d => d.category_id === catId).length
}

const error = ref<string | null>(null)
const diseases = ref<DiseaseExtended[]>([])

// 过滤后的病种列表
const filteredDiseases = computed(() => {
  let items = diseases.value
  if (selectedCategory.value) {
    items = items.filter((d) => d.category_id === selectedCategory.value)
  }
  if (selectedStatus.value) {
    items = items.filter((d) => d.status === selectedStatus.value)
  }
  return items
})

// 状态文本
function statusText(status?: string) {
  const map: Record<string, string> = {
    draft: '草稿',
    validating: '验证中',
    review_pending: '待审核',
    reviewing: '审核中',
    changes_requested: '需修改',
    approved: '已批准',
    published: '已发布',
    deprecated: '已废弃',
    archived: '已归档',
  }
  return map[status || 'draft'] || '草稿'
}

// 选择分类
function selectCategory(catId: string) {
  selectedCategory.value = selectedCategory.value === catId ? '' : catId
}

// 选择病种
function selectDisease(disease: DiseaseExtended) {
  selectedDisease.value = disease
}

// 编辑病种
function editDisease() {
  // TODO: 实现编辑功能
  message.info('编辑功能开发中')
}

// 搜索
async function onSearch() {
  loading.value = true
  error.value = null

  try {
    const { data } = await getDiseases({
      status: selectedStatus.value || undefined,
      limit: 100,
    })
    // API 返回的是数组，不是 { diseases: [...] }
    let items = Array.isArray(data) ? data : []
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      items = items.filter(
        (d: Disease) =>
          d.name.toLowerCase().includes(q) ||
          d.icd10_codes?.some(code => code.toLowerCase().includes(q)) ||
          d.icd11_codes?.some(code => code.toLowerCase().includes(q))
      )
    }
    diseases.value = items as DiseaseExtended[]
  } catch (e: any) {
    error.value = e?.message || '获取病种列表失败，请稍后重试'
    diseases.value = []
  } finally {
    loading.value = false
  }
}

// 初始化
onMounted(() => {
  onSearch()
})
</script>

<style scoped>
.diseases-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 筛选栏 */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
}

.search-box {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: 6px;
}

.search-icon { color: var(--color-text-secondary, #667085); flex-shrink: 0; }
.search-input { flex: 1; border: none; background: transparent; outline: none; font-size: 13px; color: var(--color-text-primary, #18212B); }
.search-input::placeholder { color: var(--color-text-tertiary, #98A2B3); }

.filter-group { display: flex; gap: 8px; }
.filter-select { padding: 8px 12px; font-size: 13px; border: 1px solid var(--color-border, #D0D5DD); border-radius: 6px; background: #fff; color: var(--color-text-primary, #18212B); cursor: pointer; min-width: 100px; }

/* 三栏布局 */
.content-grid {
  display: grid;
  grid-template-columns: 180px 1fr 340px;
  gap: 16px;
  min-height: 600px;
}

/* 面板 */
.panel { background: #fff; border-radius: 8px; border: 1px solid var(--color-border, #E3E7EC); display: flex; flex-direction: column; overflow: hidden; }
.panel__header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid #f0f0f0; }
.panel__title { font-size: 14px; font-weight: 600; color: var(--color-text-primary, #18212B); margin: 0; }
.panel__count { font-size: 12px; color: var(--color-text-secondary, #667085); }
.panel__body { flex: 1; overflow-y: auto; padding: 12px; }

/* 分类树 */
.category-tree { display: flex; flex-direction: column; gap: 2px; }
.tree-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 6px; cursor: pointer; transition: all 0.15s; }
.tree-item:hover { background: var(--color-bg-surface-secondary, #F1F3F5); }
.tree-item--active { background: rgba(37, 99, 235, 0.08); color: var(--color-primary, #2563EB); }
.tree-item__icon { font-size: 16px; }
.tree-item__name { flex: 1; font-size: 13px; font-weight: 500; }
.tree-item__count { font-size: 11px; color: var(--color-text-secondary, #667085); background: var(--color-bg-surface-secondary, #F1F3F5); padding: 1px 6px; border-radius: 10px; }
.tree-item--active .tree-item__count { background: rgba(37, 99, 235, 0.15); color: var(--color-primary, #2563EB); }

/* 病种列表 */
.disease-list { display: flex; flex-direction: column; gap: 4px; }
.disease-item { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-radius: 6px; cursor: pointer; transition: all 0.15s; border: 1px solid transparent; }
.disease-item:hover { background: var(--color-bg-surface-secondary, #F9FAFB); border-color: var(--color-border, #E3E7EC); }
.disease-item--active { background: rgba(37, 99, 235, 0.06); border-color: rgba(37, 99, 235, 0.2); }
.disease-item__main { display: flex; flex-direction: column; gap: 4px; }
.disease-item__name { font-size: 13px; font-weight: 600; color: var(--color-text-primary, #18212B); }
.disease-item__codes { display: flex; gap: 6px; flex-wrap: wrap; }
.code-tag { font-size: 11px; font-family: 'SF Mono', 'Consolas', monospace; padding: 1px 6px; border-radius: 3px; background: var(--color-bg-surface-secondary, #F1F3F5); color: var(--color-text-secondary, #667085); }
.disease-item__meta { display: flex; align-items: center; gap: 8px; }
.meta-version { font-size: 11px; font-family: 'SF Mono', 'Consolas', monospace; color: var(--color-text-secondary, #667085); }
.meta-rules { font-size: 11px; color: var(--color-text-tertiary, #98A2B3); }

/* 状态徽章 */
.status-badge { display: inline-flex; padding: 2px 8px; font-size: 11px; font-weight: 500; border-radius: 4px; }
.status-badge--published { color: var(--color-success, #16845B); background: rgba(22, 132, 91, 0.1); }
.status-badge--draft { color: var(--color-warning, #B54708); background: rgba(181, 71, 8, 0.1); }
.status-badge--review { color: var(--color-primary, #2563EB); background: rgba(37, 99, 235, 0.1); }

/* 病种详情 */
.disease-detail { display: flex; flex-direction: column; gap: 20px; }
.detail-section { display: flex; flex-direction: column; gap: 10px; }
.section-title { font-size: 13px; font-weight: 600; color: var(--color-text-primary, #18212B); margin: 0; padding-bottom: 6px; border-bottom: 1px solid #f0f0f0; }
.detail-row { display: flex; align-items: center; gap: 12px; }
.detail-label { font-size: 12px; color: var(--color-text-secondary, #667085); min-width: 70px; }
.detail-value { font-size: 13px; color: var(--color-text-primary, #18212B); font-weight: 500; }
.detail-value--name { font-size: 15px; font-weight: 600; }
.detail-value--code { font-family: 'SF Mono', 'Consolas', monospace; font-size: 12px; padding: 1px 6px; background: var(--color-bg-surface-secondary, #F1F3F5); border-radius: 3px; }
.detail-desc { font-size: 13px; color: var(--color-text-secondary, #667085); line-height: 1.6; margin: 0; padding: 10px; background: var(--color-bg-surface-secondary, #F9FAFB); border-radius: 6px; }

/* 同义词 */
.synonym-list { display: flex; flex-wrap: wrap; gap: 6px; }
.synonym-tag { display: inline-flex; padding: 3px 8px; font-size: 12px; border-radius: 4px; background: var(--color-bg-surface-secondary, #F1F3F5); color: var(--color-text-primary, #18212B); border: 1px solid var(--color-border, #E3E7EC); }

/* 分期 */
.stage-list { display: flex; flex-direction: column; gap: 6px; }
.stage-item { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; border-radius: 6px; background: var(--color-bg-surface-secondary, #F9FAFB); }
.stage-name { font-size: 12px; font-weight: 600; color: var(--color-text-primary, #18212B); }
.stage-desc { font-size: 12px; color: var(--color-text-secondary, #667085); }

/* 关联 */
.related-list { display: flex; flex-direction: column; gap: 6px; }
.related-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 4px; background: var(--color-bg-surface-secondary, #F9FAFB); }
.related-icon { font-size: 14px; }
.related-name { font-size: 12px; color: var(--color-text-primary, #18212B); }

/* 按钮 */
.btn { display: inline-flex; align-items: center; gap: 4px; padding: 4px 10px; font-size: 12px; font-weight: 500; border-radius: 4px; cursor: pointer; transition: all 0.15s; border: 1px solid transparent; }
.btn--sm { padding: 3px 8px; font-size: 11px; }
.btn--primary { background: var(--color-primary, #2563EB); color: #fff; border-color: var(--color-primary, #2563EB); }
.btn--primary:hover { background: #1D4FD8; }

/* 加载和空状态 */
.loading-state, .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; padding: 40px 20px; text-align: center; }
.spinner { width: 24px; height: 24px; border: 2px solid var(--color-border, #E3E7EC); border-top-color: var(--color-primary, #2563EB); border-radius: 50%; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.empty-icon { font-size: 32px; opacity: 0.6; }
.empty-text { font-size: 14px; font-weight: 500; color: var(--color-text-primary, #18212B); }

/* 响应式 */
@media (max-width: 1024px) {
  .content-grid { grid-template-columns: 1fr 300px; }
  .panel--left { display: none; }
}

@media (max-width: 768px) {
  .filter-bar { flex-direction: column; }
  .filter-group { width: 100%; }
  .filter-select { flex: 1; }
  .content-grid { grid-template-columns: 1fr; }
  .panel--right { display: none; }
}
</style>
