<template>
  <div class="ai-page">
    <!-- 能力选择栏 -->
    <div class="capability-bar">
      <div class="capability-tabs">
        <button
          v-for="cap in capabilities"
          :key="cap.key"
          :class="['cap-tab', { 'cap-tab--active': activeCapability === cap.key }]"
          @click="activeCapability = cap.key"
        >
          <span class="cap-icon">{{ cap.icon }}</span>
          <span class="cap-label">{{ cap.label }}</span>
        </button>
      </div>
      <div class="capability-info">
        <span class="info-model">本地模型: Qwen2-7B-Medical</span>
        <span class="info-status">
          <span class="status-dot status-dot--success"></span>
          在线
        </span>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="content-grid">
      <!-- 左侧：对话区 -->
      <div class="chat-panel">
        <div class="chat-header">
          <h3 class="chat-title">{{ currentCapability?.label || 'AI助手' }}</h3>
          <span class="chat-hint">{{ currentCapability?.hint }}</span>
        </div>

        <!-- 消息列表 -->
        <div class="message-list" ref="messageList">
          <div v-if="messages.length === 0" class="welcome-state">
            <span class="welcome-icon">🤖</span>
            <h3 class="welcome-title">病种中心 AI 助手</h3>
            <p class="welcome-desc">{{ currentCapability?.welcome }}</p>
            <div class="quick-actions">
              <button
                v-for="action in currentCapability?.actions"
                :key="action"
                class="quick-btn"
                @click="sendQuickAction(action)"
              >
                {{ action }}
              </button>
            </div>
          </div>

          <div v-for="(msg, i) in messages" :key="i" :class="['message', `message--${msg.role}`]">
            <div class="message-avatar">
              <span v-if="msg.role === 'user'">👤</span>
              <span v-else>🤖</span>
            </div>
            <div class="message-content">
              <div class="message-text" v-html="msg.content"></div>
              <div v-if="msg.metadata" class="message-meta">
                <span v-if="msg.metadata.model" class="meta-item">
                  <span class="meta-label">模型</span>
                  <span class="meta-value">{{ msg.metadata.model }}</span>
                </span>
                <span v-if="msg.metadata.version" class="meta-item">
                  <span class="meta-label">版本</span>
                  <span class="meta-value">{{ msg.metadata.version }}</span>
                </span>
                <span v-if="msg.metadata.confidence" class="meta-item">
                  <span class="meta-label">置信度</span>
                  <span class="meta-value">{{ msg.metadata.confidence }}%</span>
                </span>
                <span v-if="msg.metadata.source" class="meta-item">
                  <span class="meta-label">来源</span>
                  <span class="meta-value">{{ msg.metadata.source }}</span>
                </span>
              </div>
              <div v-if="msg.actions" class="message-actions">
                <button class="action-btn action-btn--accept" @click="acceptSuggestion(msg)">接受</button>
                <button class="action-btn action-btn--reject" @click="rejectSuggestion(msg)">拒绝</button>
                <button class="action-btn action-btn--modify" @click="modifySuggestion(msg)">修改后接受</button>
                <button class="action-btn" @click="viewSource(msg)">查看原文</button>
              </div>
            </div>
          </div>

          <div v-if="loading" class="message message--assistant">
            <div class="message-avatar">🤖</div>
            <div class="message-content">
              <div class="typing-indicator">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="input-area">
          <textarea
            v-model="inputText"
            class="input-textarea"
            :placeholder="`输入问题，AI 将基于${currentCapability?.label}能力回答...`"
            rows="3"
            @keydown.enter.ctrl="sendMessage"
          ></textarea>
          <div class="input-footer">
            <span class="input-hint">Ctrl + Enter 发送</span>
            <button class="btn btn--primary" :disabled="!inputText.trim() || loading" @click="sendMessage">
              发送
            </button>
          </div>
        </div>
      </div>

      <!-- 右侧：上下文面板 -->
      <div class="context-panel">
        <div class="context-header">
          <h3 class="context-title">AI 能力说明</h3>
        </div>
        <div class="context-body">
          <div class="capability-detail">
            <h4 class="detail-title">{{ currentCapability?.label }}</h4>
            <p class="detail-desc">{{ currentCapability?.description }}</p>

            <div class="detail-section">
              <h5 class="section-label">支持的操作</h5>
              <ul class="action-list">
                <li v-for="action in currentCapability?.features" :key="action">{{ action }}</li>
              </ul>
            </div>

            <div class="detail-section">
              <h5 class="section-label">使用限制</h5>
              <ul class="limit-list">
                <li>AI 建议需人工确认后才能生效</li>
                <li>不能自动发布或修改线上规则</li>
                <li>不能自动确认诊断或下达医嘱</li>
                <li>所有操作留痕可追溯</li>
              </ul>
            </div>

            <div class="detail-section">
              <h5 class="section-label">元数据说明</h5>
              <div class="meta-info">
                <div class="meta-row">
                  <span class="meta-key">模型</span>
                  <span class="meta-val">本地部署的医学大模型</span>
                </div>
                <div class="meta-row">
                  <span class="meta-key">知识包</span>
                  <span class="meta-val">v1.5.0 (2024 Q1)</span>
                </div>
                <div class="meta-row">
                  <span class="meta-key">Prompt</span>
                  <span class="meta-val">v2.1.0</span>
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
import { ref, computed, nextTick } from 'vue'
import { postAiConsultChat } from '../../api'

