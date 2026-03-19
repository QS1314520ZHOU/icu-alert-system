<template>
  <div class="mdt-page">
    <a-card :bordered="false" class="mdt-hero">
      <div class="mdt-hero__copy">
        <div class="mdt-kicker">MDT 临床协作工作站</div>
        <h1 class="mdt-title">MDT 多智能体会诊</h1>
        <p class="mdt-desc">以七大生理系统为骨架，以 MDT 讨论流为主线，把患者数字孪生、专科分析、冲突协调与执行决议收敛到一个临床工作站。</p>
        <div class="mdt-hero__badges">
          <span class="hero-badge">{{ loading ? '会诊处理中' : '会诊就绪' }}</span>
          <span class="hero-badge hero-badge--soft">{{ selectedPatientLabel }}</span>
        </div>
      </div>
      <div class="mdt-hero__side">
        <div class="mdt-toolbar">
          <div class="toolbar-label">患者检索</div>
          <div class="mdt-toolbar__row">
            <select v-model="selectedPatientId" class="mdt-select">
              <option value="">选择患者</option>
              <option v-for="item in patientOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </div>
          <div class="mdt-toolbar__actions">
            <a-button size="small" type="primary" :loading="loading" @click="loadAssessment(true)">刷新会诊</a-button>
            <a-button size="small" ghost @click="openPatientDetail" :disabled="!selectedPatientId">打开患者详情</a-button>
          </div>
        </div>
        <div class="mdt-hero__mini">
          <div class="mini-card">
            <span>患者摘要</span>
            <strong>{{ patientHeadline }}</strong>
            <small>{{ patientSubline }}</small>
          </div>
          <div class="mini-card mini-card--accent">
            <span>裁决状态</span>
            <strong>{{ loading ? '处理中' : '已汇总' }}</strong>
            <small>{{ metaActionCount }} 条最终动作</small>
          </div>
        </div>
      </div>
    </a-card>

    <section class="mdt-workspace">
      <aside class="mdt-sidebar">
        <a-card :bordered="false" class="mdt-panel" title="患者数字孪生总览">
          <div class="patient-sheet">
            <div class="patient-sheet__name">{{ patientHeadline }}</div>
            <div class="patient-sheet__sub">{{ patientSubline }}</div>
            <div class="patient-sheet__grid">
              <div class="sheet-item">
                <span>七大系统</span>
                <strong>{{ systemCards.length }}</strong>
              </div>
              <div class="sheet-item">
                <span>冲突焦点</span>
                <strong>{{ conflictRows.length }}</strong>
              </div>
              <div class="sheet-item">
                <span>决议动作</span>
                <strong>{{ metaActionCount }}</strong>
              </div>
              <div class="sheet-item">
                <span>会诊状态</span>
                <strong>{{ loading ? '处理中' : '就绪' }}</strong>
              </div>
            </div>
          </div>
        </a-card>

        <a-card :bordered="false" class="mdt-panel" title="七大生理系统">
          <div class="system-grid">
            <article v-for="item in systemCards" :key="item.agent" :class="['system-card', `is-${item.priority || 'medium'}`, { 'is-active': activeSpecialist?.agent === item.agent }]" @click="activeAgent = item.agent">
              <div class="system-card__head">
                <div>
                  <div class="system-card__domain">{{ item.label }}</div>
                  <div class="system-card__priority">{{ priorityLabel(item.priority) }}</div>
                </div>
                <span class="system-card__status">{{ item.hasData ? '已评估' : '待补充' }}</span>
              </div>
              <div class="system-card__summary">{{ item.summary }}</div>
            </article>
          </div>
        </a-card>

        <a-card :bordered="false" class="mdt-panel" title="专科意见板">
          <div v-if="specialistRows.length" class="specialist-list">
            <article v-for="item in specialistRows" :key="item.agent" :class="['specialist-row', `is-${item.priority || 'medium'}`, { 'is-active': activeSpecialist?.agent === item.agent }]" @click="activeAgent = item.agent">
              <div class="specialist-row__main">
                <div class="specialist-row__domain">{{ domainLabel(item.domain) }}</div>
                <div class="specialist-row__summary">{{ item.summary || '暂无摘要' }}</div>
              </div>
              <div class="specialist-row__meta">{{ priorityLabel(item.priority) }}</div>
            </article>
          </div>
          <div v-else-if="isGeneratingAssessment" class="empty-box">已选中患者，正在生成 MDT 会诊结果，请稍候。</div>
          <div v-else class="empty-box">选择患者后加载会诊结果。</div>
        </a-card>
      </aside>

      <main class="mdt-content">
        <a-card :bordered="false" class="mdt-panel mdt-panel--hero" :title="`${activeSystemLabel} 详细分析`">
          <div class="section-kicker">专科深度面板</div>
          <div class="summary-box summary-box--hero">{{ isGeneratingAssessment ? 'Meta-Agent 正在汇总专科意见、冲突焦点与优先级动作。' : metaSummary }}</div>
          <div class="deep-panel-grid">
            <section class="deep-panel">
              <div class="deep-panel__title">{{ activeSystemLabel }}趋势与证据</div>
              <div class="deep-panel__body">
                <div class="trend-placeholder">
                  <div class="trend-placeholder__header">
                    <strong>{{ activeSystemLabel }}趋势</strong>
                    <select v-model="trendWindow" class="panel-select">
                      <option value="24h">24h</option>
                      <option value="72h">72h</option>
                    </select>
                  </div>
                  <div class="trend-placeholder__chart">
                    <span v-for="item in trendBars" :key="item.key" :style="{ height: `${item.height}%` }" :title="item.text"></span>
                  </div>
                  <div class="trend-metrics">
                    <div v-for="item in trendMetricCards.slice(0, 4)" :key="`metric-${item.key}`" class="trend-metrics__item">
                      <span>{{ item.label }}</span>
                      <strong>{{ displayMetricValue(item.value) != null ? `${displayMetricValue(item.value)}${item.unit ? ` ${item.unit}` : ''}` : '—' }}</strong>
                    </div>
                  </div>
                  <div class="trend-placeholder__caption">{{ activeSystemPanel?.summary || activeSpecialist?.summary || '等待系统分析结果' }}</div>
                </div>
                <div class="chip-row">
                  <span v-for="(item, idx) in activeSpecialist?.evidence || []" :key="`hero-evidence-${idx}`" class="chip">{{ item }}</span>
                </div>
              </div>
            </section>

            <section class="deep-panel">
              <div class="deep-panel__title">{{ detailPanelTitle }}</div>
              <div class="deep-panel__body">
                <template v-if="activeSystemDomain === 'hemodynamic' && activeSystemPanel">
                  <div class="assistant-note">
                    <div class="assistant-note__label">血管活性药</div>
                    <div class="assistant-note__text">
                      {{ activeSystemPanel.active_vasopressors?.length ? activeSystemPanel.active_vasopressors.map((item: any) => `${item.drug}${item.dose_display ? ` ${item.dose_display}` : ''}`).join('；') : '当前未识别到持续血管活性药事件。' }}
                    </div>
                  </div>
                  <div class="assistant-note">
                    <div class="assistant-note__label">液体平衡</div>
                    <div class="assistant-note__text">
                      {{ activeSystemPanel.fluid_balance?.windows?.length ? activeSystemPanel.fluid_balance.windows.map((item: any) => `${item.label}净平衡 ${item.net_ml} mL`).join('；') : '当前无可用液体平衡窗口。' }}
                    </div>
                  </div>
                  <div v-if="activeSystemPanel.vasopressor_timeline?.length" class="detail-timeline">
                    <article v-for="(item, idx) in activeSystemPanel.vasopressor_timeline.slice().reverse().slice(0, 6)" :key="`vaso-${idx}`" class="timeline-item">
                      <strong>{{ item.drug }}</strong>
                      <span>{{ item.dose_display || item.order_name || '剂量未结构化' }}</span>
                      <small>{{ item.time ? String(item.time).slice(0, 16).replace('T', ' ') : '时间未记载' }}</small>
                    </article>
                  </div>
                </template>
                <template v-else-if="activeSystemDomain === 'infection' && activeSystemPanel">
                  <div class="assistant-note">
                    <div class="assistant-note__label">降阶梯判断</div>
                    <div class="assistant-note__text">{{ activeSystemPanel.deescalation?.title || '暂无判断' }} · {{ activeSystemPanel.deescalation?.detail || '等待培养与药敏结果。' }}</div>
                  </div>
                  <div class="assistant-note">
                    <div class="assistant-note__label">当前抗菌药</div>
                    <div class="assistant-note__text">
                      {{ activeSystemPanel.current_antibiotics?.length ? activeSystemPanel.current_antibiotics.map((item: any) => `${item.name}${item.broad_spectrum ? '·广谱' : ''}`).join('；') : '当前未识别到持续抗菌药疗程。' }}
                    </div>
                  </div>
                  <div v-if="activeSystemPanel.culture_timeline?.length" class="detail-timeline">
                    <article v-for="(item, idx) in activeSystemPanel.culture_timeline.slice(0, 6)" :key="`culture-${idx}`" class="timeline-item">
                      <strong>{{ item.title }}</strong>
                      <span>{{ item.detail }}</span>
                      <small>{{ item.time ? String(item.time).slice(0, 16).replace('T', ' ') : '时间未记载' }}</small>
                    </article>
                  </div>
                </template>
                <template v-else-if="activeSystemDomain === 'respiratory' && activeSystemPanel">
                  <div class="assistant-note">
                    <div class="assistant-note__label">当前通气支持</div>
                    <div class="assistant-note__text">
                      模式 {{ activeSystemPanel.latest?.mode || '—' }} / FiO2 {{ activeSystemPanel.latest?.fio2 ?? '—' }}% / PEEP {{ activeSystemPanel.latest?.peep ?? '—' }} cmH2O / RR {{ activeSystemPanel.latest?.rr ?? '—' }} /min
                    </div>
                  </div>
                  <div class="assistant-note">
                    <div class="assistant-note__label">P/F 趋势</div>
                    <div class="assistant-note__text">
                      {{ activeSystemPanel.pf_trend?.pf_ratio != null ? `P/F ${activeSystemPanel.pf_trend.pf_ratio}，趋势 ${activeSystemPanel.pf_trend.trend || 'stable'}` : '当前未生成 P/F 趋势。' }}
                    </div>
                  </div>
                  <div v-if="activeSystemPanel.ventilator_timeline?.length" class="detail-timeline">
                    <article v-for="(item, idx) in activeSystemPanel.ventilator_timeline.slice().reverse().slice(0, 6)" :key="`vent-${idx}`" class="timeline-item">
                      <strong>{{ item.mode || activeSystemPanel.latest?.mode || 'Vent' }}</strong>
                      <span>FiO2 {{ item.fio2 ?? '—' }} / PEEP {{ item.peep ?? '—' }} / RR {{ item.rr ?? '—' }} / Vte {{ item.vte ?? '—' }}</span>
                      <small>{{ item.time ? String(item.time).slice(0, 16).replace('T', ' ') : '时间未记载' }}</small>
                    </article>
                  </div>
                </template>
                <template v-else>
                  <div class="assistant-note">
                    <div class="assistant-note__label">类型判断</div>
                    <div class="assistant-note__text">{{ activeSpecialist?.summary || '暂无系统级判断' }}</div>
                  </div>
                  <div class="assistant-note">
                    <div class="assistant-note__label">Evidence</div>
                    <div class="assistant-note__text">{{ activeSpecialistEvidence }}</div>
                  </div>
                  <div class="assistant-note">
                    <div class="assistant-note__label">Suggestion</div>
                    <div class="assistant-note__text">{{ activeSpecialistSuggestion }}</div>
                  </div>
                </template>
              </div>
            </section>
          </div>
        </a-card>

        <div class="mdt-content-grid">
          <a-card :bordered="false" class="mdt-panel" title="相关告警链">
            <div v-if="filteredAlerts.length" class="alert-chain">
              <article v-for="(item, idx) in filteredAlerts" :key="`chain-${idx}`" class="alert-chain__item">
                <div class="alert-chain__time">{{ item.created_at ? String(item.created_at).slice(11, 16) : `链路 ${Number(idx) + 1}` }}</div>
                <div class="alert-chain__text">{{ item.name || item.alert_type || item.rule_id || '告警事件' }}</div>
                <div class="alert-chain__sub">{{ item.explanation?.summary || item.explanation || '' }}</div>
              </article>
            </div>
            <div v-else class="empty-box">当前系统暂无结构化告警链，等待更多事件数据。</div>
          </a-card>

          <a-card :bordered="false" class="mdt-panel" :title="impactPanelTitle">
            <div v-if="activeSystemDomain === 'hemodynamic' && activeSystemPanel?.fluid_balance?.windows?.length" class="impact-list">
              <article v-for="item in activeSystemPanel.fluid_balance.windows" :key="item.label" class="impact-card">
                <div class="impact-card__title">{{ item.label }} 液体平衡</div>
                <div class="impact-card__text">入量 {{ item.intake_ml }} mL / 出量 {{ item.output_ml }} mL / 净平衡 {{ item.net_ml }} mL</div>
              </article>
            </div>
            <div v-else-if="activeSystemDomain === 'infection' && activeSystemPanel?.coverage_mismatches?.length" class="impact-list">
              <article v-for="(item, idx) in activeSystemPanel.coverage_mismatches" :key="`mismatch-${idx}`" class="impact-card">
                <div class="impact-card__title">{{ item.organism || '覆盖偏差' }}</div>
                <div class="impact-card__text">{{ item.suggestion || '当前方案与药敏不一致。' }}</div>
                <div class="impact-card__sub">{{ (item.resistant_to || []).join(' / ') }}</div>
              </article>
            </div>
            <div v-else-if="activeSystemDomain === 'respiratory' && activeSystemPanel?.ventilator_timeline?.length" class="impact-list">
              <article v-for="(item, idx) in activeSystemPanel.ventilator_timeline.slice().reverse().slice(0, 8)" :key="`resp-impact-${idx}`" class="impact-card">
                <div class="impact-card__title">{{ item.mode || activeSystemPanel.latest?.mode || 'Vent' }}</div>
                <div class="impact-card__text">FiO2 {{ item.fio2 ?? '—' }} / PEEP {{ item.peep ?? '—' }} / RR {{ item.rr ?? '—' }} / PIP {{ item.pip ?? '—' }}</div>
                <div class="impact-card__sub">{{ item.time ? String(item.time).slice(0, 16).replace('T', ' ') : '时间未记载' }}</div>
              </article>
            </div>
            <div v-else-if="filteredDrugs.length" class="impact-list">
              <article v-for="item in filteredDrugs" :key="`${item.drugName}-${item.executeTime}`" class="impact-card">
                <div class="impact-card__title">{{ item.drugName || item.orderName || '用药' }}</div>
                <div class="impact-card__text">
                  {{ item.dose || '--' }}{{ item.doseUnit || '' }} / {{ item.route || '给药途径未记载' }} / {{ item.frequency || '频次未记载' }}
                </div>
                <div class="impact-card__sub">{{ item.executeTime ? String(item.executeTime).slice(0, 16).replace('T', ' ') : '执行时间未记载' }}</div>
              </article>
            </div>
            <div v-else class="empty-box">当前系统暂无明显相关结构化事件。</div>
          </a-card>
        </div>

        <div class="mdt-content-grid">
          <a-card :bordered="false" class="mdt-panel" title="MDT 冲突高亮">
            <div v-if="conflictRows.length" class="conflict-list">
              <article v-for="(item, idx) in conflictRows" :key="`${item.type || 'conflict'}-${idx}`" class="conflict-card">
                <div class="conflict-card__title">{{ item.summary || '存在跨专科冲突' }}</div>
                <div class="conflict-card__agents">{{ (item.agents || []).map(domainLabel).join(' / ') || '多专科' }}</div>
                <div class="conflict-card__meta">{{ item.resolution_focus || '需结合动态病情进一步裁决。' }}</div>
              </article>
            </div>
            <div v-else-if="isGeneratingAssessment" class="empty-box">会诊生成中，正在汇总冲突焦点与 Meta-Agent 裁决。</div>
            <div v-else class="empty-box">当前未识别到明显跨专科冲突，可继续按 Meta-Agent 裁决跟踪执行。</div>
          </a-card>

          <a-card :bordered="false" class="mdt-panel" title="专科意见与 AI 预填充">
            <div v-if="activeSpecialist" class="detail-stack">
              <div class="summary-box">{{ activeSpecialist.summary || '暂无摘要' }}</div>
              <div class="detail-block">
                <div class="detail-label">该专科视角评估</div>
                <ul class="action-list">
                  <li v-for="(item, idx) in activeSpecialist.concerns || []" :key="`concern-${idx}`">{{ item }}</li>
                </ul>
              </div>
              <div class="detail-block">
                <div class="detail-label">AI 预填充建议</div>
                <ul class="action-list">
                  <li v-for="(item, idx) in activeSpecialist.recommendations || []" :key="`rec-${idx}`">{{ item }}</li>
                </ul>
              </div>
              <div class="detail-block">
                <div class="detail-label">证据线索</div>
                <div class="chip-row">
                  <span v-for="(item, idx) in activeSpecialist.evidence || []" :key="`evidence-${idx}`" class="chip">{{ item }}</span>
                </div>
              </div>
            </div>
            <div v-else-if="isGeneratingAssessment" class="empty-box">专科 Agent 正在生成细化意见与建议动作。</div>
            <div v-else class="empty-box">点击左侧专科卡片后查看详细意见。</div>
          </a-card>
        </div>

        <div class="mdt-content-grid">
          <a-card :bordered="false" class="mdt-panel" title="Meta-Agent 全局优先级">
            <div v-if="priorityRows.length" class="priority-row">
              <article v-for="item in priorityRows" :key="`${item.agent}-${item.domain}`" :class="['priority-card', `is-${item.priority || 'medium'}`]">
                <div class="priority-card__head">
                  <strong>{{ domainLabel(item.domain) }}</strong>
                  <span>{{ priorityLabel(item.priority) }}</span>
                </div>
                <div class="priority-card__main">{{ item.summary || '待补充摘要' }}</div>
              </article>
            </div>
            <div v-else class="empty-box">等待 Meta-Agent 汇总全局优先级。</div>
          </a-card>

          <a-card :bordered="false" class="mdt-panel" title="决议记录与执行追踪">
            <div class="decision-list">
              <article v-for="(item, idx) in decisionRows" :key="item.id || `decision-${idx}`" class="decision-item">
                <div class="decision-item__head">
                  <strong>决议 {{ Number(idx) + 1 }}</strong>
                  <span>{{ Number(idx) === 0 ? '立即执行' : '待追踪' }}</span>
                </div>
                <div class="decision-form">
                  <input v-model="item.action" class="field-input" placeholder="输入 MDT 决议动作" />
                  <div class="decision-form__grid">
                    <input v-model="item.owner" class="field-input" placeholder="负责人" />
                    <input v-model="item.deadline" class="field-input" placeholder="执行时限" />
                    <input v-model="item.monitoring" class="field-input" placeholder="监测指标" />
                    <input v-model="item.review_time" class="field-input" placeholder="复评时间" />
                  </div>
                  <textarea v-model="item.note" class="field-textarea" rows="2" placeholder="补充说明 / 平衡方案"></textarea>
                </div>
                <div class="decision-item__meta">
                  <span>状态：{{ item.status || 'pending' }}</span>
                  <button type="button" class="mini-link" @click="removeDecision(item.id)">删除</button>
                </div>
              </article>
            </div>
            <div class="workspace-actions">
              <a-button size="small" @click="addDecision">新增决议</a-button>
              <a-button size="small" type="primary" :loading="savingWorkspace" @click="saveWorkspace">保存决议</a-button>
            </div>
          </a-card>
        </div>

        <div class="mdt-content-grid">
          <a-card :bordered="false" class="mdt-panel" title="会诊记录 / 病程记录">
            <div class="doc-stack">
              <div class="doc-block">
                <div class="detail-label">MDT 会诊记录</div>
                <textarea v-model="consultRecord" class="field-textarea field-textarea--lg" rows="8" placeholder="可先编辑，再一键保存或用 AI 生成。"></textarea>
                <div class="workspace-actions">
                  <a-button size="small" :loading="generatingDocType === 'mdt_summary'" @click="generateDocument('mdt_summary')">AI生成讨论材料</a-button>
                  <a-button size="small" :loading="generatingDocType === 'consultation_request'" @click="generateDocument('consultation_request')">AI生成会诊记录</a-button>
                </div>
              </div>
              <div class="doc-block">
                <div class="detail-label">病程记录</div>
                <textarea v-model="progressRecord" class="field-textarea field-textarea--lg" rows="8" placeholder="将 MDT 讨论要点整合进当日病程记录。"></textarea>
                <div class="workspace-actions">
                  <a-button size="small" :loading="generatingDocType === 'daily_progress'" @click="generateDocument('daily_progress')">AI生成病程记录</a-button>
                  <a-button size="small" type="primary" :loading="savingWorkspace" @click="saveWorkspace">保存文书</a-button>
                </div>
              </div>
            </div>
            <div class="impact-list">
              <article v-if="latestGeneratedDocuments.mdt_summary" class="impact-card">
                <div class="impact-card__title">最新 MDT 讨论材料</div>
                <div class="impact-card__text">{{ latestGeneratedDocuments.mdt_summary.document?.document_text || latestGeneratedDocuments.mdt_summary.summary || '已生成' }}</div>
              </article>
              <article v-if="latestGeneratedDocuments.daily_progress" class="impact-card">
                <div class="impact-card__title">最新病程记录</div>
                <div class="impact-card__text">{{ latestGeneratedDocuments.daily_progress.document?.document_text || latestGeneratedDocuments.daily_progress.summary || '已生成' }}</div>
              </article>
            </div>
          </a-card>

          <a-card :bordered="false" class="mdt-panel" title="医嘱草稿">
            <div class="decision-list">
              <article v-for="item in generatedOrderDrafts" :key="item.id" class="decision-item">
                <div class="decision-item__head">
                  <strong>{{ item.category || '医嘱建议' }}</strong>
                  <span>{{ item.priority || 'medium' }}</span>
                </div>
                <textarea v-model="item.order_text" class="field-textarea" rows="3"></textarea>
                <div class="decision-item__meta">
                  <span>状态：{{ item.status || 'draft' }}</span>
                  <span>来源：{{ item.source || 'mdt_workspace' }}</span>
                </div>
              </article>
            </div>
          </a-card>
        </div>
      </main>
    </section>

    <div v-if="error" class="error-box">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Button as AButton, Card as ACard } from 'ant-design-vue'
