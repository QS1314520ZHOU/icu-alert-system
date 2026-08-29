<template>
  <div class="offline-page">
    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="toolbar__left">
        <h3 class="toolbar__title">离线知识包管理</h3>
        <span class="toolbar__hint">管理 ICD、术语、指南、模型等离线资源包</span>
      </div>
      <div class="toolbar__right">
        <button class="btn btn--primary" @click="showUpload = true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          上传离线包
        </button>
      </div>
    </div>

    <!-- 包列表 -->
    <div class="packages-grid">
      <div v-for="pkg in packages" :key="pkg.id" class="package-card">
        <div class="package-header">
          <div class="package-icon">{{ packageIcon(pkg.type) }}</div>
          <div class="package-info">
            <h4 class="package-name">{{ pkg.name }}</h4>
            <span class="package-type">{{ pkg.type }}</span>
          </div>
          <span :class="['status-badge', `status-badge--${pkg.status}`]">{{ statusText(pkg.status) }}</span>
        </div>

        <div class="package-body">
          <div class="package-versions">
            <div class="version-item">
              <span class="version-label">包版本</span>
              <span class="version-value">{{ pkg.version }}</span>
            </div>
            <div v-if="pkg.icd_version" class="version-item">
              <span class="version-label">ICD版本</span>
              <span class="version-value">{{ pkg.icd_version }}</span>
            </div>
            <div v-if="pkg.guide_version" class="version-item">
              <span class="version-label">指南版本</span>
              <span class="version-value">{{ pkg.guide_version }}</span>
            </div>
            <div v-if="pkg.model_version" class="version-item">
              <span class="version-label">模型版本</span>
              <span class="version-value">{{ pkg.model_version }}</span>
            </div>
          </div>

          <div class="package-meta">
            <div class="meta-item">
              <span class="meta-label">SHA-256</span>
              <span class="meta-value meta-value--code">{{ pkg.sha256?.substring(0, 16) }}...</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">大小</span>
              <span class="meta-value">{{ pkg.size }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">上传时间</span>
              <span class="meta-value">{{ pkg.uploaded_at }}</span>
            </div>
          </div>
        </div>

        <div class="package-footer">
          <button class="btn btn--sm btn--outline" @click="verifyPackage(pkg)">验证</button>
          <button v-if="pkg.status === 'draft'" class="btn btn--sm btn--primary" @click="publishPackage(pkg)">发布</button>
          <button v-if="pkg.status === 'published'" class="btn btn--sm btn--outline" @click="rollbackPackage(pkg)">回滚</button>
          <button class="btn btn--sm btn--outline" @click="previewDiff(pkg)">差异预览</button>
        </div>
      </div>

      <!-- 空状态 -->
      <div v-if="packages.length === 0" class="empty-card">
        <span class="empty-icon">📦</span>
        <span class="empty-text">暂无离线知识包</span>
        <span class="empty-hint">点击"上传离线包"导入资源</span>
      </div>
    </div>

    <!-- 上传弹窗 -->
    <div v-if="showUpload" class="modal-overlay" @click.self="showUpload = false">
      <div class="modal">
        <div class="modal__header">
          <h3 class="modal__title">上传离线知识包</h3>
          <button class="modal__close" @click="showUpload = false">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div class="modal__body">
          <div class="upload-area">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.4">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <p class="upload-text">拖拽文件到此处，或点击选择文件</p>
            <p class="upload-hint">支持 .tar.gz, .zip 格式，最大 2GB</p>
            <input type="file" class="upload-input" accept=".tar.gz,.zip" @change="onFileSelect" />
          </div>

          <div class="form-item">
            <label class="form-label">包类型</label>
            <select v-model="uploadForm.type" class="form-select">
              <option value="icd">ICD数据</option>
              <option value="terminology">医学术语</option>
              <option value="guidelines">指南文档</option>
              <option value="model">AI模型</option>
              <option value="embedding">Embedding</option>
              <option value="vector">向量索引</option>
            </select>
          </div>

          <div class="form-item">
            <label class="form-label">签名验证（可选）</label>
            <input v-model="uploadForm.signature" class="form-input" type="text" placeholder="输入签名或留空" />
          </div>
        </div>
        <div class="modal__footer">
          <button class="btn btn--outline" @click="showUpload = false">取消</button>
          <button class="btn btn--primary" @click="uploadPackage">上传并验证</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

// 状态
const showUpload = ref(false)
const uploadForm = ref({ type: 'icd', signature: '' })

// 包数据
interface OfflinePackage {
  id: string
  name: string
  type: string
  version: string
  icd_version?: string
  guide_version?: string
  model_version?: string
  prompt_version?: string
  sha256?: string
  size: string
  status: 'draft' | 'published' | 'deprecated'
  uploaded_at: string
}

const packages = ref<OfflinePackage[]>([])

// 模拟数据
const mockPackages: OfflinePackage[] = [
  {
    id: '1',
    name: 'ICD-10/11 标准编码库',
    type: 'ICD数据',
    version: 'v2024.1',
    icd_version: 'ICD-10 v2024',
    sha256: 'a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456',
    size: '45.2 MB',
    status: 'published',
    uploaded_at: '2024-03-15',
  },
  {
    id: '2',
    name: '医学术语同义词库',
    type: '医学术语',
    version: 'v3.2.0',
    sha256: 'b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef12345678',
    size: '12.8 MB',
    status: 'published',
    uploaded_at: '2024-03-10',
  },
  {
    id: '3',
    name: '重症医学指南合集',
    type: '指南文档',
    version: 'v1.5.0',
    guide_version: '2024 Q1',
    sha256: 'c3d4e5f6789012345678901234567890abcdef1234567890abcdef1234567890',
    size: '156.3 MB',
    status: 'published',
    uploaded_at: '2024-03-08',
  },
  {
    id: '4',
    name: '本地 LLM 医学模型',
    type: 'AI模型',
    version: 'v2.1.0',
    model_version: 'Qwen2-7B-Medical',
    sha256: 'd4e5f6789012345678901234567890abcdef1234567890abcdef123456789012',
    size: '4.2 GB',
    status: 'draft',
    uploaded_at: '2024-03-20',
  },
  {
    id: '5',
    name: '医学 Embedding 模型',
    type: 'Embedding',
    version: 'v1.0.0',
    model_version: 'bge-large-zh-v1.5',
    sha256: 'e5f6789012345678901234567890abcdef1234567890abcdef12345678901234',
    size: '1.2 GB',
    status: 'published',
    uploaded_at: '2024-02-28',
  },
]

// 包类型图标
function packageIcon(type: string) {
  const icons: Record<string, string> = {
    'ICD数据': '📋',
    '医学术语': '📖',
    '指南文档': '📚',
    'AI模型': '🤖',
    'Embedding': '🔢',
    '向量索引': '🗂️',
  }
  return icons[type] || '📦'
}

// 状态文本
function statusText(status: string) {
  const map: Record<string, string> = { draft: '草稿', published: '已发布', deprecated: '已废弃' }
  return map[status] || status
}

// 验证包
function verifyPackage(pkg: OfflinePackage) {
  alert(`正在验证 ${pkg.name}...\nSHA-256: ${pkg.sha256?.substring(0, 32)}...`)
}

// 发布包
function publishPackage(pkg: OfflinePackage) {
  if (confirm(`确认发布 ${pkg.name} ${pkg.version}？`)) {
    pkg.status = 'published'
    alert('发布成功')
  }
}

// 回滚包
function rollbackPackage(pkg: OfflinePackage) {
  if (confirm(`确认回滚 ${pkg.name} 到上一版本？`)) {
    alert('回滚功能开发中')
  }
}

// 差异预览
function previewDiff(pkg: OfflinePackage) {
  alert(`差异预览功能开发中\n包: ${pkg.name}\n版本: ${pkg.version}`)
}

// 文件选择
function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) {
    alert(`已选择文件: ${file.name}\n大小: ${(file.size / 1024 / 1024).toFixed(2)} MB`)
  }
}

