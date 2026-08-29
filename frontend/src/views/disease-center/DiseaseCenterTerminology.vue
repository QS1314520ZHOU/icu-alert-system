<template>
  <div class="terminology-page">
    <!-- 搜索和筛选栏 -->
    <div class="filter-bar">
      <div class="search-box">
        <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          v-model="searchQuery"
          class="search-input"
          type="text"
          placeholder="搜索术语、ICD编码、同义词..."
          @input="onSearch"
        />
      </div>
      <div class="filter-group">
        <select v-model="selectedCategory" class="filter-select" @change="onSearch">
          <option value="">全部分类</option>
          <option v-for="cat in categories" :key="cat.id" :value="cat.id">
            {{ cat.name }} ({{ cat.count }})
          </option>
        </select>
        <select v-model="selectedStatus" class="filter-select" @change="onSearch">
          <option value="">全部状态</option>
          <option value="active">已启用</option>
          <option value="draft">草稿</option>
          <option value="deprecated">已废弃</option>
        </select>
      </div>
    </div>

    <!-- 三栏布局 -->
    <div class="content-grid">
      <!-- 左栏：分类树 -->
      <div class="panel panel--left">
        <div class="panel__header">
          <h3 class="panel__title">术语分类</h3>
        </div>
        <div class="panel__body">
          <div class="category-tree">
            <div
              v-for="cat in categories"
              :key="cat.id"
              :class="['tree-item', { 'tree-item--active': selectedCategory === cat.id }]"
              @click="selectCategory(cat.id || '')"
            >
              <span class="tree-item__name">{{ cat.name }}</span>
              <span class="tree-item__count">{{ cat.count }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 中栏：术语列表 -->
      <div class="panel panel--center">
        <div class="panel__header">
          <h3 class="panel__title">术语列表</h3>
          <span class="panel__count">{{ filteredItems.length }} 条</span>
        </div>
        <div class="panel__body">
          <div v-if="loading" class="loading-state">
            <div class="spinner"></div>
            <span>加载中...</span>
          </div>
          <div v-else-if="filteredItems.length === 0" class="empty-state">
            <span class="empty-icon">🔤</span>
            <span class="empty-text">暂无术语数据</span>
            <span class="empty-hint">请尝试调整搜索条件</span>
          </div>
          <div v-else class="term-list">
            <div
              v-for="item in filteredItems"
              :key="item.id"
              :class="['term-item', { 'term-item--active': selectedTerm?.id === item.id }]"
              @click="selectTerm(item)"
            >
              <div class="term-item__main">
                <div class="term-item__name">{{ item.standard_name }}</div>
                <div class="term-item__codes">
                  <span v-if="item.icd10_codes?.length" class="code-tag">ICD-10: {{ item.icd10_codes[0] }}</span>
                  <span v-if="item.icd11_codes?.length" class="code-tag">ICD-11: {{ item.icd11_codes[0] }}</span>
                </div>
              </div>
              <div class="term-item__meta">
                <span v-if="item.category" class="meta-tag">{{ item.category }}</span>
                <span class="meta-info">{{ item.synonyms?.length || 0 }} 个同义词</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 右栏：术语详情 -->
      <div class="panel panel--right">
        <div class="panel__header">
          <h3 class="panel__title">术语详情</h3>
        </div>
        <div class="panel__body">
          <div v-if="!selectedTerm" class="empty-state">
            <span class="empty-icon">👈</span>
            <span class="empty-text">选择左侧术语查看详情</span>
          </div>
          <div v-else class="term-detail">
            <div class="detail-section">
              <h4 class="section-title">基本信息</h4>
              <div class="detail-row">
                <span class="detail-label">标准名称</span>
                <span class="detail-value">{{ selectedTerm.standard_name }}</span>
              </div>
              <div v-if="selectedTerm.english_name" class="detail-row">
                <span class="detail-label">英文名称</span>
                <span class="detail-value">{{ selectedTerm.english_name }}</span>
              </div>
              <div v-if="selectedTerm.abbreviation" class="detail-row">
                <span class="detail-label">缩写</span>
                <span class="detail-value detail-value--code">{{ selectedTerm.abbreviation }}</span>
              </div>
              <div v-if="selectedTerm.icd10_codes?.length" class="detail-row">
                <span class="detail-label">ICD-10</span>
                <span class="detail-value detail-value--code">{{ selectedTerm.icd10_codes.join(', ') }}</span>
              </div>
              <div v-if="selectedTerm.icd11_codes?.length" class="detail-row">
                <span class="detail-label">ICD-11</span>
                <span class="detail-value detail-value--code">{{ selectedTerm.icd11_codes.join(', ') }}</span>
              </div>
              <div v-if="selectedTerm.category" class="detail-row">
                <span class="detail-label">分类</span>
                <span class="detail-value">{{ selectedTerm.category }}</span>
              </div>
              <div v-if="selectedTerm.unit" class="detail-row">
                <span class="detail-label">单位</span>
                <span class="detail-value">{{ selectedTerm.unit }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-label">状态</span>
                <span :class="['status-badge', `status-badge--${selectedTerm.status || 'active'}`]">
                  {{ statusText(selectedTerm.status) }}
                </span>
              </div>
            </div>

            <div v-if="selectedTerm.description" class="detail-section">
              <h4 class="section-title">描述</h4>
              <p class="detail-desc">{{ selectedTerm.description }}</p>
            </div>

            <div v-if="selectedTerm.synonyms?.length" class="detail-section">
              <h4 class="section-title">同义词 ({{ selectedTerm.synonyms.length }})</h4>
              <div class="synonym-list">
                <span v-for="syn in selectedTerm.synonyms" :key="syn" class="synonym-tag">{{ syn }}</span>
              </div>
            </div>

            <div class="detail-section">
              <h4 class="section-title">版本信息</h4>
              <div class="detail-row">
                <span class="detail-label">版本</span>
                <span class="detail-value">{{ selectedTerm.version }}</span>
              </div>
              <div v-if="selectedTerm.source" class="detail-row">
                <span class="detail-label">来源</span>
                <span class="detail-value">{{ selectedTerm.source }}</span>
              </div>
              <div v-if="selectedTerm.updated_at" class="detail-row">
                <span class="detail-label">最后更新</span>
                <span class="detail-value">{{ selectedTerm.updated_at }}</span>
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
import {
  getTerminologies,
  getTerminologyCategories,
  type TerminologyItem,
  type TerminologyCategory,
} from '../../api/diseaseCenter'

// 状态
const searchQuery = ref('')
const selectedCategory = ref('')
const selectedStatus = ref('')
const selectedTerm = ref<TerminologyItem | null>(null)

// 数据
const categories = ref<TerminologyCategory[]>([])
const termItems = ref<TerminologyItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

// 过滤后的列表
const filteredItems = computed(() => {
  let items = termItems.value
  if (selectedStatus.value) {
    items = items.filter((item) => item.status === selectedStatus.value)
  }
  return items
})

// 状态文本
function statusText(status?: string) {
  const map: Record<string, string> = {
    active: '已启用',
    draft: '草稿',
    deprecated: '已废弃',
  }
  return map[status || 'active'] || '已启用'
}

// 选择分类
function selectCategory(catId: string) {
  selectedCategory.value = selectedCategory.value === catId ? '' : catId
  onSearch()
}

// 选择术语
function selectTerm(item: TerminologyItem) {
  selectedTerm.value = item
}

// 搜索
async function onSearch() {
  loading.value = true
  error.value = null

  try {
    const { data } = await getTerminologies({
      keyword: searchQuery.value || undefined,
      category: selectedCategory.value || undefined,
      limit: 50,
    })
    termItems.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    error.value = e?.message || '搜索术语失败，请稍后重试'
    termItems.value = []
  } finally {
    loading.value = false
  }
}

// 初始化
onMounted(async () => {
  // 加载分类
  try {
    const { data } = await getTerminologyCategories()
    categories.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    message.error(e?.message || '获取术语分类失败')
  }

  // 加载术语列表
  await onSearch()
})
</script>

<style scoped>
.terminology-page {
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

.search-icon {
  color: var(--color-text-secondary, #667085);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 13px;
  color: var(--color-text-primary, #18212B);
}

.search-input::placeholder {
  color: var(--color-text-tertiary, #98A2B3);
}

.filter-group {
  display: flex;
  gap: 8px;
}

.filter-select {
  padding: 8px 12px;
  font-size: 13px;
  border: 1px solid var(--color-border, #D0D5DD);
  border-radius: 6px;
  background: #fff;
  color: var(--color-text-primary, #18212B);
  cursor: pointer;
  min-width: 120px;
}

/* 三栏布局 */
.content-grid {
  display: grid;
  grid-template-columns: 200px 1fr 320px;
  gap: 16px;
  min-height: 600px;
}

/* 面板 */
.panel {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.panel__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}

.panel__count {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

.panel__body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

/* 分类树 */
.category-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tree-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.tree-item:hover {
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

.tree-item--active {
  background: rgba(37, 99, 235, 0.08);
  color: var(--color-primary, #2563EB);
}

.tree-item__name {
  font-size: 13px;
  font-weight: 500;
}

.tree-item__count {
  font-size: 11px;
  color: var(--color-text-secondary, #667085);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  padding: 1px 6px;
  border-radius: 10px;
}

.tree-item--active .tree-item__count {
  background: rgba(37, 99, 235, 0.15);
  color: var(--color-primary, #2563EB);
}

/* 术语列表 */
.term-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.term-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.term-item:hover {
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-color: var(--color-border, #E3E7EC);
}

.term-item--active {
  background: rgba(37, 99, 235, 0.06);
  border-color: rgba(37, 99, 235, 0.2);
}

.term-item__main {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.term-item__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
}

.term-item__codes {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.code-tag {
  font-size: 11px;
  font-family: 'SF Mono', 'Consolas', monospace;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  color: var(--color-text-secondary, #667085);
}

.term-item__meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.meta-tag {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(37, 99, 235, 0.08);
  color: var(--color-primary, #2563EB);
}

.meta-info {
  font-size: 11px;
  color: var(--color-text-tertiary, #98A2B3);
}

/* 术语详情 */
.term-detail {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
  padding-bottom: 6px;
  border-bottom: 1px solid #f0f0f0;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-label {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  min-width: 70px;
}

.detail-value {
  font-size: 13px;
  color: var(--color-text-primary, #18212B);
  font-weight: 500;
}

.detail-value--code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
  padding: 1px 6px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border-radius: 3px;
}

/* 状态徽章 */
.status-badge {
  display: inline-flex;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
}

.status-badge--active {
  color: var(--color-success, #16845B);
  background: rgba(22, 132, 91, 0.1);
}

.status-badge--draft {
  color: var(--color-warning, #B54708);
  background: rgba(181, 71, 8, 0.1);
}

.status-badge--deprecated {
  color: var(--color-text-secondary, #667085);
  background: var(--color-bg-surface-secondary, #F1F3F5);
}

/* 同义词 */
.synonym-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.synonym-tag {
  display: inline-flex;
  padding: 3px 8px;
  font-size: 12px;
  border-radius: 4px;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  color: var(--color-text-primary, #18212B);
  border: 1px solid var(--color-border, #E3E7EC);
}

/* 关联病种 */
.related-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.related-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: 4px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
}

.related-icon {
  font-size: 14px;
}

.related-name {
  font-size: 12px;
  color: var(--color-text-primary, #18212B);
}

/* 加载和空状态 */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 20px;
  text-align: center;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border, #E3E7EC);
  border-top-color: var(--color-primary, #2563EB);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-icon {
  font-size: 32px;
  opacity: 0.6;
}

.empty-text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

.empty-hint {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

/* 响应式 */
@media (max-width: 1024px) {
  .content-grid {
    grid-template-columns: 1fr 280px;
  }

  .panel--left {
    display: none;
  }
}

@media (max-width: 768px) {
  .filter-bar {
    flex-direction: column;
  }

  .filter-group {
    width: 100%;
  }

  .filter-select {
    flex: 1;
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .panel--right {
    display: none;
  }
}
</style>