import {
  generateAiDocument,
  getAiMdtWorkspace,
  getAiMultiAgentAssessment,
  getAiSystemPanels,
  getPatientAlerts,
  getPatientDetail,
  getPatientDrugs,
  getPatientVitalsTrend,
  getPatients,
  saveAiMdtWorkspace,
} from '../api'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const error = ref('')
const patients = ref<any[]>([])
const patient = ref<any>(null)
const assessment = ref<any>(null)
const selectedPatientId = ref('')
const activeAgent = ref('')
const currentLoadToken = ref(0)
const trendWindow = ref<'24h' | '72h'>('24h')
const vitalsTrendPoints = ref<any[]>([])
const drugs = ref<any[]>([])
const alerts = ref<any[]>([])
const systemPanels = ref<Record<string, any>>({})
const workspaceRecord = ref<any>(null)
const workspaceDocuments = ref<any[]>([])
const generatedOrderDrafts = ref<any[]>([])
const decisions = ref<any[]>([])
const consultRecord = ref('')
const progressRecord = ref('')
const savingWorkspace = ref(false)
const generatingDocType = ref('')

const patientOptions = computed(() =>
  patients.value.map((item: any) => ({
    value: String(item?._id || ''),
    label: `${item?.hisBed || '--'}床 · ${item?.name || item?.hisName || '未知患者'} · ${item?.clinicalDiagnosis || item?.admissionDiagnosis || '暂无诊断'}`,
  }))
)
const assessmentRecord = computed(() => assessment.value?.assessment || assessment.value || null)
const assessmentResult = computed(() => assessmentRecord.value?.result || assessmentRecord.value || {})
const specialistRows = computed(() => Object.values(assessmentResult.value?.assessments || {}) as any[])
const conflictRows = computed(() => Array.isArray(assessmentResult.value?.conflicts) ? assessmentResult.value.conflicts : [])
const metaSummaryRecord = computed(() => assessmentResult.value?.meta_agent || {})
const metaSummary = computed(() => String(metaSummaryRecord.value?.summary || assessmentRecord.value?.summary || '暂无 Meta-Agent 裁决摘要'))
const metaActions = computed(() => Array.isArray(metaSummaryRecord.value?.final_actions) ? metaSummaryRecord.value.final_actions : [])
const metaActionCount = computed(() => metaActions.value.length)
const priorityRows = computed(() => Array.isArray(metaSummaryRecord.value?.top_priorities) ? metaSummaryRecord.value.top_priorities : [])
const activeSpecialist = computed(() => specialistRows.value.find((item: any) => item.agent === activeAgent.value) || specialistRows.value[0] || null)
const systemCards = computed(() => {
  const systems = [
    { agent: 'hemodynamic_agent', domain: 'hemodynamic', label: '循环系统' },
    { agent: 'respiratory_agent', domain: 'respiratory', label: '呼吸系统' },
    { agent: 'infection_agent', domain: 'infection', label: '感染系统' },
    { agent: 'renal_agent', domain: 'renal', label: '肾脏系统' },
    { agent: 'neuro_agent', domain: 'neuro', label: '神经系统' },
    { agent: 'nutrition_agent', domain: 'nutrition', label: '营养代谢' },
    { agent: 'pharmacy_agent', domain: 'pharmacy', label: '药学安全' },
  ]
  return systems.map((item) => {
    const row = specialistRows.value.find((entry: any) => entry.agent === item.agent) || null
    return {
      ...item,
      priority: row?.priority || 'medium',
      hasData: Boolean(row),
      summary: row?.summary || '当前暂无该系统专科分析结果',
    }
  })
})
const isGeneratingAssessment = computed(() => Boolean(selectedPatientId.value) && loading.value && !specialistRows.value.length)
const activeSystemDomain = computed(() => String(activeSpecialist.value?.domain || 'hemodynamic'))
const activeSystemLabel = computed(() => activeSpecialist.value ? domainLabel(activeSpecialist.value.domain) : '系统')
const activeSystemPanel = computed(() => systemPanels.value?.[activeSystemDomain.value] || null)
const activeSystemConfig = computed(() => {
  const domain = String(activeSpecialist.value?.domain || '')
  const fallbackConfig: { fields: string[]; labels: Record<string, string>; drugKeywords: string[]; alertKeywords: string[] } = {
    fields: ['nibp_map', 'ibp_map', 'hr', 'nibp_sys'],
    labels: { nibp_map: 'MAP', ibp_map: '有创MAP', hr: 'HR', nibp_sys: 'SBP' },
    drugKeywords: ['去甲'],
    alertKeywords: ['map'],
  }
  const configs: Record<string, { fields: string[]; labels: Record<string, string>; drugKeywords: string[]; alertKeywords: string[] }> = {
    hemodynamic: {
      fields: ['nibp_map', 'ibp_map', 'hr', 'nibp_sys'],
      labels: { nibp_map: 'MAP', ibp_map: '有创MAP', hr: 'HR', nibp_sys: 'SBP' },
      drugKeywords: ['去甲', '肾上腺素', '血管加压素', '多巴胺', '多巴酚丁胺'],
      alertKeywords: ['map', '休克', '乳酸', 'hemodynamic', 'fluid'],
    },
    respiratory: {
      fields: ['spo2', 'rr', 'temp'],
      labels: { spo2: 'SpO2', rr: 'RR', temp: 'Temp' },
      drugKeywords: ['雾化', '沙丁胺醇', '布地奈德'],
      alertKeywords: ['spo2', '呼吸', 'ards', 'vent', 'oxygen'],
    },
    infection: {
      fields: ['temp', 'hr', 'rr'],
      labels: { temp: 'Temp', hr: 'HR', rr: 'RR' },
      drugKeywords: ['美罗培南', '万古霉素', '哌拉西林', '利奈唑胺', '头孢'],
      alertKeywords: ['感染', 'sepsis', '培养', '炎症'],
    },
    renal: {
      fields: ['nibp_map', 'ibp_map', 'hr'],
      labels: { nibp_map: 'MAP', ibp_map: '有创MAP', hr: 'HR' },
      drugKeywords: ['呋塞米', 'CRRT', '碳酸氢钠'],
      alertKeywords: ['renal', 'crrt', 'aki', '尿量'],
    },
    neuro: {
      fields: ['hr', 'spo2', 'temp'],
      labels: { hr: 'HR', spo2: 'SpO2', temp: 'Temp' },
      drugKeywords: ['丙泊酚', '咪达唑仑', '右美托咪定'],
      alertKeywords: ['gcs', 'delirium', 'pupil', 'neuro'],
    },
    nutrition: {
      fields: ['hr', 'temp'],
      labels: { hr: 'HR', temp: 'Temp' },
      drugKeywords: ['营养', '肠内营养', 'TPN', '胰岛素'],
      alertKeywords: ['nutrition', 'feeding', 'po4'],
    },
    pharmacy: {
      fields: ['hr', 'nibp_map', 'spo2'],
      labels: { hr: 'HR', nibp_map: 'MAP', spo2: 'SpO2' },
      drugKeywords: [],
      alertKeywords: ['drug', 'dose', 'toxicity', '药'],
    },
  }
  return configs[domain] ?? configs.hemodynamic ?? fallbackConfig
})
const filteredTrendPoints = computed(() => {
  const fields = activeSystemConfig.value.fields
  const rows = vitalsTrendPoints.value.filter((point: any) => fields.some((field) => point?.[field] != null))
  return rows.slice(-12)
})
const trendBars = computed(() => {
  const panelPoints = Array.isArray(activeSystemPanel.value?.trend_points) ? activeSystemPanel.value.trend_points : []
  if (panelPoints.length) {
    const numericKeys = Object.keys(panelPoints[0] || {}).filter((key) => key !== 'time')
    const primaryKey = numericKeys[0]
    const maxValue = Math.max(
      ...panelPoints.flatMap((row: any) => numericKeys.map((key) => Number(row?.[key])).filter((value) => Number.isFinite(value))),
      1
    )
    return panelPoints.map((point: any, idx: number) => {
      const values = numericKeys
        .map((key) => ({ key, value: Number(point?.[key]) }))
        .filter((item) => Number.isFinite(item.value))
      const primary = values.find((item) => item.key === primaryKey) || values[0]
      return {
        key: `${point?.time || idx}`,
        label: String(point?.time || '').slice(11, 16) || `${idx + 1}`,
        height: primary ? Math.max(16, Math.round((primary.value / maxValue) * 100)) : 16,
        text: values.map((item) => `${item.key.toUpperCase()} ${item.value}`).join(' / ') || '无数据',
      }
    })
  }
  const fields = activeSystemConfig.value.fields
  const labels = activeSystemConfig.value.labels
  return filteredTrendPoints.value.map((point: any, idx: number) => {
    const values = fields
      .map((field) => ({ field, value: Number(point?.[field]), label: labels[field] || field }))
      .filter((item) => Number.isFinite(item.value))
    const primary = values[0]
    const maxValue = Math.max(...filteredTrendPoints.value.flatMap((row: any) => fields.map((field) => Number(row?.[field])).filter(Number.isFinite)), 1)
    return {
      key: `${point?.time || idx}`,
      label: String(point?.time || '').slice(11, 16) || `${idx + 1}`,
      height: primary ? Math.max(16, Math.round((primary.value / maxValue) * 100)) : 16,
      text: values.map((item) => `${item.label} ${item.value}`).join(' / ') || '无数据',
    }
  })
})
const trendMetricCards = computed(() => {
  const rows = Array.isArray(activeSystemPanel.value?.metric_cards) ? activeSystemPanel.value.metric_cards : []
  if (rows.length) return rows
  return trendBars.value.slice(-4).map((item: any) => ({ key: item.key, label: item.label, value: item.text, unit: '' }))
})

