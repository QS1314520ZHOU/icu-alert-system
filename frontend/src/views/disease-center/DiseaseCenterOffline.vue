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
          <div class="package-icon">{{ packageIcon(pkg.package_type) }}</div>
          <div class="package-info">
            <h4 class="package-name">{{ pkg.name }}</h4>
            <span class="package-type">{{ pkg.package_type }}</span>
          </div>
          <span :class="['status-badge', `status-badge--${pkg.status}`]">{{ statusText(pkg.status) }}</span>
        </div>

        <div class="package-body">
          <div class="package-versions">
            <div class="version-item">
              <span class="version-label">包版本</span>
              <span class="version-value">{{ pkg.version }}</span>
            </div>
            <div v-if="pkg.source_version" class="version-item">
              <span class="version-label">源版本</span>
              <span class="version-value">{{ pkg.source_version }}</span>
            </div>
          </div>

          <div class="package-meta">
            <div class="meta-item">
              <span class="meta-label">SHA-256</span>
              <span class="meta-value meta-value--code">{{ pkg.sha256?.substring(0, 16) }}...</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">大小</span>
              <span class="meta-value">{{ formatFileSize(pkg.file_size || 0) }}</span>
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
          <button class="btn btn--primary" :disabled="uploading" @click="uploadPackage">
            {{ uploading ? '登记中...' : '上传并验证' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  getOfflinePackages,
  createOfflinePackage,
  buildOfflinePackage,
  publishOfflinePackage,
} from '../../api/diseaseCenter'

// 状态
const showUpload = ref(false)
const uploadForm = ref({ type: 'icd', signature: '' })
const selectedFile = ref<File | null>(null)
const uploading = ref(false)

// 包数据
interface OfflinePackage {
  id: string
  name: string
  package_type?: string  // icd, terminology, guidelines, model, embedding, vector
  version?: string
  source_version?: string
  sha256?: string
  file_size?: number
  status: string
  uploaded_at?: string
  uploaded_by?: string
  diff_summary?: string
  impact_summary?: string
}

const packages = ref<OfflinePackage[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

// 包类型图标
function packageIcon(type?: string) {
  const icons: Record<string, string> = {
    'icd': '📋',
    'terminology': '📖',
    'guidelines': '📚',
    'model': '🤖',
    'embedding': '🔢',
    'vector': '🗂️',
  }
  return type ? (icons[type] || '📦') : '📦'
}

// 格式化文件大小
function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

// 状态文本
function statusText(status: string) {
  const map: Record<string, string> = { draft: '草稿', validating: '验证中', building: '构建中', built: '已构建', published: '已发布', deprecated: '已废弃', rollback: '已回滚' }
  return map[status] || status
}

// 验证包
function verifyPackage(_pkg: OfflinePackage) {
  message.info('后端暂未提供离线包验证接口')
}

// 发布包（后端要求先构建再发布）
function publishPackage(pkg: OfflinePackage) {
  Modal.confirm({
    title: '发布确认',
    content: `确认发布 ${pkg.name} ${pkg.version}？将先构建再发布。`,
    okText: '确认',
    cancelText: '取消',
    async onOk() {
      try {
        await buildOfflinePackage(pkg.id)
        await publishOfflinePackage(pkg.id)
        message.success('发布成功')
        await loadPackages()
      } catch (e: any) {
        message.error('发布失败: ' + (e?.message || '未知错误'))
        throw e
      }
    },
  })
}

// 回滚包
function rollbackPackage(_pkg: OfflinePackage) {
  message.info('后端暂未提供离线包回滚接口')
}

// 差异预览
function previewDiff(pkg: OfflinePackage) {
  const rows: Array<[string, string]> = [
    ['包名称', pkg.name],
    ['包版本', pkg.version || '-'],
    ['源版本', pkg.source_version || '-'],
    ['状态', statusText(pkg.status)],
    ['SHA-256', pkg.sha256 || '-'],
    ['差异摘要', pkg.diff_summary || '暂无差异摘要数据'],
    ['影响摘要', pkg.impact_summary || '暂无影响摘要数据'],
  ]
  Modal.info({
    title: `差异预览 - ${pkg.name}`,
    content: () =>
      h(
        'div',
        rows.map(([k, v]) =>
          h('div', { style: 'display:flex;gap:8px;margin-bottom:6px;' }, [
            h('span', { style: 'min-width:70px;color:#667085;flex-shrink:0;' }, k),
            h('span', { style: 'word-break:break-all;' }, v),
          ])
        )
      ),
    okText: '关闭',
    width: 520,
  })
}

// 文件选择
function onFileSelect(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  selectedFile.value = file || null
  if (file) {
    message.info(`已选择文件: ${file.name}`)
  }
}

// 上传包（登记包信息）
async function uploadPackage() {
  if (!selectedFile.value) {
    message.warning('请先选择文件')
    return
  }
  uploading.value = true
  try {
    await createOfflinePackage({
      name: selectedFile.value.name,
      package_type: uploadForm.value.type,
      signature: uploadForm.value.signature || '',
    })
    showUpload.value = false
    selectedFile.value = null
    message.success('离线包信息已登记（后端暂无文件传输接口，文件内容未上传）')
    await loadPackages()
  } catch (e: any) {
    message.error('登记失败: ' + (e?.message || '未知错误'))
  } finally {
    uploading.value = false
  }
}

// 加载数据
async function loadPackages() {
  loading.value = true
  error.value = null

  try {
    const { data } = await getOfflinePackages()
    packages.value = Array.isArray(data) ? data : []
  } catch (e: any) {
    error.value = e?.message || '获取离线包列表失败，请稍后重试'
    packages.value = []
  } finally {
    loading.value = false
  }
}

// 初始化
onMounted(() => {
  loadPackages()
})
</script>

<style scoped>.offline-page { display: flex; flex-direction: column; gap: 20px }

/* 工具栏 */ .toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 16px 20px; background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-md, 6px); border: 1px solid var(--color-border, #E5E7EB) }
.toolbar__title { font-size: var(--text-section-title, 15px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 }
.toolbar__hint { font-size: var(--text-body, 13px); color: var(--color-text-secondary, #4B5563); margin-top: 2px }

/* 包网格 */ .packages-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 16px }

/* 包卡片 */ .package-card { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px solid var(--color-border, #E5E7EB); overflow: hidden; transition: all 0.15s }
.package-card:hover { border-color: var(--color-primary, #2F6FED) }
.package-header { display: flex; align-items: center; gap: 12px; padding: 16px; border-bottom: 1px solid var(--color-divider, #F0F2F5) }
.package-icon { font-size: 28px }
.package-info { flex: 1; min-width: 0 }
.package-name { font-size: var(--text-body, 13px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 }
.package-type { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }

/* 状态徽章 */ .status-badge { display: inline-flex; padding: 2px 8px; font-size: var(--text-caption, 12px); font-weight: 500; border-radius: var(--radius-tag, 4px) }
.status-badge--published { color: var(--color-success, #16845B); background: var(--color-success-bg) }
.status-badge--draft { color: var(--color-warning, #B54708); background: var(--color-warning-bg) }
.status-badge--deprecated { color: var(--color-text-secondary, #4B5563); background: var(--color-bg-surface-secondary, #F1F4F8) }
.package-body { padding: 16px }

/* 版本信息 */ .package-versions { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 12px }
.version-item { display: flex; flex-direction: column; gap: 2px }
.version-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563) }
.version-value { font-size: var(--text-body, 13px); font-weight: 500; color: var(--color-text-primary, #111827); font-family: 'SF Mono', 'Consolas', monospace }

/* 元数据 */ .package-meta { display: flex; flex-direction: column; gap: 6px; padding-top: 12px; border-top: 1px solid var(--color-divider, #F0F2F5) }
.meta-item { display: flex; align-items: center; gap: 8px }
.meta-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); min-width: 60px }
.meta-value { font-size: var(--text-caption, 12px); color: var(--color-text-primary, #111827) }
.meta-value--code { font-family: 'SF Mono', 'Consolas', monospace; font-size: var(--text-caption, 12px); padding: 1px 4px; background: var(--color-bg-surface-secondary, #F1F4F8); border-radius: var(--radius-tag, 4px) }

/* 操作栏 */ .package-footer { display: flex; gap: 8px; padding: 12px 16px; background: var(--color-bg-surface-secondary, #F1F4F8); border-top: 1px solid var(--color-divider, #F0F2F5) }

/* 空卡片 */ .empty-card { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 60px 40px; background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); border: 1px dashed var(--color-border, #E5E7EB); grid-column: 1 / -1 }
.empty-icon { font-size: 48px; opacity: 0.4 }
.empty-text { font-size: var(--text-section-title, 15px); font-weight: 500; color: var(--color-text-primary, #111827) }
.empty-hint { font-size: var(--text-body, 13px); color: var(--color-text-secondary, #4B5563) }

/* 弹窗 */ .modal-overlay { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.5); display: flex; align-items: center; justify-content: center; z-index: 1000 }
.modal { background: var(--color-bg-surface, #FFFFFF); border-radius: var(--radius-lg, 10px); width: 480px; max-width: 90vw; max-height: 90vh; display: flex; flex-direction: column; overflow: hidden }
.modal__header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--color-divider, #F0F2F5) }
.modal__title { font-size: var(--text-section-title, 15px); font-weight: 600; color: var(--color-text-primary, #111827); margin: 0 }
.modal__close { background: transparent; border: none; color: var(--color-text-secondary, #4B5563); cursor: pointer; padding: 4px; border-radius: var(--radius-tag, 4px) }
.modal__close:hover { background: var(--color-bg-surface-secondary, #F1F4F8) }
.modal__body { padding: 20px; display: flex; flex-direction: column; gap: 16px }

/* 上传区域 */ .upload-area { display: flex; flex-direction: column; align-items: center; gap: 12px; padding: 40px 20px; border: 2px dashed var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); cursor: pointer; transition: all 0.15s; position: relative }
.upload-area:hover { border-color: var(--color-primary, #2F6FED); background: var(--color-primary-bg) }
.upload-text { font-size: var(--text-body, 13px); color: var(--color-text-primary, #111827); margin: 0 }
.upload-hint { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); margin: 0 }
.upload-input { position: absolute; inset: 0; opacity: 0; cursor: pointer }
.modal__footer { display: flex; justify-content: flex-end; gap: 8px; padding: 16px 20px; border-top: 1px solid var(--color-divider, #F0F2F5) }

/* 表单 */ .form-item { display: flex; flex-direction: column; gap: 6px }
.form-label { font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #4B5563); font-weight: 500 }
.form-input, .form-select { padding: 8px 12px; font-size: var(--text-body, 13px); border: 1px solid var(--color-border, #E5E7EB); border-radius: var(--radius-md, 6px); background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); outline: none }
.form-input:focus, .form-select:focus { border-color: var(--color-primary, #2F6FED) }

/* 按钮 */ .btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 8px 14px; font-size: var(--text-body, 13px); font-weight: 500; border-radius: var(--radius-md, 6px); cursor: pointer; transition: all 0.15s; border: 1px solid transparent; white-space: nowrap }
.btn--sm { padding: 4px 10px; font-size: var(--text-caption, 12px) }
.btn--outline { background: var(--color-bg-surface, #FFFFFF); color: var(--color-text-primary, #111827); border-color: var(--color-border, #E5E7EB) }
.btn--outline:hover { background: var(--color-bg-surface-secondary, #F1F4F8); border-color: var(--color-border-strong, #D1D5DB) }
.btn--primary { background: var(--color-primary, #2F6FED); color: var(--color-text-inverse, #FFFFFF); border-color: var(--color-primary, #2F6FED) }
.btn--primary:hover { background: var(--color-primary-hover, #3B82F6) }

/* 响应式 */

@media (max-width: 768px) {.packages-grid { grid-template-columns: 1fr }
.toolbar { flex-direction: column; align-items: flex-start }

}

</style>