// 上传包
function uploadPackage() {
  alert('上传功能开发中')
  showUpload.value = false
}

// 初始化
onMounted(() => {
  packages.value = mockPackages
})
</script>

<style scoped>
.offline-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
}

.toolbar__title { font-size: 16px; font-weight: 600; color: var(--color-text-primary, #18212B); margin: 0; }
.toolbar__hint { font-size: 13px; color: var(--color-text-secondary, #667085); margin-top: 2px; }

/* 包网格 */
.packages-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 16px;
}

/* 包卡片 */
.package-card {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  overflow: hidden;
  transition: all 0.15s;
}

.package-card:hover {
  border-color: var(--color-primary, #2563EB);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.08);
}

.package-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.package-icon { font-size: 28px; }
.package-info { flex: 1; min-width: 0; }
.package-name { font-size: 14px; font-weight: 600; color: var(--color-text-primary, #18212B); margin: 0; }
.package-type { font-size: 12px; color: var(--color-text-secondary, #667085); }

/* 状态徽章 */
.status-badge { display: inline-flex; padding: 2px 8px; font-size: 11px; font-weight: 500; border-radius: 4px; }
.status-badge--published { color: var(--color-success, #16845B); background: rgba(22, 132, 91, 0.1); }
.status-badge--draft { color: var(--color-warning, #B54708); background: rgba(181, 71, 8, 0.1); }
.status-badge--deprecated { color: var(--color-text-secondary, #667085); background: var(--color-bg-surface-secondary, #F1F3F5); }

.package-body { padding: 16px; }

/* 版本信息 */
.package-versions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 12px;
}

.version-item { display: flex; flex-direction: column; gap: 2px; }
.version-label { font-size: 11px; color: var(--color-text-secondary, #667085); }
.version-value { font-size: 13px; font-weight: 500; color: var(--color-text-primary, #18212B); font-family: 'SF Mono', 'Consolas', monospace; }

/* 元数据 */
.package-meta { display: flex; flex-direction: column; gap: 6px; padding-top: 12px; border-top: 1px solid #f0f0f0; }
.meta-item { display: flex; align-items: center; gap: 8px; }
.meta-label { font-size: 11px; color: var(--color-text-secondary, #667085); min-width: 60px; }
.meta-value { font-size: 12px; color: var(--color-text-primary, #18212B); }
.meta-value--code { font-family: 'SF Mono', 'Consolas', monospace; font-size: 11px; padding: 1px 4px; background: var(--color-bg-surface-secondary, #F1F3F5); border-radius: 3px; }

/* 操作栏 */
.package-footer {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-top: 1px solid #f0f0f0;
}

/* 空卡片 */
.empty-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 40px;
  background: #fff;
  border-radius: 8px;
  border: 1px dashed var(--color-border, #E3E7EC);
  grid-column: 1 / -1;
}

.empty-icon { font-size: 48px; opacity: 0.4; }
.empty-text { font-size: 16px; font-weight: 500; color: var(--color-text-primary, #18212B); }
.empty-hint { font-size: 13px; color: var(--color-text-secondary, #667085); }

/* 弹窗 */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: #fff;
  border-radius: 12px;
  width: 480px;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
}

.modal__title { font-size: 16px; font-weight: 600; color: var(--color-text-primary, #18212B); margin: 0; }

.modal__close { background: transparent; border: none; color: var(--color-text-secondary, #667085); cursor: pointer; padding: 4px; border-radius: 4px; }
.modal__close:hover { background: var(--color-bg-surface-secondary, #F1F3F5); }

.modal__body { padding: 20px; display: flex; flex-direction: column; gap: 16px; }

/* 上传区域 */
.upload-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 20px;
  border: 2px dashed var(--color-border, #E3E7EC);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}

.upload-area:hover { border-color: var(--color-primary, #2563EB); background: rgba(37, 99, 235, 0.02); }

.upload-text { font-size: 14px; color: var(--color-text-primary, #18212B); margin: 0; }
.upload-hint { font-size: 12px; color: var(--color-text-secondary, #667085); margin: 0; }

.upload-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid #f0f0f0;
}

/* 表单 */
.form-item { display: flex; flex-direction: column; gap: 6px; }
.form-label { font-size: 12px; color: var(--color-text-secondary, #667085); font-weight: 500; }
.form-input, .form-select { padding: 8px 12px; font-size: 13px; border: 1px solid var(--color-border, #D0D5DD); border-radius: 6px; background: #fff; color: var(--color-text-primary, #18212B); outline: none; }
.form-input:focus, .form-select:focus { border-color: var(--color-primary, #2563EB); }

/* 按钮 */
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 14px; font-size: 13px; font-weight: 500; border-radius: 6px; cursor: pointer; transition: all 0.15s; border: 1px solid transparent; white-space: nowrap; }
.btn--sm { padding: 4px 10px; font-size: 12px; }
.btn--outline { background: #fff; color: var(--color-text-primary, #18212B); border-color: var(--color-border, #D0D5DD); }
.btn--outline:hover { background: var(--color-bg-surface-secondary, #F9FAFB); border-color: #B0B8C4; }
.btn--primary { background: var(--color-primary, #2563EB); color: #fff; border-color: var(--color-primary, #2563EB); }
.btn--primary:hover { background: #1D4FD8; }

/* 响应式 */
@media (max-width: 768px) {
  .packages-grid { grid-template-columns: 1fr; }
  .toolbar { flex-direction: column; align-items: flex-start; }
}
</style>