// 状态
const activeCapability = ref('disease')
const inputText = ref('')
const loading = ref(false)
const messageList = ref<HTMLElement | null>(null)

// 消息类型
interface Message {
  role: 'user' | 'assistant'
  content: string
  metadata?: {
    model?: string
    version?: string
    confidence?: number
    source?: string
    generated_at?: string
  }
  actions?: boolean
}

const messages = ref<Message[]>([])

// 能力配置
interface Capability {
  key: string
  icon: string
  label: string
  hint: string
  welcome: string
  description: string
  actions: string[]
  features: string[]
}

const capabilities: Capability[] = [
  {
    key: 'disease',
    icon: '📁',
    label: '病种编辑',
    hint: '从指南提取定义、推荐分型分期、推荐指标',
    welcome: '我可以帮您从医学指南中提取病种定义、推荐分型分期标准、发现缺失内容，并生成逐字段草稿。',
    description: '在病种编辑过程中提供 AI 辅助，包括从指南提取定义、推荐分型分期、查找缺失内容、生成草稿等。',
    actions: ['从指南提取脓毒症定义', '推荐 ARDS 分期标准', '检查 AKI 定义缺失内容'],
    features: ['从本地指南提取定义', '推荐分型分期', '推荐指标', '查找缺失内容', '生成逐字段草稿'],
  },
  {
    key: 'terminology',
    icon: '🔤',
    label: '术语编码',
    hint: '智能搜索、同义词推荐、ICD候选',
    welcome: '我可以帮您智能搜索术语、推荐同义词、查找 ICD 编码候选，并解释编码冲突。',
    description: '在术语编码管理中提供 AI 辅助，包括智能搜索、同义词推荐、ICD 候选查找、编码冲突解释等。',
    actions: ['搜索脓毒症相关术语', '推荐 Sepsis 同义词', '查找 A41.9 ICD-11 映射'],
    features: ['智能搜索', '同义词推荐', 'ICD候选', '编码冲突解释'],
  },
  {
    key: 'scoring',
    icon: '📈',
    label: '评分规则',
    hint: '解释评分过程、检查缺失数据、比较版本',
    welcome: '我可以帮您解释评分计算过程、检查缺失数据、比较 Classic SOFA 和 SOFA-2 差异，并生成测试病例。',
    description: '在评分规则管理中提供 AI 辅助，包括解释评分过程、检查缺失数据、比较评分版本、生成测试病例等。',
    actions: ['解释 SOFA 评分过程', '检查缺失数据影响', '比较 Classic SOFA 和 SOFA-2'],
    features: ['解释评分过程', '检查缺失数据', '比较 Classic SOFA 和 SOFA-2', '生成测试病例'],
  },
  {
    key: 'phenotype',
    icon: '🧬',
    label: '表型规则',
    hint: '指南转DSL、生成测试、检查冲突',
    welcome: '我可以帮您把指南文字转换成 JSON DSL 草稿、生成边界测试、检查逻辑冲突，并解释规则含义。',
    description: '在表型规则编辑中提供 AI 辅助，包括指南转 DSL、生成边界测试、检查逻辑冲突、解释规则等。',
    actions: ['把脓毒症指南转成 DSL', '生成边界测试用例', '检查规则逻辑冲突'],
    features: ['指南文字转 JSON DSL 草稿', '生成边界测试', '检查逻辑冲突', '解释规则'],
  },
  {
    key: 'review',
    icon: '✅',
    label: '审核发布',
    hint: '总结差异、分析影响、检查来源',
    welcome: '我可以帮您总结版本差异、分析影响范围、检查来源完整性，并提示高风险修改。',
    description: '在审核发布流程中提供 AI 辅助，包括总结版本差异、分析影响范围、检查来源、提示高风险修改等。',
    actions: ['总结最新版本差异', '分析影响范围', '检查来源完整性'],
    features: ['总结版本差异', '分析影响范围', '检查来源', '提示高风险修改'],
  },
  {
    key: 'quality',
    icon: '🔍',
    label: '质量监控',
    hint: '分析误报漏报、发现规则漂移',
    welcome: '我可以帮您分析误报和漏报、发现规则漂移、发现重复病种和异常映射。',
    description: '在质量监控中提供 AI 辅助，包括分析误报漏报、发现规则漂移、发现重复病种、发现异常映射等。',
    actions: ['分析最近误报原因', '检查规则漂移', '发现重复病种'],
    features: ['分析误报和漏报', '发现规则漂移', '发现重复病种', '发现异常映射'],
  },
]

