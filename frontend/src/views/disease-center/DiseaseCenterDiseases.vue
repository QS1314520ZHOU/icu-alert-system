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
          <option value="published">已发布</option>
          <option value="draft">草稿</option>
          <option value="review">审核中</option>
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
              <span class="tree-item__count">{{ cat.count }}</span>
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
                  <span v-if="disease.icd10" class="code-tag">ICD-10: {{ disease.icd10 }}</span>
                  <span v-if="disease.icd11" class="code-tag">ICD-11: {{ disease.icd11 }}</span>
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
              <div v-if="selectedDisease.icd10" class="detail-row">
                <span class="detail-label">ICD-10</span>
                <span class="detail-value detail-value--code">{{ selectedDisease.icd10 }}</span>
              </div>
              <div v-if="selectedDisease.icd11" class="detail-row">
                <span class="detail-label">ICD-11</span>
                <span class="detail-value detail-value--code">{{ selectedDisease.icd11 }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">分类</span>
                <span class="detail-value">{{ selectedDisease.category }}</span>
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

            <!-- 同义词 -->
            <div v-if="selectedDisease.synonyms?.length" class="detail-section">
              <h4 class="section-title">同义词 ({{ selectedDisease.synonyms.length }})</h4>
              <div class="synonym-list">
                <span v-for="syn in selectedDisease.synonyms" :key="syn" class="synonym-tag">{{ syn }}</span>
              </div>
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

            <!-- 关联评分 -->
            <div v-if="selectedDisease.related_scores?.length" class="detail-section">
              <h4 class="section-title">关联评分 ({{ selectedDisease.related_scores.length }})</h4>
              <div class="related-list">
                <div v-for="score in selectedDisease.related_scores" :key="score.id" class="related-item">
                  <span class="related-icon">📈</span>
                  <span class="related-name">{{ score.name }}</span>
                </div>
              </div>
            </div>

            <!-- 关联规则 -->
            <div v-if="selectedDisease.related_rules?.length" class="detail-section">
              <h4 class="section-title">关联规则 ({{ selectedDisease.related_rules.length }})</h4>
              <div class="related-list">
                <div v-for="rule in selectedDisease.related_rules" :key="rule.id" class="related-item">
                  <span class="related-icon">🧬</span>
                  <span class="related-name">{{ rule.name }}</span>
                </div>
              </div>
            </div>

            <!-- 关联指南 -->
            <div v-if="selectedDisease.guidelines?.length" class="detail-section">
              <h4 class="section-title">关联指南 ({{ selectedDisease.guidelines.length }})</h4>
              <div class="related-list">
                <div v-for="guide in selectedDisease.guidelines" :key="guide.id" class="related-item">
                  <span class="related-icon">📚</span>
                  <span class="related-name">{{ guide.name }}</span>
                </div>
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
import { getDiseases, type Disease } from '../../api/diseaseCenter'

// 扩展病种类型
interface DiseaseExtended extends Disease {
  description?: string
  stages?: Array<{ name: string; description: string }>
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
  { id: 'infection', name: '感染', icon: '🦠', count: 32 },
  { id: 'respiratory', name: '呼吸', icon: '🫁', count: 28 },
  { id: 'circulation', name: '循环', icon: '❤️', count: 24 },
  { id: 'neurology', name: '神经', icon: '🧠', count: 18 },
  { id: 'nephrology', name: '肾脏', icon: '🫘', count: 16 },
  { id: 'coagulation', name: '凝血', icon: '🩸', count: 12 },
  { id: 'digestive', name: '消化', icon: '🏥', count: 14 },
  { id: 'nutrition', name: '营养', icon: '🍎', count: 12 },
])