function displayMetricValue(value: any) {
  if (value == null || value === '') return null
  if (typeof value === 'number' || typeof value === 'string') return value
  if (typeof value === 'object') {
    const numeric = Number((value as any)?.value)
    if (Number.isFinite(numeric)) return numeric
    return null
  }
  return String(value)
}
const filteredDrugs = computed(() => {
  const keywords = activeSystemConfig.value.drugKeywords.map((item) => item.toLowerCase())
  const rows = drugs.value.filter((item: any) => {
    const text = `${item?.drugName || ''} ${item?.orderName || ''}`.toLowerCase()
    return !keywords.length || keywords.some((keyword) => text.includes(keyword))
  })
  return rows.slice(0, 8)
})
const filteredAlerts = computed(() => {
  const keywords = activeSystemConfig.value.alertKeywords.map((item) => item.toLowerCase())
  return alerts.value.filter((item: any) => {
    const text = `${item?.name || ''} ${item?.alert_type || ''} ${item?.rule_id || ''} ${item?.explanation?.summary || item?.explanation || ''}`.toLowerCase()
    return keywords.some((keyword) => text.includes(keyword))
  }).slice(0, 8)
})
const activeSpecialistEvidence = computed(() => {
  const evidence = Array.isArray(activeSpecialist.value?.evidence) ? activeSpecialist.value.evidence : []
  return evidence.length ? evidence.join('；') : '未见更多结构化证据线索'
})
const activeSpecialistSuggestion = computed(() => {
  const rows = Array.isArray(activeSpecialist.value?.recommendations) ? activeSpecialist.value.recommendations : []
  return rows.length ? rows.join('；') : '建议继续动态评估并等待更多数据支撑'
})
const detailPanelTitle = computed(() => {
  if (activeSystemDomain.value === 'hemodynamic') return '血管活性药物时间轴与液体平衡'
  if (activeSystemDomain.value === 'infection') return '培养 / 抗菌药降阶梯判断'
  if (activeSystemDomain.value === 'respiratory') return '呼吸机参数趋势'
  return `AI ${activeSystemLabel.value}顾问`
})
const impactPanelTitle = computed(() => {
  if (activeSystemDomain.value === 'hemodynamic') return '循环系统关键事件'
  if (activeSystemDomain.value === 'infection') return '感染系统关键事件'
  if (activeSystemDomain.value === 'respiratory') return '呼吸系统关键事件'
  return '用药时间轴'
})
const decisionRows = computed(() => decisions.value.length ? decisions.value : [{
  id: 'decision-1',
  action: metaActions.value[0] || '等待 MDT 形成结构化决议后展示执行追踪。',
  owner: '值班医生',
  deadline: '6h',
  monitoring: '按系统指标复评',
  review_time: '6h',
  status: 'pending',
  note: '',
}])
const latestGeneratedDocuments = computed(() =>
  workspaceDocuments.value.reduce((acc: Record<string, any>, item: any) => {
    const key = String(item?.doc_type || '')
    if (key && !acc[key]) acc[key] = item
    return acc
  }, {})
)
const selectedPatientLabel = computed(() => {
  if (patient.value) {
    const bed = patient.value?.hisBed || patient.value?.bed || '--'
    return `${bed}床 · ${patientHeadline.value}`
  }
  return selectedPatientId.value ? '患者已选择' : '未选择患者'
})
const patientHeadline = computed(() => patient.value?.name || patient.value?.hisName || '未选择患者')
const patientSubline = computed(() => {
  if (selectedPatientId.value && loading.value && !patient.value) return '患者信息加载中，请稍候'
  if (!patient.value) return '可从患者详情页带入，或在本页直接选择患者'
  const bed = patient.value?.hisBed || patient.value?.bed || '--'
  const diagnosis = patient.value?.clinicalDiagnosis || patient.value?.admissionDiagnosis || '暂无诊断'
  return `${bed}床 · ${diagnosis}`
})