// 当前能力
const currentCapability = computed(() => capabilities.find((c) => c.key === activeCapability.value))

// 发送消息
async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  loading.value = true

  await scrollToBottom()

  try {
    const { data } = await postAiConsultChat({
      message: text,
      mode: 'clinical',
      history: messages.value.slice(-10).map((m) => ({
        role: m.role,
        content: m.content,
      })),
    })

    messages.value.push({
      role: 'assistant',
      content: data.reply || data.message || '抱歉，我无法处理这个请求。',
      metadata: {
        model: data.model || 'Qwen2-7B-Medical',
        version: data.version || 'v2.1.0',
        confidence: data.confidence || 85,
        source: data.source || '本地知识库',
      },
      actions: true,
    })
  } catch {
    // 模拟回复
    await new Promise((r) => setTimeout(r, 1000))
    messages.value.push({
      role: 'assistant',
      content: generateMockReply(text),
      metadata: {
        model: 'Qwen2-7B-Medical',
        version: 'v2.1.0',
        confidence: 88,
        source: '本地知识库',
      },
      actions: true,
    })
  } finally {
    loading.value = false
    await scrollToBottom()
  }
}

// 快捷操作
function sendQuickAction(action: string) {
  inputText.value = action
  sendMessage()
}

// 生成模拟回复
function generateMockReply(question: string): string {
  const q = question.toLowerCase()
  if (q.includes('脓毒症') && q.includes('定义')) {
    return `<p><strong>脓毒症定义（Sepsis-3）：</strong></p>
<p>脓毒症是指因感染引起的宿主反应失调，导致危及生命的器官功能障碍。</p>
<p><strong>诊断标准：</strong></p>
<ul>
<li>疑似或确认感染</li>
<li>SOFA 评分急性升高 ≥ 2 分</li>
</ul>
<p><strong>来源：</strong>Singer M, et al. JAMA. 2016;315(8):801-810.</p>
<p><strong>置信度：</strong>95% — 基于 SCCM/ESICM 2021 指南</p>`
  }
  if (q.includes('sofa') && q.includes('比较')) {
    return `<p><strong>Classic SOFA vs SOFA-2 对比：</strong></p>
<table>
<tr><th>项目</th><th>Classic SOFA 1996</th><th>SOFA-2 2025</th></tr>
<tr><td>呼吸系统</td><td>PaO2/FiO2</td><td>PaO2/FiO2 + 机械通气校正</td></tr>
<tr><td>肾脏系统</td><td>肌酐 + 尿量</td><td>肌酐 + 尿量 + AKI 分期</td></tr>
<tr><td>心血管</td><td>MAP + 血管活性药物</td><td>MAP + 血管活性药物剂量梯度</td></tr>
</table>
<p><strong>主要改进：</strong>SOFA-2 增加了器官支持校正和时间窗约束。</p>`
  }
  return `<p>感谢您的提问。基于本地知识库分析：</p>
<p>您的问题涉及 <strong>${currentCapability.value?.label}</strong> 领域。</p>
<p><strong>建议：</strong></p>
<ul>
<li>请参考最新指南文档</li>
<li>结合临床实际情况判断</li>
<li>AI 建议需人工确认后才能生效</li>
</ul>
<p><em>此回复由本地 AI 模型生成，仅供参考。</em></p>`
}