// 模拟数据
const mockDiseases: DiseaseExtended[] = [
  {
    id: '1',
    name: '脓毒症',
    icd10: 'A41.9',
    icd11: '1G40-1G41',
    category: '感染',
    status: 'published',
    version: 'v2.1.0',
    description: '脓毒症是指因感染引起的宿主反应失调，导致危及生命的器官功能障碍。根据 Sepsis-3 定义，SOFA 评分急性升高 ≥ 2 分提示脓毒症。',
    synonyms: ['Sepsis', '败血症', '全身性感染', '脓毒病'],
    stages: [
      { name: '脓毒症', description: 'SOFA ≥ 2 分' },
      { name: '脓毒性休克', description: '需要血管活性药物维持 MAP ≥ 65 mmHg，且乳酸 > 2 mmol/L' },
    ],
    related_scores: [{ id: 'sofa', name: 'SOFA' }, { id: 'qsofa', name: 'qSOFA' }],
    related_rules: [{ id: 'sep-1', name: 'Sepsis 1h Bundle' }],
    guidelines: [{ id: 'sccm-2021', name: 'SCCM/ESICM 2021 指南' }],
    rules_count: 5,
    patients_count: 1247,
    updated_at: '2024-03-15',
  },
  {
    id: '2',
    name: '急性呼吸窘迫综合征',
    icd10: 'J80',
    icd11: 'CA0Y',
    category: '呼吸',
    status: 'published',
    version: 'v1.3.0',
    description: 'ARDS 是一种急性弥漫性肺部炎症性损伤，导致肺血管通透性增加、肺组织实变和低氧血症。',
    synonyms: ['ARDS', '急性肺损伤', 'Adult Respiratory Distress Syndrome'],
    stages: [
      { name: '轻度', description: '200 < PaO2/FiO2 ≤ 300 mmHg（PEEP ≥ 5 cmH2O）' },
      { name: '中度', description: '100 < PaO2/FiO2 ≤ 200 mmHg（PEEP ≥ 5 cmH2O）' },
      { name: '重度', description: 'PaO2/FiO2 ≤ 100 mmHg（PEEP ≥ 5 cmH2O）' },
    ],
    related_scores: [{ id: 'pao2_fio2', name: 'PaO2/FiO2' }],
    related_rules: [{ id: 'ards-vent', name: 'ARDS 通气策略' }],
    guidelines: [{ id: 'ards-2023', name: 'ARDS 管理指南 2023' }],
    rules_count: 3,
    patients_count: 892,
    updated_at: '2024-03-10',
  },
  {
    id: '3',
    name: '急性肾损伤',
    icd10: 'N17',
    icd11: 'GB60',
    category: '肾脏',
    status: 'published',
    version: 'v1.2.1',
    description: 'AKI 是指肾功能在短时间内（数小时至数天）急剧下降，表现为血肌酐升高和/或尿量减少。',
    synonyms: ['AKI', '急性肾功能衰竭', 'Acute Kidney Injury'],
    stages: [
      { name: 'AKI 1期', description: '血肌酐升高 1.5-1.9 倍或尿量 < 0.5 mL/kg/h 持续 6-12h' },
      { name: 'AKI 2期', description: '血肌酐升高 2.0-2.9 倍或尿量 < 0.5 mL/kg/h 持续 ≥ 12h' },
      { name: 'AKI 3期', description: '血肌酐升高 ≥ 3.0 倍或尿量 < 0.3 mL/kg/h 持续 ≥ 24h' },
    ],
    related_scores: [{ id: 'kdigo', name: 'KDIGO' }],
    related_rules: [{ id: 'aki-monitor', name: 'AKI 监测规则' }],
    guidelines: [{ id: 'kdigo-2012', name: 'KDIGO AKI 指南 2012' }],
    rules_count: 4,
    patients_count: 756,
    updated_at: '2024-03-08',
  },
  {
    id: '4',
    name: '弥散性血管内凝血',
    icd10: 'D65',
    icd11: '3B20',
    category: '凝血',
    status: 'draft',
    version: 'v1.0.0',
    description: 'DIC 是一种获得性凝血功能紊乱，特征为全身性凝血激活、微血管血栓形成和继发性纤溶亢进。',
    synonyms: ['DIC', '消耗性凝血病', 'Disseminated Intravascular Coagulation'],
    related_scores: [{ id: 'isth-dic', name: 'ISTH DIC 评分' }],
    related_rules: [],
    guidelines: [],
    rules_count: 2,
    patients_count: 534,
    updated_at: '2024-02-28',
  },
  {
    id: '5',
    name: '多器官功能障碍综合征',
    icd10: 'R65.3',
    icd11: 'MG46',
    category: '感染',
    status: 'published',
    version: 'v1.1.0',
    description: 'MODS 是指急性疾病过程中，两个或两个以上器官或系统同时或序贯发生功能障碍。',
    synonyms: ['MODS', '多器官衰竭', 'MOF'],
    stages: [
      { name: '功能障碍', description: '器官功能评分升高但可逆' },
      { name: '功能衰竭', description: '器官功能严重受损，需要支持治疗' },
    ],
    related_scores: [{ id: 'sofa', name: 'SOFA' }, { id: 'apache', name: 'APACHE II' }],
    related_rules: [{ id: 'mods-monitor', name: 'MODS 监测' }],
    guidelines: [],
    rules_count: 3,
    patients_count: 423,
    updated_at: '2024-02-20',
  },
]

const diseases = ref<DiseaseExtended[]>([])

// 过滤后的病种列表
const filteredDiseases = computed(() => {
  let items = diseases.value
  if (selectedCategory.value) {
    const catName = categories.value.find((c) => c.id === selectedCategory.value)?.name
    if (catName) items = items.filter((d) => d.category === catName)
  }
  if (selectedStatus.value) {
    items = items.filter((d) => d.status === selectedStatus.value)
  }
  return items
})

// 状态文本
function statusText(status?: string) {
  const map: Record<string, string> = { published: '已发布', draft: '草稿', review: '审核中' }
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
  // TODO: 进入分步编辑器
  alert('编辑功能开发中')
}

// 搜索
async function onSearch() {
  loading.value = true
  try {
    const { data } = await getDiseases({
      status: selectedStatus.value || undefined,
      limit: 100,
    })
    let items = data.diseases || []
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      items = items.filter(
        (d: Disease) =>
          d.name.toLowerCase().includes(q) ||
          d.icd10?.toLowerCase().includes(q) ||
          d.icd11?.toLowerCase().includes(q)
      )
    }
    diseases.value = items as DiseaseExtended[]
  } catch {
    // 使用模拟数据
    let items = [...mockDiseases]
    if (searchQuery.value) {
      const q = searchQuery.value.toLowerCase()
      items = items.filter(
        (d) =>
          d.name.toLowerCase().includes(q) ||
          d.icd10?.toLowerCase().includes(q) ||
          d.synonyms?.some((s) => s.toLowerCase().includes(q))
      )
    }
    diseases.value = items
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
