<template>
  <div class="voice-rounding">
    <!-- 录音控制区 -->
    <div class="vr-controls">
      <button
        v-if="!recording && !processingStage"
        class="vr-btn vr-btn--start"
        :disabled="loading"
        @click="startRecord"
      >
        <span class="vr-icon">🎤</span>
        <span>开始口述</span>
      </button>
      <button
        v-else-if="recording"
        class="vr-btn vr-btn--stop"
        @click="stopRecord"
      >
        <span class="vr-icon">⏹</span>
        <span>结束并转写</span>
      </button>

      <!-- 录音状态 -->
      <span v-if="recording" class="vr-recording-indicator">
        <span class="vr-dot"></span>
        录音中 {{ formatDuration(recordingDuration) }}
      </span>

      <!-- 处理阶段状态 -->
      <span v-if="processingStage" class="vr-loading">
        {{ processingStageText }}
      </span>

      <!-- 录音设置信息（开发模式） -->
      <details v-if="recordingSettings && isDev" class="vr-dev-info">
        <summary>录音设置</summary>
        <pre>{{ JSON.stringify(recordingSettings, null, 2) }}</pre>
      </details>
    </div>

    <!-- 超时提示 -->
    <div v-if="timeoutWarning" class="vr-timeout-warn">
      ⏰ 录音已达到最大时长（{{ maxRecordingSeconds }}秒），已自动停止。
    </div>

    <!-- 实时字幕（流式模式） -->
    <div v-if="streamingActive || streamDraft" class="vr-live-caption">
      <p class="vr-live-label">实时转写</p>
      <div class="vr-caption-text">
        <span class="vr-committed">{{ committedText }}</span>
        <mark v-if="partialText" class="vr-partial">{{ partialText }}</mark>
      </div>
      <div v-if="sessionState === 'stopping'" class="vr-live-status">
        正在生成最终结果…
      </div>
      <div v-if="sessionState === 'error'" class="vr-stream-error">
        {{ streamErrorMessage }}
        <button v-if="audioCapture" class="vr-btn vr-btn--retry" @click="fallbackToOfflineUpload">
          使用离线录音上传
        </button>
      </div>
    </div>

    <!-- 转写结果区 -->
    <div v-if="draft" class="vr-result">
      <!-- 人工审核警告 -->
      <div v-if="draft.needs_human_review" class="vr-warn">
        <strong>⚠️ 需人工核对（可能涉及数值/剂量）：</strong>
        <ul>
          <li
            v-for="(s, i) in draft.suspect"
            :key="i"
            :class="['vr-suspect-item', suspectClass(s.type)]"
          >
            <span class="vr-suspect-term">{{ s.term }}</span>
            <span v-if="s.note" class="vr-suspect-note"> — {{ s.note }}</span>
          </li>
        </ul>
      </div>

      <!-- 降级提示 -->
      <div v-if="draft.degraded" class="vr-degraded">
        ℹ️ LLM 纠错不可用，已返回规则清洗后的文本。
      </div>

      <!-- 处理信息 -->
      <div v-if="draft.processing" class="vr-processing-info">
        <span>音频格式: {{ draft.processing.source_format || '未知' }}</span>
        <span v-if="draft.duration_seconds"> | 时长: {{ formatDuration(draft.duration_seconds) }}</span>
        <span> | ASR: {{ draft.processing.asr_mode }}</span>
      </div>

      <p class="vr-hint">请核对下方文本，尤其是剂量与数值，确认无误后保存：</p>

      <!-- 可编辑文本区 -->
      <textarea
        v-model="editText"
        class="vr-edit-area"
        rows="10"
        placeholder="转写结果将显示在此处…"
      ></textarea>

      <div class="vr-actions">
        <button
          class="vr-btn vr-btn--confirm"
          :disabled="!editText.trim()"
          @click="confirmText"
        >
          确认入库
        </button>
        <button class="vr-btn vr-btn--cancel" @click="discardDraft">
          放弃
        </button>
        <button class="vr-btn vr-btn--retry" @click="retryRecord">
          重新录音
        </button>
      </div>

      <!-- 原始识别对比 -->
      <details class="vr-raw-details">
        <summary>查看原始识别（对比纠错）</summary>
        <div class="vr-raw-text">
          <div class="vr-raw-label">ASR 原文：</div>
          <pre>{{ draft.raw_text }}</pre>
          <div v-if="draft.cleaned_text !== draft.raw_text" class="vr-raw-label">规则清洗后：</div>
          <pre v-if="draft.cleaned_text !== draft.raw_text">{{ draft.cleaned_text }}</pre>
        </div>
      </details>
    </div>

    <!-- 失败后重试 -->
    <div v-if="errorMessage" class="vr-error">
      <p>{{ errorMessage }}</p>
      <button class="vr-btn vr-btn--retry" @click="retryRecord">重新录音</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import {
  transcribeAudio,
  confirmVoiceRounding,
  getVoiceRoundingCapabilities,
  type VoiceRoundingDraft,
  type VoiceRoundingDraftStream,
  type VoiceRoundingSuspect,
} from '../api/voiceRounding'
import { AudioCapture } from '../audio/captureWorklet'
import {
  VoiceRoundingSession,
  buildVoiceRoundingWsUrl,
  type SessionState,
} from '../services/voiceRoundingSession'