function domainLabel(domain: any) {
  const key = String(domain || '')
  return ({
    hemodynamic: '循环',
    respiratory: '呼吸',
    infection: '感染',
    renal: '肾脏',
    neuro: '神经',
    nutrition: '营养',
    pharmacy: '药学',
    hemodynamic_agent: '循环',
    respiratory_agent: '呼吸',
    infection_agent: '感染',
    renal_agent: '肾脏',
    neuro_agent: '神经',
    nutrition_agent: '营养',
    pharmacy_agent: '药学',
  } as Record<string, string>)[key] || key || '未知专科'
}

function priorityLabel(priority: any) {
  const key = String(priority || 'medium').toLowerCase()
  return ({ critical: '危急', high: '高优先', medium: '中优先', low: '低优先' } as Record<string, string>)[key] || '中优先'
}

async function loadPatientOptions() {
  const res = await getPatients()
  patients.value = Array.isArray(res.data?.patients) ? res.data.patients : []
}

async function loadWorkspaceExtras(patientId: string) {
  const trendPromise = getPatientVitalsTrend(patientId, trendWindow.value === '72h' ? '48h' : '24h')
  const drugsPromise = getPatientDrugs(patientId)
  const alertsPromise = getPatientAlerts(patientId)
  const workspacePromise = getAiMdtWorkspace(patientId)
  const systemPanelsPromise = getAiSystemPanels(patientId, { window: trendWindow.value })
  const [trendRes, drugsRes, alertsRes, workspaceRes, systemPanelsRes] = await Promise.all([
    trendPromise,
    drugsPromise,
    alertsPromise,
    workspacePromise,
    systemPanelsPromise,
  ])
  vitalsTrendPoints.value = Array.isArray(trendRes.data?.points) ? trendRes.data.points : []
  drugs.value = Array.isArray(drugsRes.data?.records) ? drugsRes.data.records : []
  alerts.value = Array.isArray(alertsRes.data?.records) ? alertsRes.data.records : []
  workspaceRecord.value = workspaceRes.data?.workspace || null
  workspaceDocuments.value = Array.isArray(workspaceRes.data?.documents) ? workspaceRes.data.documents : []
  generatedOrderDrafts.value = Array.isArray(workspaceRes.data?.order_drafts) ? workspaceRes.data.order_drafts : []
  systemPanels.value = systemPanelsRes.data?.panels || {}
  decisions.value = Array.isArray(workspaceRecord.value?.decisions) && workspaceRecord.value.decisions.length
    ? workspaceRecord.value.decisions
    : metaActions.value.slice(0, 4).map((item: string, idx: number) => ({
        id: `decision-${idx + 1}`,
        action: item,
        owner: '值班医生',
        deadline: idx === 0 ? '立即' : '6h',
        monitoring: '按系统指标复评',
        review_time: '6h',
        status: 'pending',
        note: '',
      }))
  consultRecord.value = String(workspaceRecord.value?.consult_record || '')
  progressRecord.value = String(workspaceRecord.value?.progress_record || '')
}