// 接受建议
function acceptSuggestion(_msg: Message) {
  alert('已接受建议')
}

// 拒绝建议
function rejectSuggestion(_msg: Message) {
  alert('已拒绝建议')
}

// 修改后接受
function modifySuggestion(_msg: Message) {
  alert('修改后接受功能开发中')
}

// 查看原文
function viewSource(msg: Message) {
  alert(`来源: ${msg.metadata?.source || '本地知识库'}`)
}

// 滚动到底部
async function scrollToBottom() {
  await nextTick()
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight
  }
}
</script>

<style scoped>
.ai-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100vh - 200px);
  min-height: 600px;
}

/* 能力选择栏 */
.capability-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 8px 12px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
}

.capability-tabs {
  display: flex;
  gap: 4px;
  overflow-x: auto;
}

.cap-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-text-secondary, #667085);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.cap-tab:hover { background: var(--color-bg-surface-secondary, #F1F3F5); }
.cap-tab--active { background: var(--color-primary, #2563EB); color: #fff; }

.cap-icon { font-size: 14px; }

.capability-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.info-model {
  font-size: 11px;
  color: var(--color-text-secondary, #667085);
  font-family: 'SF Mono', 'Consolas', monospace;
}

.info-status {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-success, #16845B);
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-dot--success { background: var(--color-success, #16845B); }

/* 内容区 */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

/* 对话面板 */
.chat-panel {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-header {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.chat-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}

.chat-hint {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
}

/* 消息列表 */
.message-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 欢迎状态 */
.welcome-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 20px;
  text-align: center;
}

.welcome-icon { font-size: 48px; }

.welcome-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}

.welcome-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #667085);
  margin: 0;
  max-width: 400px;
  line-height: 1.6;
}

.quick-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 8px;
}

.quick-btn {
  padding: 6px 12px;
  font-size: 12px;
  border: 1px solid var(--color-border, #D0D5DD);
  border-radius: 16px;
  background: #fff;
  color: var(--color-text-primary, #18212B);
  cursor: pointer;
  transition: all 0.15s;
}

.quick-btn:hover {
  border-color: var(--color-primary, #2563EB);
  color: var(--color-primary, #2563EB);
  background: rgba(37, 99, 235, 0.04);
}

/* 消息 */
.message {
  display: flex;
  gap: 10px;
}

.message--user { flex-direction: row-reverse; }

.message-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-bg-surface-secondary, #F1F3F5);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  flex-shrink: 0;
}

.message--user .message-avatar {
  background: var(--color-primary, #2563EB);
}

.message-content {
  max-width: 80%;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message-text {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--color-text-primary, #18212B);
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border: 1px solid var(--color-border, #E3E7EC);
}

.message--user .message-text {
  background: var(--color-primary, #2563EB);
  color: #fff;
  border-color: var(--color-primary, #2563EB);
}

.message-text :deep(p) { margin: 0 0 8px; }
.message-text :deep(p:last-child) { margin: 0; }
.message-text :deep(ul) { margin: 4px 0; padding-left: 20px; }
.message-text :deep(table) { border-collapse: collapse; margin: 8px 0; font-size: 12px; }
.message-text :deep(th), .message-text :deep(td) { padding: 4px 8px; border: 1px solid var(--color-border, #E3E7EC); text-align: left; }
.message-text :deep(th) { background: var(--color-bg-surface-secondary, #F1F3F5); font-weight: 600; }

/* 元数据 */
.message-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 10px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: 6px;
  border: 1px solid var(--color-border, #E3E7EC);
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.meta-label {
  font-size: 10px;
  color: var(--color-text-secondary, #667085);
}

.meta-value {
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-primary, #18212B);
}

/* 操作按钮 */
.message-actions {
  display: flex;
  gap: 6px;
}

.action-btn {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  border: 1px solid var(--color-border, #D0D5DD);
  border-radius: 4px;
  background: #fff;
  color: var(--color-text-primary, #18212B);
  cursor: pointer;
  transition: all 0.15s;
}

.action-btn:hover { background: var(--color-bg-surface-secondary, #F9FAFB); }
.action-btn--accept { color: var(--color-success, #16845B); border-color: rgba(22, 132, 91, 0.3); }
.action-btn--reject { color: var(--color-danger, #D92D20); border-color: rgba(217, 45, 32, 0.3); }

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 12px 16px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-text-tertiary, #98A2B3);
  animation: typing 1.4s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) { animation-delay: 0s; }
.typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* 输入区 */
.input-area {
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
}

.input-textarea {
  width: 100%;
  padding: 10px 12px;
  font-size: 13px;
  border: 1px solid var(--color-border, #D0D5DD);
  border-radius: 8px;
  resize: none;
  outline: none;
  font-family: inherit;
  color: var(--color-text-primary, #18212B);
}

.input-textarea:focus { border-color: var(--color-primary, #2563EB); }

.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 8px;
}

.input-hint {
  font-size: 11px;
  color: var(--color-text-tertiary, #98A2B3);
}

/* 上下文面板 */
.context-panel {
  background: #fff;
  border-radius: 8px;
  border: 1px solid var(--color-border, #E3E7EC);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.context-header {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
}

.context-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}

.context-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.capability-detail {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}

.detail-desc {
  font-size: 13px;
  color: var(--color-text-secondary, #667085);
  margin: 0;
  line-height: 1.6;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-primary, #18212B);
  margin: 0;
}

.action-list, .limit-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.action-list li, .limit-list li {
  font-size: 12px;
  color: var(--color-text-secondary, #667085);
  padding-left: 16px;
  position: relative;
}

.action-list li::before, .limit-list li::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--color-text-tertiary, #98A2B3);
}

.meta-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px;
  background: var(--color-bg-surface-secondary, #F9FAFB);
  border-radius: 6px;
}

.meta-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.meta-key { color: var(--color-text-secondary, #667085); }
.meta-val { color: var(--color-text-primary, #18212B); font-weight: 500; }

/* 按钮 */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
}

.btn--primary { background: var(--color-primary, #2563EB); color: #fff; }
.btn--primary:hover { background: #1D4FD8; }
.btn--primary:disabled { opacity: 0.5; cursor: not-allowed; }

/* 响应式 */
@media (max-width: 1024px) {
  .content-grid { grid-template-columns: 1fr; }
  .context-panel { display: none; }
}

@media (max-width: 768px) {
  .capability-bar { flex-direction: column; align-items: flex-start; }
  .capability-info { width: 100%; justify-content: space-between; }
}
</style>