const props = defineProps<{
  patientId: string
}>()

const emit = defineEmits<{
  confirmed: [text: string]
}>()

// 开发模式检测
const isDev = import.meta.env.DEV

// 录音配置
const maxRecordingSeconds = 300

// ── Shared state ──────────────────────────────────────────────────────
const recording = ref(false)
const loading = ref(false)
const draft = ref<VoiceRoundingDraft | null>(null)
const editText = ref('')
const recordingDuration = ref(0)
const timeoutWarning = ref(false)
const errorMessage = ref('')
const processingStage = ref<string | null>(null)
const recordingSettings = ref<Record<string, unknown> | null>(null)

// ── Offline (MediaRecorder) state ─────────────────────────────────────
let mediaRecorder: MediaRecorder | null = null
let mediaStream: MediaStream | null = null
let chunks: Blob[] = []
let durationTimer: number | null = null
let actualMimeType = ''

// ── Streaming state ───────────────────────────────────────────────────
const streamingEnabled = ref(false)
const streamDraft = ref<VoiceRoundingDraftStream | null>(null)
const committedText = ref('')
const partialText = ref('')
const sessionState = ref<SessionState>('idle')
const streamErrorMessage = ref('')
let wsSession: VoiceRoundingSession | null = null
let audioCapture: AudioCapture | null = null
let streamCleanup: (() => void) | null = null

// Derived
const streamingActive = computed(() =>
  sessionState.value === 'ready' ||
  sessionState.value === 'recording' ||
  sessionState.value === 'stopping'
)

// ── Capabilities check on mount ───────────────────────────────────────
getVoiceRoundingCapabilities()
  .then(({ data }) => {
    streamingEnabled.value = data.streaming_enabled
  })
  .catch(() => {
    streamingEnabled.value = false
  })

// 处理阶段文本
const processingStageText = computed(() => {
  switch (processingStage.value) {
    case 'uploading':
      return '正在上传…'
    case 'processing':
      return '正在处理音频…'
    case 'transcribing':
      return '正在识别…'
    default:
      return '处理中…'
  }
})

/**
 * 检测浏览器支持的音频约束。
 * 只传浏览器支持的约束，避免部分浏览器因不支持某项配置而启动录音失败。
 */
function getSupportedAudioConstraints(): MediaTrackConstraints {
  const desired: Record<string, unknown> = {
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
    channelCount: 1,
    sampleRate: 16000,
  }

  const supported = navigator.mediaDevices.getSupportedConstraints()
  const constraints: Record<string, unknown> = {}

  for (const [key, value] of Object.entries(desired)) {
    if (supported[key]) {
      constraints[key] = value
    }
  }

  return constraints as MediaTrackConstraints
}

/**
 * 检测浏览器支持的 MediaRecorder MIME 类型。
 * 按优先级检测，返回第一个支持的类型。
 */
function getSupportedMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
  ]

  for (const mime of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mime)) {
      return mime
    }
  }

  // 浏览器默认格式
  return ''
}

/**
 * MIME 类型对应的文件扩展名。
 */
function getExtensionFromMimeType(mime: string): string {
  if (mime.includes('webm')) return 'webm'
  if (mime.includes('ogg')) return 'ogg'
  if (mime.includes('mp4')) return 'mp4'
  return 'webm' // 默认
}

/**
 * 格式化时长显示。
 */
function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return m > 0 ? `${m}:${String(s).padStart(2, '0')}` : `${s}s`
}

/**
 * suspect 类型对应的 CSS 类。
 */
function suspectClass(type: string): string {
  switch (type) {
    case 'drug_confusable':
    case 'number_override':
      return 'vr-suspect--high'
    case 'unit_uncertain':
      return 'vr-suspect--medium'
    case 'low_confidence':
    case 'dialect_uncertain':
      return 'vr-suspect--low'
    default:
      return 'vr-suspect--other'
  }
}