async function loadAssessment(refresh = false) {
  if (!selectedPatientId.value) return
  const loadToken = currentLoadToken.value + 1
  currentLoadToken.value = loadToken
  loading.value = true
  error.value = ''
  assessment.value = null
  systemPanels.value = {}
  activeAgent.value = ''
  try {
    const patientPromise = getPatientDetail(selectedPatientId.value)
    const assessmentPromise = getAiMultiAgentAssessment(selectedPatientId.value, { refresh })
    const extrasPromise = loadWorkspaceExtras(selectedPatientId.value)
    const patientRes = await patientPromise
    if (loadToken !== currentLoadToken.value) return
    patient.value = patientRes.data?.patient || null
    const assessmentRes = await assessmentPromise
    if (loadToken !== currentLoadToken.value) return
    assessment.value = assessmentRes.data || null
    activeAgent.value = specialistRows.value[0]?.agent || ''
    await extrasPromise
    if (!decisions.value.length && metaActions.value.length) {
      decisions.value = metaActions.value.slice(0, 4).map((item: string, idx: number) => ({
        id: `decision-${idx + 1}`,
        action: item,
        owner: '值班医生',
        deadline: idx === 0 ? '立即' : '6h',
        monitoring: '按系统指标复评',
        review_time: '6h',
        status: 'pending',
        note: '',
      }))
    }
  } catch {
    if (loadToken !== currentLoadToken.value) return
    error.value = 'MDT 会诊加载失败，请检查患者数据和后端多智能体接口。'
  } finally {
    if (loadToken === currentLoadToken.value) {
      loading.value = false
    }
  }
}

