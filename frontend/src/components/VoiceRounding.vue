<template>
  <div class="voice-rounding">
    <!-- 录音控制区 -->
    <div class="vr-controls">
      <button
        v-if="!recording"
        class="vr-btn vr-btn--start"
        :disabled="loading"
        @click="startRecord"
      >
        <span class="vr-icon">🎤</span>
        <span>开始口述</span>
      </button>
      <button
        v-else
        class="vr-btn vr-btn--stop"
        @click="stopRecord"
      >
        <span class="vr-icon">⏹</span>
        <span>结束并转写</span>
      </button>

      <span v-if="recording" class="vr-recording-indicator">
        <span class="vr-dot"></span>
        录音中 {{ recordingDuration }}s
      </span>
      <span v-if="loading" class="vr-loading">识别中…</span>
    </div>

    <!-- 转写结果区 -->
    <div v-if="draft" class="vr-result">
      <!-- 人工审核警告 -->
      <div v-if="draft.needs_human_review" class="vr-warn">
        <strong>⚠️ 需人工核对（可能涉及数值/剂量）：</strong>
        <ul>
          <li v-for="(s, i) in draft.suspect" :key="i">{{ s }}</li>
        </ul>
      </div>

      <!-- 降级提示 -->
      <div v-if="draft.degraded" class="vr-degraded">
        ℹ️ LLM 纠错不可用，已返回规则清洗后的文本。
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
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { transcribeAudio, confirmVoiceRounding, type VoiceRoundingDraft } from '../api/voiceRounding'

const props = defineProps<{
  patientId: string
}>()

const emit = defineEmits<{
  confirmed: [text: string]
}>()

const recording = ref(false)
const loading = ref(false)
const draft = ref<VoiceRoundingDraft | null>(null)
const editText = ref('')
const recordingDuration = ref(0)

let mediaRecorder: MediaRecorder | null = null
let chunks: Blob[] = []
let durationTimer: number | null = null

async function startRecord() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks = []
    mediaRecorder = new MediaRecorder(stream)

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data)
    }

    mediaRecorder.onstop = () => {
      // 停止所有音频轨道
      stream.getTracks().forEach((t) => t.stop())
      upload()
    }

    mediaRecorder.start()
    recording.value = true
    recordingDuration.value = 0
    durationTimer = window.setInterval(() => {
      recordingDuration.value++
    }, 1000)
  } catch (err) {
    console.error('录音启动失败:', err)
    alert('无法访问麦克风，请检查浏览器权限设置。')
  }
}

function stopRecord() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }
  recording.value = false
  if (durationTimer) {
    clearInterval(durationTimer)
    durationTimer = null
  }
}

async function upload() {
  if (!chunks.length) return
  loading.value = true
  try {
    const blob = new Blob(chunks, { type: 'audio/webm' })
    const fd = new FormData()
    fd.append('audio', blob, 'rounding.webm')

    const { data } = await transcribeAudio(props.patientId, fd)
    draft.value = data
    editText.value = data.corrected_text || data.cleaned_text || ''
  } catch (err: any) {
    console.error('转写失败:', err)
    const msg = err.response?.data?.detail || err.message || '转写失败'
    alert(`转写失败: ${msg}`)
  } finally {
    loading.value = false
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
  } catch (err: any) {
    console.error('确认入库失败:', err)
    alert(`确认失败: ${err.response?.data?.detail || err.message}`)
  }
}

function discardDraft() {
  draft.value = null
  editText.value = ''
}

onUnmounted(() => {
  if (durationTimer) clearInterval(durationTimer)
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop()
  }
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
}

.vr-degraded {
  color: #795548;
  background: #fff8e1;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
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
</style>