async function startRecord() {
  // 清掉上一次的状态
  draft.value = null
  streamDraft.value = null
  editText.value = ''
  errorMessage.value = ''
  streamErrorMessage.value = ''
  timeoutWarning.value = false
  processingStage.value = null
  recordingSettings.value = null
  committedText.value = ''
  partialText.value = ''

  // Use streaming if available and AudioWorklet is supported
  if (streamingEnabled.value && typeof AudioWorkletNode !== 'undefined') {
    await startStreaming()
  } else {
    await startOfflineRecord()
  }
}

async function startStreaming() {
  try {
    // 1. Create AudioCapture
    audioCapture = new AudioCapture({
      onPcmChunk: (pcm: ArrayBuffer) => {
        wsSession?.sendPcmChunk(pcm)
      },
      onPcmFinal: (pcm: ArrayBuffer) => {
        wsSession?.sendPcmChunk(pcm)
      },
      onError: (message: string) => {
        streamErrorMessage.value = message
        sessionState.value = 'error'
      },
      onBackupExceeded: () => {
        streamErrorMessage.value = '录音过长，离线备份可能不完整'
      },
    })

    // 2. Create WS session and connect
    sessionState.value = 'connecting'
    wsSession = new VoiceRoundingSession(props.patientId)
    wsSession.connect(buildVoiceRoundingWsUrl(props.patientId))

    // 3. Listen for messages
    streamCleanup = wsSession.onMessage((msg) => {
      switch (msg.type) {
        case 'connected':
          // auto send start after connected (handled by VoiceRoundingSession)
          break
        case 'ready':
          sessionState.value = 'ready'
          break
        case 'partial':
          partialText.value = msg.text // replace, not append
          break
        case 'final_segment':
          if (committedText.value) committedText.value += '。'
          committedText.value += msg.text
          partialText.value = '' // clear the matching partial
          break
        case 'stopped':
          sessionState.value = 'stopping'
          break
        case 'completed':
          sessionState.value = 'completed'
          streamDraft.value = msg.draft
          draft.value = msg.draft
          editText.value = msg.draft.corrected_text || msg.draft.cleaned_text || ''
          streamCleanup?.()
          cleanupStreamResources()
          break
        case 'error':
          sessionState.value = 'error'
          streamErrorMessage.value = msg.message
          break
      }
    })

    // 4. Start audio capture (auto-connects AudioWorklet)
    await audioCapture.start()
    recordingSettings.value = {
      sampleRate: audioCapture.sampleRate,
      channelCount: 1,
      streaming: true,
    }

    recording.value = true
    recordingDuration.value = 0

    // 5. Timer
    durationTimer = window.setInterval(() => {
      recordingDuration.value++
      if (recordingDuration.value >= maxRecordingSeconds) {
        stopRecord()
        timeoutWarning.value = true
      }
    }, 1000)
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    if (message.includes('NotAllowedError') || message.includes('Permission')) {
      errorMessage.value = '无法访问麦克风，请检查浏览器权限设置。'
    } else if (message.includes('NotFoundError')) {
      errorMessage.value = '未检测到麦克风设备。'
    } else {
      // Fallback to offline
      console.warn('流式启动失败，尝试离线模式:', message)
      await startOfflineRecord()
    }
  }
}

async function startOfflineRecord() {
  // 清掉 streaming state
  cleanupStreamResources()

  try {
    const constraints = getSupportedAudioConstraints()
    const stream = await navigator.mediaDevices.getUserMedia({ audio: constraints })

    const track = stream.getAudioTracks()[0]
    if (track) {
      const settings = track.getSettings()
      recordingSettings.value = {
        sampleRate: settings.sampleRate,
        channelCount: settings.channelCount,
        echoCancellation: settings.echoCancellation,
        noiseSuppression: settings.noiseSuppression,
        autoGainControl: settings.autoGainControl,
      }
    }

    actualMimeType = getSupportedMimeType()
    chunks = []
    mediaStream = stream

    const recorderOptions: MediaRecorderOptions = {}
    if (actualMimeType) recorderOptions.mimeType = actualMimeType
    mediaRecorder = new MediaRecorder(stream, recorderOptions)
    actualMimeType = mediaRecorder.mimeType || actualMimeType

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data)
    }

    mediaRecorder.onstop = () => {
      releaseMediaResources()
      upload()
    }

    mediaRecorder.onerror = () => {
      releaseMediaResources()
      errorMessage.value = '录音过程中出现错误，请重试。'
      recording.value = false
      clearTimer()
    }

    mediaRecorder.start()
    recording.value = true
    recordingDuration.value = 0

    durationTimer = window.setInterval(() => {
      recordingDuration.value++
      if (recordingDuration.value >= maxRecordingSeconds) {
        stopRecord()
        timeoutWarning.value = true
      }
    }, 1000)
  } catch (err: unknown) {
    releaseMediaResources()
    const message = err instanceof Error ? err.message : String(err)
    if (message.includes('NotAllowedError') || message.includes('Permission')) {
      errorMessage.value = '无法访问麦克风，请检查浏览器权限设置。'
    } else if (message.includes('NotFoundError')) {
      errorMessage.value = '未检测到麦克风设备。'
    } else {
      errorMessage.value = `录音启动失败: ${message}`
    }
  }
}