async function saveWorkspace() {
  if (!selectedPatientId.value) return
  savingWorkspace.value = true
  try {
    const res = await saveAiMdtWorkspace(selectedPatientId.value, {
      decisions: decisions.value,
      consult_record: consultRecord.value,
      progress_record: progressRecord.value,
      order_drafts: generatedOrderDrafts.value,
    })
    workspaceRecord.value = res.data?.workspace || null
  } finally {
    savingWorkspace.value = false
  }
}

async function generateDocument(docType: 'mdt_summary' | 'daily_progress' | 'consultation_request') {
  if (!selectedPatientId.value) return
  generatingDocType.value = docType
  try {
    const res = await generateAiDocument(selectedPatientId.value, { doc_type: docType, time_range: { hours: trendWindow.value === '72h' ? 72 : 24 } })
    const doc = res.data?.document
    if (doc) {
      workspaceDocuments.value = [doc, ...workspaceDocuments.value.filter((item: any) => item?._id !== doc?._id)]
      const text = String(doc?.document?.document_text || '')
      if (docType === 'consultation_request') consultRecord.value = text
      if (docType === 'daily_progress') progressRecord.value = text
    }
  } finally {
    generatingDocType.value = ''
  }
}

function addDecision() {
  decisions.value = [
    ...decisions.value,
    {
      id: `decision-${Date.now()}`,
      action: '',
      owner: '值班医生',
      deadline: '6h',
      monitoring: '按系统指标复评',
      review_time: '6h',
      status: 'pending',
      note: '',
    },
  ]
}

function removeDecision(id: string) {
  decisions.value = decisions.value.filter((item: any) => item.id !== id)
}

function openPatientDetail() {
  if (!selectedPatientId.value) return
  router.push({ path: `/patient/${selectedPatientId.value}`, query: { tab: 'twin' } })
}

watch(() => route.query.patient_id ?? route.query.patientId, (value) => {
  const next = String(Array.isArray(value) ? value[0] : value || '').trim()
  if (next && next !== selectedPatientId.value) {
    selectedPatientId.value = next
  }
}, { immediate: true })

watch(selectedPatientId, (value) => {
  if (!value) return
  router.replace({ path: '/mdt', query: { ...route.query, patient_id: value } })
  void loadAssessment(false)
})

watch(trendWindow, () => {
  if (!selectedPatientId.value) return
  void loadWorkspaceExtras(selectedPatientId.value)
})

onMounted(async () => {
  try {
    await loadPatientOptions()
    if (!selectedPatientId.value && patientOptions.value.length) {
      selectedPatientId.value = patientOptions.value[0]?.value || ''
    }
  } catch {
    error.value = '患者列表加载失败'
  }
})
</script>

<style scoped>
.mdt-page {
  display: grid;
  gap: 14px;
  position: relative;
}
.mdt-page::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.015), transparent 18%),
    linear-gradient(90deg, rgba(125, 167, 214, 0.04) 1px, transparent 1px),
    linear-gradient(rgba(125, 167, 214, 0.03) 1px, transparent 1px);
  background-size: auto, 24px 24px, 24px 24px;
}
.mdt-hero,.mdt-panel {
  border-radius: 16px;
  border: 1px solid rgba(125, 167, 214, 0.18);
  background: linear-gradient(180deg, rgba(10, 22, 35, 0.985), rgba(8, 18, 30, 0.985));
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.14), inset 0 1px 0 rgba(255, 255, 255, 0.03);
}
.mdt-hero {
  position: relative;
  overflow: hidden;
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(340px, 0.85fr);
  gap: 18px;
  align-items: stretch;
  padding: 2px;
}
.mdt-hero__copy,.mdt-hero__side {
  position: relative;
  z-index: 1;
}
.mdt-hero__copy {
  display: grid;
  align-content: center;
  gap: 10px;
  padding: 16px 10px 16px 16px;
}
.mdt-kicker {
  color: #8eb6c9;
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.mdt-title {
  margin: 0;
  color: #eff7fb;
  font-size: clamp(26px, 2.5vw, 34px);
  line-height: 1.15;
  font-weight: 800;
  letter-spacing: -0.03em;
}
.mdt-desc {
  margin: 0;
  color: #9eb8c7;
  max-width: 680px;
  font-size: 13px;
  line-height: 1.7;
}
.mdt-hero__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.hero-badge {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 6px 10px;
  border-radius: 8px;
  background: rgba(18, 53, 76, 0.48);
  border: 1px solid rgba(125, 167, 214, 0.18);
  color: #dcebf3;
  font-size: 12px;
}
.hero-badge--soft {
  background: rgba(10, 21, 34, 0.72);
  color: #b4ccda;
}
.panel-select,
.field-input,
.field-textarea {
  width: 100%;
  border-radius: 8px;
  border: 1px solid rgba(125, 167, 214, 0.18);
  background: rgba(7, 17, 27, 0.94);
  color: #e4f0f6;
}
.panel-select,
.field-input {
  min-height: 34px;
  padding: 7px 10px;
}
.field-textarea {
  padding: 10px 12px;
  resize: vertical;
}
.field-textarea--lg {
  min-height: 180px;
}
.mdt-hero__side {
  display: grid;
  gap: 10px;
  padding: 14px 14px 14px 0;
}
.mdt-toolbar,
.mini-card {
  border-radius: 12px;
  border: 1px solid rgba(125, 167, 214, 0.18);
  background: linear-gradient(180deg, rgba(12, 24, 37, 0.94), rgba(9, 19, 30, 0.94));
}
.mdt-toolbar {
  display: grid;
  gap: 10px;
  padding: 14px;
}
.toolbar-label {
  color: #8ea8b8;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.mdt-toolbar__row,
.mdt-toolbar__actions,
.mdt-hero__mini {
  display: grid;
  gap: 10px;
}
.mdt-toolbar__actions,
.mdt-hero__mini {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.mdt-select {
  width: 100%;
  min-width: 0;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(125, 167, 214, 0.18);
  background: rgba(9, 18, 29, 0.95);
  color: #e4f0f6;
}
.mini-card {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
}
.mini-card span {
  color: #89a6b8;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.mini-card strong {
  color: #f1f7fb;
  font-size: 17px;
  line-height: 1.25;
}
.mini-card small {
  color: #a5bfcd;
  font-size: 12px;
  line-height: 1.55;
}
.mini-card--accent {
  background: linear-gradient(180deg, rgba(18, 38, 54, 0.96), rgba(10, 22, 33, 0.95));
}
.detail-label,.conflict-card__agents {
  color: #89a6b8;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.mdt-workspace {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}
.mdt-sidebar,
.mdt-content,
.mdt-content-grid {
  display: grid;
  gap: 12px;
}
.mdt-sidebar {
  position: sticky;
  top: 16px;
}
.patient-sheet {
  display: grid;
  gap: 12px;
}
.patient-sheet__name {
  color: #f2f8fb;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.03em;
}
.patient-sheet__sub {
  color: #9eb8c7;
  font-size: 13px;
  line-height: 1.7;
}
.patient-sheet__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.sheet-item {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(9, 20, 31, 0.76);
}
.sheet-item span {
  color: #89a6b8;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.sheet-item strong {
  color: #f3f8fb;
  font-size: 18px;
  line-height: 1.2;
}
.specialist-list {
  display: grid;
  gap: 8px;
}
.system-grid {
  display: grid;
  gap: 8px;
}
.system-card {
  display: grid;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(9, 20, 31, 0.86);
  cursor: pointer;
  transition: border-color .18s ease, background .18s ease, transform .18s ease;
}
.system-card:hover {
  transform: translateY(-1px);
  border-color: rgba(148, 163, 184, 0.28);
}
.system-card.is-active {
  border-color: rgba(96, 165, 250, 0.38);
  box-shadow: inset 3px 0 0 rgba(96, 165, 250, 0.92);
  background: linear-gradient(180deg, rgba(14, 27, 41, 0.96), rgba(9, 19, 30, 0.94));
}
.system-card__head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}
.system-card__domain {
  color: #f3f8fb;
  font-size: 14px;
  font-weight: 700;
}
.system-card__priority,
.system-card__status {
  color: #9eb8c7;
  font-size: 11px;
}
.system-card__summary {
  color: #cfdfe8;
  font-size: 12px;
  line-height: 1.6;
}
.specialist-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: start;
  padding: 12px 12px 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(9, 20, 31, 0.86);
  cursor: pointer;
  transition: border-color .18s ease, background .18s ease, transform .18s ease;
}
.specialist-row:hover {
  transform: translateY(-1px);
  border-color: rgba(148, 163, 184, 0.28);
}
.specialist-row.is-active {
  border-color: rgba(96, 165, 250, 0.38);
  box-shadow: inset 3px 0 0 rgba(96, 165, 250, 0.92);
  background: linear-gradient(180deg, rgba(14, 27, 41, 0.96), rgba(9, 19, 30, 0.94));
}
.specialist-row__main {
  display: grid;
  gap: 5px;
}
.specialist-row__domain {
  color: #f3f8fb;
  font-size: 14px;
  font-weight: 700;
}
.specialist-row__summary {
  color: #cfdfe8;
  font-size: 12px;
  line-height: 1.6;
}
.specialist-row__meta {
  color: #9eb8c7;
  font-size: 11px;
  white-space: nowrap;
}
.mdt-content-grid {
  grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
}
.section-kicker {
  color: #8ea8b8;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}
.deep-panel-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
  gap: 12px;
}
.deep-panel {
  display: grid;
  gap: 10px;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(9, 20, 31, 0.82);
}
.deep-panel__title {
  color: #f1f7fb;
  font-size: 14px;
  font-weight: 700;
}
.deep-panel__body {
  display: grid;
  gap: 10px;
}
.trend-placeholder {
  display: grid;
  gap: 10px;
}
.trend-placeholder__header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  color: #cfe0ea;
  font-size: 12px;
}
.trend-placeholder__chart {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  align-items: end;
  gap: 6px;
  min-height: 92px;
}
.trend-placeholder__chart span {
  border-radius: 6px 6px 0 0;
  background: linear-gradient(180deg, rgba(96, 165, 250, 0.78), rgba(29, 78, 216, 0.18));
}
.trend-placeholder__chart span:nth-child(1) { height: 28%; }
.trend-placeholder__chart span:nth-child(2) { height: 42%; }
.trend-placeholder__chart span:nth-child(3) { height: 36%; }
.trend-placeholder__chart span:nth-child(4) { height: 58%; }
.trend-placeholder__chart span:nth-child(5) { height: 54%; }
.trend-placeholder__chart span:nth-child(6) { height: 74%; }
.trend-placeholder__chart span:nth-child(7) { height: 66%; }
.trend-placeholder__chart span:nth-child(8) { height: 82%; }
.trend-placeholder__chart span:nth-child(9) { height: 63%; }
.trend-placeholder__chart span:nth-child(10) { height: 48%; }
.trend-placeholder__chart span:nth-child(11) { height: 57%; }
.trend-placeholder__chart span:nth-child(12) { height: 44%; }
.trend-placeholder__caption {
  color: #9eb8c7;
  font-size: 12px;
  line-height: 1.6;
}
.trend-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.trend-metrics__item {
  display: grid;
  gap: 3px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(11, 24, 36, 0.76);
  border: 1px solid rgba(125, 167, 214, 0.12);
}
.trend-metrics__item span {
  color: #89a6b8;
  font-size: 11px;
}
.trend-metrics__item strong {
  color: #dfeef6;
  font-size: 11px;
  line-height: 1.5;
}
.assistant-note {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(12, 26, 40, 0.86);
}
.assistant-note__label {
  color: #89a6b8;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.assistant-note__text {
  color: #d8e8f1;
  font-size: 12px;
  line-height: 1.7;
}
.detail-timeline {
  display: grid;
  gap: 8px;
}
.timeline-item {
  display: grid;
  gap: 3px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(11, 24, 36, 0.76);
}
.timeline-item strong {
  color: #f1f7fb;
  font-size: 12px;
}
.timeline-item span,
.timeline-item small {
  color: #b7cfdb;
  font-size: 11px;
  line-height: 1.6;
}
.alert-chain,
.impact-list,
.decision-list {
  display: grid;
  gap: 10px;
}
.alert-chain__item,
.impact-card,
.decision-item {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(9, 20, 31, 0.86);
}
.alert-chain__time,
.impact-card__title {
  color: #8ea8b8;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.alert-chain__text,
.impact-card__text,
.decision-item__text {
  color: #d7e7f0;
  font-size: 12px;
  line-height: 1.7;
}
.alert-chain__sub,
.impact-card__sub {
  color: #9eb8c7;
  font-size: 11px;
  line-height: 1.6;
}
.decision-item__head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.decision-item__head strong {
  color: #f3f8fb;
  font-size: 13px;
}
.decision-item__head span,
.decision-item__meta span {
  color: #9eb8c7;
  font-size: 11px;
}
.decision-item__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.decision-form,
.decision-form__grid,
.doc-stack,
.doc-block,
.workspace-actions {
  display: grid;
  gap: 10px;
}
.decision-form__grid,
.doc-stack {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.mdt-panel--hero :deep(.ant-card-body) {
  display: grid;
  gap: 10px;
}
.summary-box,.empty-box,.error-box,.priority-card,.specialist-card,.conflict-card {
  border-radius: 12px;
  background: rgba(9, 20, 31, 0.92);
  border: 1px solid rgba(125, 167, 214, 0.14);
}
.summary-box,.empty-box,.error-box { padding: 14px 16px; color: #d8edf8; line-height: 1.75; }
.summary-box--hero {
  background: linear-gradient(180deg, rgba(13, 28, 42, 0.95), rgba(9, 19, 30, 0.96));
  border-color: rgba(125, 167, 214, 0.18);
  font-size: 13px;
}
.priority-row,.conflict-list,.detail-stack { display: grid; gap: 10px; }
.priority-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.priority-card,.conflict-card { padding: 13px 14px; }
.priority-card__head { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.priority-card__head strong,.conflict-card__title { color: #f3f8fb; font-size: 14px; font-weight: 700; }
.priority-card__main,.conflict-card__meta { margin-top: 8px; color: #d0e1eb; font-size: 12px; line-height: 1.7; }
.priority-card.is-critical { border-color: rgba(248, 113, 113, 0.32); }
.priority-card.is-high { border-color: rgba(251, 146, 60, 0.28); }
.priority-card.is-medium { border-color: rgba(96, 165, 250, 0.2); }
.chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.chip {
  padding: 5px 9px;
  border-radius: 8px;
  border: 1px solid rgba(125, 167, 214, 0.16);
  background: rgba(13, 31, 46, 0.86);
  color: #d6e7f1;
  font-size: 11px;
}
.mini-link { border: none; padding: 0; background: transparent; color: #9fc1d2; cursor: pointer; font-size: 12px; }
.detail-stack {
  gap: 10px;
}
.detail-block {
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(9, 23, 36, 0.82);
  border: 1px solid rgba(125, 167, 214, 0.12);
}
.action-list { margin: 10px 0 0; padding-left: 18px; color: #dbf0fa; display: grid; gap: 8px; }
.conflict-card__agents { margin-top: 6px; }
.error-box { background: rgba(127, 29, 29, 0.22); border-color: rgba(248, 113, 113, 0.24); color: #fecaca; }
@media (max-width: 1280px) {
  .mdt-hero,
  .mdt-workspace,
  .mdt-content-grid,
  .deep-panel-grid {
    grid-template-columns: 1fr;
  }
  .mdt-sidebar {
    position: static;
  }
}
@media (max-width: 1100px) {
  .priority-row,
  .patient-sheet__grid,
  .trend-metrics,
  .decision-form__grid,
  .doc-stack { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 720px) {
  .priority-row,
  .patient-sheet__grid,
  .mdt-toolbar__actions,
  .mdt-hero__mini,
  .trend-metrics,
  .decision-form__grid,
  .doc-stack { grid-template-columns: 1fr; }
  .mdt-select { min-width: 0; width: 100%; }
  .mdt-title { font-size: 28px; }
  .mdt-hero__copy,
  .mdt-hero__side { padding: 14px; }
}
</style>