function stopRecord() {
  if (wsSession && (sessionState.value === 'ready' || sessionState.value === 'recording')) {
    // Streaming mode — send stop
    sessionState.value = 'stopping'
    wsSession.sendStop()
    audioCapture?.stop()
  } else if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    // Offline mode
    mediaRecorder.stop()
  }
  recording.value = false
  clearTimer()
}

function clearTimer() {
  if (durationTimer) {
    clearInterval(durationTimer)
    durationTimer = null
  }
}

function releaseMediaResources() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop())
    mediaStream = null
  }
  mediaRecorder = null
}

function cleanupStreamResources() {
  streamCleanup?.()
  streamCleanup = null
  audioCapture?.stop()
  audioCapture?.clearBackup()
  audioCapture = null
  wsSession?.close()
  wsSession = null
}

/** WS failure → try offline upload using MediaRecorder backup. */
function fallbackToOfflineUpload() {
  if (!audioCapture) return
  const backupBlob = audioCapture.getBackupBlob()
  if (!backupBlob) {
    errorMessage.value = '无可用离线录音备份。保留已识别文本供参考: ' + committedText.value
    return
  }
  // Upload backup via offline path
  const ext = 'webm'
  const filename = `rounding.${ext}`
  const fd = new FormData()
  fd.append('audio', backupBlob, filename)

  loading.value = true
  processingStage.value = 'uploading'
  transcribeAudio(props.patientId, fd)
    .then(({ data }) => {
      draft.value = data
      editText.value = data.corrected_text || data.cleaned_text || ''
    })
    .catch((err: unknown) => {
      const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
      errorMessage.value = '离线上传也失败: ' + (axiosErr.response?.data?.detail || axiosErr.message || '')
    })
    .finally(() => {
      loading.value = false
      processingStage.value = null
      cleanupStreamResources()
    })
}

async function upload() {
  if (!chunks.length) {
    errorMessage.value = '录音数据为空，请重试。'
    return
  }

  loading.value = true
  processingStage.value = 'uploading'
  errorMessage.value = ''

  try {
    // 使用实际录制的 MIME 类型
    const mime = actualMimeType || 'audio/webm'
    const blob = new Blob(chunks, { type: mime })
    const ext = getExtensionFromMimeType(mime)
    const filename = `rounding.${ext}`

    const fd = new FormData()
    fd.append('audio', blob, filename)

    processingStage.value = 'processing'

    const { data } = await transcribeAudio(props.patientId, fd)
    draft.value = data
    editText.value = data.corrected_text || data.cleaned_text || ''
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    const msg = axiosErr.response?.data?.detail || axiosErr.message || '转写失败'
    errorMessage.value = `转写失败: ${msg}`
  } finally {
    loading.value = false
    processingStage.value = null
    // 清理 Blob 引用
    chunks = []
  }
}

async function confirmText() {
  if (!editText.value.trim() || !draft.value) return
  try {
    await confirmVoiceRounding(props.patientId, {
      final_text: editText.value,
      draft_id: draft.value._id,
    })
    emit('confirmed', editText.value)
    draft.value = null
    editText.value = ''
  } catch (err: unknown) {
    const axiosErr = err as { response?: { data?: { detail?: string } }; message?: string }
    const msg = axiosErr.response?.data?.detail || axiosErr.message || '确认失败'
    errorMessage.value = `确认失败: ${msg}`
  }
}

function discardDraft() {
  draft.value = null
  editText.value = ''
  errorMessage.value = ''
}

function retryRecord() {
  draft.value = null
  editText.value = ''
  errorMessage.value = ''
  timeoutWarning.value = false
  processingStage.value = null
}

onUnmounted(() => {
  clearTimer()
  releaseMediaResources()
  cleanupStreamResources()
  chunks = []
})
</script>

<style scoped>
.voice-rounding {
  padding: 16px;
  border: 1px solid var(--border-color, #e0e0e0);
  border-radius: 8px;
  background: var(--card-bg, #fff);
}

.vr-controls {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.vr-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.vr-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.vr-btn--start {
  background: #1976d2;
  color: #fff;
}

.vr-btn--stop {
  background: #d32f2f;
  color: #fff;
}

.vr-btn--confirm {
  background: #2e7d32;
  color: #fff;
}

.vr-btn--cancel {
  background: transparent;
  color: #666;
  border: 1px solid #ccc;
}

.vr-btn--retry {
  background: transparent;
  color: #1976d2;
  border: 1px solid #1976d2;
}

.vr-icon {
  font-size: 18px;
}

.vr-recording-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #d32f2f;
  font-size: 13px;
}

.vr-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d32f2f;
  animation: vr-pulse 1s infinite;
}

@keyframes vr-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.vr-loading {
  color: #1976d2;
  font-size: 13px;
}

.vr-dev-info {
  font-size: 12px;
  color: #999;
  margin-left: auto;
}

.vr-dev-info summary {
  cursor: pointer;
}

.vr-dev-info pre {
  font-size: 11px;
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 4px;
  margin-top: 4px;
}

.vr-timeout-warn {
  color: #e65100;
  background: #fff3e0;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  border-left: 3px solid #e65100;
}

.vr-result {
  margin-top: 8px;
}

.vr-warn {
  color: #b00020;
  background: #fff3f3;
  padding: 10px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
  border-left: 3px solid #b00020;
}

.vr-warn ul {
  margin: 4px 0 0 16px;
  padding: 0;
  list-style: none;
}

.vr-suspect-item {
  padding: 2px 0;
  font-size: 13px;
}

/* 高风险：药名、剂量、数值 */
.vr-suspect--high {
  color: #b00020;
  font-weight: 600;
}

/* 中风险：单位不确定 */
.vr-suspect--medium {
  color: #e65100;
}

/* 低风险：低置信度、方言 */
.vr-suspect--low {
  color: #f9a825;
}

/* 其他 */
.vr-suspect--other {
  color: #757575;
}

.vr-suspect-term {
  font-weight: 600;
}

.vr-suspect-note {
  font-weight: 400;
  opacity: 0.85;
}

.vr-degraded {
  color: #795548;
  background: #fff8e1;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
}

.vr-processing-info {
  color: #999;
  font-size: 12px;
  margin-bottom: 8px;
}

.vr-hint {
  color: #666;
  font-size: 13px;
  margin-bottom: 8px;
}

.vr-edit-area {
  width: 100%;
  font-size: 15px;
  line-height: 1.6;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  resize: vertical;
  font-family: inherit;
}

.vr-edit-area:focus {
  outline: none;
  border-color: #1976d2;
  box-shadow: 0 0 0 2px rgba(25, 118, 210, 0.15);
}

.vr-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.vr-raw-details {
  margin-top: 16px;
  font-size: 13px;
  color: #666;
}

.vr-raw-details summary {
  cursor: pointer;
  user-select: none;
}

.vr-raw-text {
  margin-top: 8px;
  padding: 8px;
  background: #f5f5f5;
  border-radius: 4px;
}

.vr-raw-label {
  font-weight: 600;
  margin-bottom: 4px;
  color: #333;
}

.vr-raw-text pre {
  margin: 0 0 8px 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 13px;
  line-height: 1.5;
}

.vr-error {
  color: #b00020;
  background: #fff3f3;
  padding: 12px;
  border-radius: 6px;
  margin-top: 12px;
  font-size: 13px;
  border-left: 3px solid #b00020;
}

.vr-error p {
  margin: 0 0 8px;
}

/* Live caption (streaming mode) */
.vr-live-caption {
  background: #f0f7ff;
  border: 1px solid #bbdefb;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
}

.vr-live-label {
  font-size: 12px;
  color: #1976d2;
  margin: 0 0 8px;
  font-weight: 600;
}

.vr-caption-text {
  font-size: 15px;
  line-height: 1.6;
  min-height: 24px;
}

.vr-committed {
  color: #333;
}

.vr-partial {
  color: #1976d2;
  background: #e3f2fd;
  padding: 1px 4px;
  border-radius: 3px;
}

.vr-live-status {
  font-size: 13px;
  color: #1976d2;
  margin-top: 8px;
}

.vr-stream-error {
  color: #b00020;
  font-size: 13px;
  margin-top: 8px;
}

.vr-stream-error .vr-btn--retry {
  margin-top: 8px;
  display: inline-block;
}
</style>
