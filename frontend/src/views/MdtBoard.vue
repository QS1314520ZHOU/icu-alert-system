<template>
  <div class="mdt-page">
    <a-card :bordered="false" class="mdt-hero">
      <section class="mdt-command-center">
        <header class="mdt-command-top">
          <div class="mdt-command-title">
            <div class="mdt-kicker">ICU MDT</div>
            <h1 class="mdt-title">多学科会诊</h1>
            <p class="mdt-desc">先看哪个系统最危险，再决定谁来处理。</p>
          </div>
          <div class="mdt-hero__badges">
            <span class="hero-badge">{{ loading ? '会诊处理中' : '会诊就绪' }}</span>
            <span class="hero-badge hero-badge--soft">{{ selectedPatientLabel }}</span>
            <span class="hero-badge hero-badge--focus">聚焦 {{ activeSystemLabel }}</span>
            <span :class="['hero-badge', `hero-badge--${mdtSeverityTone}`]">风险 {{ mdtSeverityLabel }}</span>
            <span :class="['hero-badge', `hero-badge--${closureTone}`]">闭环 {{ closureLabel }}</span>
            <span v-if="workspaceDirty" class="hero-badge hero-badge--warning">未保存</span>
            <span v-if="isSessionClosed" class="hero-badge hero-badge--closed">已归档只读</span>
          </div>
        </header>

        <section v-if="viewMode === 'moderator'" class="mdt-simple-board">
          <section class="mdt-simple-left">
            <div class="simple-patient-card">
              <div>
                <span>当前患者</span>
                <strong>{{ patientHeadline }}</strong>
                <small>{{ patientSubline }}</small>
              </div>
              <select v-model="selectedPatientId" class="mdt-select">
                <option value="">选择患者</option>
                <option v-for="item in patientOptions" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
              <div class="simple-actions">
                <a-button type="primary" :loading="loading" @click="loadAssessment(true)">
                  {{ selectedPatientId ? '生成会诊' : '先选患者' }}
                </a-button>
                <a-button :disabled="!selectedPatientId" @click="openPatientDetail">患者详情</a-button>
                <a-button @click="viewMode = 'deep'">详细会诊</a-button>
              </div>
            </div>

            <div class="mdt-body-card">
              <OrganHeatmapFigure
                compact
                show-legend
                :organ-states="mdtOrganStates"
                :organ-tooltips="mdtOrganTooltips"
                @organ-click="handleMdtOrganClick"
              />
            </div>
          </section>

          <section class="mdt-simple-right">
            <article class="simple-card simple-card--summary">
              <span>总控结论</span>
              <strong>{{ mdtSeverityLabel }}</strong>
              <div class="moderator-metrics">
                <i><b :style="{ width: `${closurePercent}%` }"></b></i>
                <em>闭环 {{ closurePercent }}%</em>
              </div>
              <p>{{ shortMdtText(metaSummary, 38) }}</p>
            </article>

            <article class="simple-card simple-card--decisions">
              <div class="simple-card-head">
                <span>决议闭环</span>
                <strong>{{ pendingConfirmationCount + pendingDecisionCount + inProgressDecisionCount }}</strong>
              </div>
              <div class="decision-pill-row">
                <button
                  v-for="item in moderatorDecisionRows"
                  :key="item.id"
                  type="button"
                  :class="['decision-pill', `status-${item.status || 'pending'}`]"
                  @click="markDecisionDone(item)"
                >
                  <strong>{{ shortMdtText(item.action, 24) }}</strong>
                  <span>{{ item.owner || '责任人待定' }}</span>
                </button>
              </div>
            </article>

            <article class="simple-card">
              <div class="simple-card-head">
                <span>最危险器官</span>
                <strong>{{ mdtOrganRows[0]?.label || '暂无' }}</strong>
              </div>
              <div class="organ-pill-grid">
                <button
                  v-for="item in mdtOrganRows"
                  :key="item.agent"
                  type="button"
                  :class="['organ-pill', `is-${item.severity}`, { active: activeSpecialist?.agent === item.agent }]"
                  @click="selectSpecialist(item.agent)"
                >
                  <span>{{ item.label }}</span>
                  <b>{{ item.text }}</b>
                </button>
              </div>
            </article>

            <article class="simple-card">
              <div class="simple-card-head">
                <span>需要裁决</span>
                <strong>{{ conflictRows.length }} 项</strong>
              </div>
              <div v-if="conflictRows.length" class="simple-list">
                <div v-for="(item, idx) in conflictRows.slice(0, 3)" :key="`simple-conflict-${idx}`">
                  <strong>{{ shortMdtText(item.summary || '跨专科意见不一致', 34) }}</strong>
                  <span>{{ (item.agents || []).map(domainLabel).join(' / ') || '多专科' }}</span>
                </div>
              </div>
              <div v-else class="simple-empty">暂无明显冲突</div>
            </article>

            <article class="simple-card">
              <div class="simple-card-head">
                <span>下一步动作</span>
                <strong>{{ syncableAiActions.length || decisionRows.length }}</strong>
              </div>
              <div v-if="syncableAiActions.length" class="simple-list">
                <div v-for="item in syncableAiActions.slice(0, 3)" :key="item">
                  <strong>{{ shortMdtText(item, 38) }}</strong>
                </div>
              </div>
              <div v-else class="simple-empty">生成会诊后自动列出</div>
              <div class="simple-actions slim">
                <a-button size="small" type="primary" :disabled="isSessionClosed || !syncableAiActions.length" @click="syncDecisionsFromMetaActions">同步动作</a-button>
                <a-button size="small" :loading="savingWorkspace" :disabled="isSessionClosed" @click="saveWorkspace">保存</a-button>
              </div>
            </article>
          </section>
        </section>

        <section v-if="viewMode === 'deep'" class="mdt-flow">
          <article
            v-for="step in workflowSteps"
            :key="step.key"
            :class="['mdt-flow-step', { 'is-active': step.key === currentWorkflowStep, 'is-done': step.done }]"
          >
            <span class="mdt-flow-step__index">{{ step.index }}</span>
            <div>
              <strong>{{ step.title }}</strong>
              <small>{{ step.desc }}</small>
            </div>
          </article>
        </section>

        <section v-if="viewMode === 'deep'" class="mdt-clinical-strip">
          <article class="clinical-card clinical-card--patient">
            <div class="clinical-card__head">
              <span>患者入口</span>
              <strong>{{ patientHeadline }}</strong>
            </div>
            <select v-model="selectedPatientId" class="mdt-select">
              <option value="">选择患者</option>
              <option v-for="item in patientOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
            <div v-if="selectedPatientOutOfDeptHint" class="toolbar-hint">{{ selectedPatientOutOfDeptHint }}</div>
            <div class="clinical-actions">
              <a-button size="small" type="primary" :loading="loading" @click="loadAssessment(true)">刷新会诊</a-button>
              <a-button size="small" @click="openPatientDetail" :disabled="!selectedPatientId">患者详情</a-button>
              <select v-model="viewMode" class="mdt-select mdt-select--compact">
                <option value="moderator">主持视图</option>
                <option value="deep">深度视图</option>
              </select>
            </div>
          </article>

          <article class="clinical-card clinical-card--summary">
            <div class="clinical-card__head">
              <span>总控裁决</span>
              <strong>{{ metaSummary }}</strong>
            </div>
            <div class="clinical-actions">
              <a-button size="small" type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="saveWorkspace">保存会话</a-button>
              <a-button size="small" :loading="generatingDocType === 'mdt_summary'" :disabled="isSessionClosed" @click="generateDocument('mdt_summary')">生成材料</a-button>
              <a-button size="small" :disabled="!autoSessionSummary" @click="copyText(autoSessionSummary, '会诊摘要已复制')">复制摘要</a-button>
            </div>
          </article>

          <article class="clinical-card clinical-card--metrics">
            <div class="clinical-card__head">
              <span>临床态势</span>
              <strong>{{ mdtSeverityLabel }} · {{ closureLabel }}</strong>
            </div>
            <div class="clinical-metric-grid">
              <div v-for="item in cockpitMetricRows" :key="item.label" class="clinical-metric">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
              <div v-for="item in signalSourceRows" :key="item.label" class="clinical-metric">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <div class="closure-meter">
              <i :style="{ width: `${closurePercent}%` }"></i>
            </div>
          </article>

          <article class="clinical-card clinical-card--handoff">
            <div class="clinical-card__head">
              <span>冲突与下一步</span>
              <strong>{{ topConflictSummary }}</strong>
            </div>
            <div class="next-action-box">{{ nextActionText }}</div>
            <div v-if="ownerSummaryRows.length" class="owner-mini-list">
              <div v-for="item in ownerSummaryRows.slice(0, 3)" :key="item.owner" class="owner-mini-row">
                <strong>{{ item.owner }}</strong>
                <span>待 {{ item.pending }} / 进 {{ item.inProgress }} / 完 {{ item.completed }}</span>
              </div>
            </div>
          </article>
        </section>

        <section v-if="viewMode === 'deep'" class="mdt-clinical-meta">
          <div class="meta-edit-grid">
            <input v-model="tagsText" class="field-input" :disabled="isSessionClosed" placeholder="标签：如 脓毒症、撤机、高乳酸" />
            <input v-model="participantsText" class="field-input" :disabled="isSessionClosed" placeholder="参与成员：ICU、感染、呼吸、药学" />
            <textarea v-model="finalSummary" class="field-textarea" :disabled="isSessionClosed" rows="2" placeholder="最终纪要（留空则关闭会话时自动生成）"></textarea>
          </div>
          <div v-if="todoRows.length" class="todo-list todo-list--inline">
            <div v-for="item in todoRows.slice(0, 3)" :key="item.id" class="todo-row">
              <strong>{{ item.action }}</strong>
              <small>{{ item.owner }} / {{ item.deadline || '时限未填' }}</small>
            </div>
          </div>
        </section>
      </section>
    </a-card>

    <section v-if="viewMode === 'deep'" class="mdt-workspace">
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
            <article v-for="item in systemCards" :key="item.agent" :class="['system-card', `is-${item.priority || 'medium'}`, { 'is-active': activeSpecialist?.agent === item.agent }]" @click="selectSpecialist(item.agent)">
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
            <article v-for="item in specialistRows" :key="item.agent" :class="['specialist-row', `is-${item.priority || 'medium'}`, { 'is-active': activeSpecialist?.agent === item.agent }]" @click="selectSpecialist(item.agent)">
              <div class="specialist-row__main">
                <div class="specialist-row__domain">{{ domainLabel(item.domain) }}</div>
                <div class="specialist-row__summary">{{ item.summary || '暂无摘要' }}</div>
              </div>
              <div class="specialist-row__meta">
                <span>{{ priorityLabel(item.priority) }}</span>
                <span v-if="activeSpecialist?.agent === item.agent" class="row-active-chip">当前聚焦</span>
              </div>
            </article>
          </div>
          <div v-if="activeSpecialist" class="focus-specialist-card">
            <div class="focus-specialist-card__head">
              <strong>当前聚焦：{{ activeSystemLabel }}</strong>
              <span>{{ priorityLabel(activeSpecialist.priority) }}</span>
            </div>
            <div class="focus-specialist-card__summary">{{ activeSpecialist.summary || '暂无该专科摘要' }}</div>
            <div class="session-chip-row">
              <span class="session-chip">{{ (activeSpecialist.concerns || []).length }} 条关注点</span>
              <span class="session-chip">{{ (activeSpecialist.recommendations || []).length }} 条建议</span>
              <span class="session-chip">{{ (activeSpecialist.evidence || []).length }} 条证据</span>
            </div>
          </div>
          <div v-else-if="isGeneratingAssessment" class="empty-box">已选中患者，正在生成 MDT 会诊结果，请稍候。</div>
          <div v-else class="empty-box">选择患者后加载会诊结果。</div>
        </a-card>

        <a-card :bordered="false" class="mdt-panel" title="最近会诊会话">
          <div class="workspace-actions workspace-actions--top workspace-actions--sidebar">
              <a-button size="small" @click="startNewSession">新建会话</a-button>
              <a-button size="small" ghost :disabled="!currentSessionId" @click="duplicateCurrentSession">复制当前会话</a-button>
              <a-button size="small" ghost :disabled="!currentSessionId" @click="exportCurrentSession">导出会话</a-button>
              <a-button v-if="isSessionClosed" size="small" ghost @click="reopenCurrentSession">复开会话</a-button>
              <label class="inline-toggle">
                <input v-model="sessionListOpenOnly" type="checkbox">
                <span>仅看未关闭</span>
              </label>
          </div>
          <div class="workspace-actions workspace-actions--top workspace-actions--sidebar">
            <select v-model="selectedTemplateKey" class="panel-select">
              <option value="">选择会诊模板</option>
              <option v-for="item in sessionTemplates" :key="item.key" :value="item.key">{{ item.label }}</option>
            </select>
            <a-button size="small" ghost :disabled="isSessionClosed || !selectedTemplateKey" @click="applySessionTemplate">套用模板</a-button>
          </div>
          <div class="workspace-actions workspace-actions--top workspace-actions--sidebar">
            <input v-model="sessionSearch" class="field-input" placeholder="搜索会话标题/摘要" />
            <select v-model="sessionPhaseFilter" class="panel-select">
              <option value="">全部阶段</option>
              <option value="collecting">收集中</option>
              <option value="conflict_review">冲突评审</option>
              <option value="finalizing">裁决定稿</option>
              <option value="closed">已关闭</option>
            </select>
          </div>
          <div v-if="workspaceSessions.length" class="specialist-list">
            <article
              v-for="item in visibleWorkspaceSessions"
              :key="item.session_id"
              :class="['specialist-row', { 'is-active': currentSessionId === item.session_id }]"
              @click="switchSession(String(item.session_id || ''))"
            >
              <div class="specialist-row__main">
                <div class="system-card__domain">{{ item.title || 'MDT 会话' }}</div>
                <div class="specialist-row__summary">{{ item.summary || item.final_summary || '暂无摘要' }}</div>
                <div v-if="item.final_summary" class="specialist-row__summary muted-line">{{ item.final_summary }}</div>
              <div class="session-chip-row">
                  <span class="session-chip">{{ (item.decisions || []).length }} 条决议</span>
                  <span class="session-chip">{{ sessionCompletedCount(item) }}/{{ sessionDecisionCount(item) }} 完成</span>
                  <span v-if="sessionDecisionCount(item) > 0" :class="['session-chip', sessionCompletedCount(item) === sessionDecisionCount(item) ? 'session-chip--done' : 'session-chip--running']">
                    {{ sessionCompletedCount(item) === sessionDecisionCount(item) ? '已闭环' : '进行中' }}
                  </span>
                  <span v-if="item.template_name" class="session-chip session-chip--tag">模板 {{ templateLabel(item.template_name) }}</span>
                  <span v-if="sessionDecisionCount(item) > 0" class="session-chip">{{ sessionCompletionRate(item) }}%</span>
                  <span class="session-chip">{{ formatBeijingTime(item.updated_at) }}</span>
                  <span v-if="String(item.phase || '') === 'closed'" class="session-chip session-chip--closed">已关闭</span>
                  <span v-for="tag in (item.tags || []).slice(0, 3)" :key="`${item.session_id}-${tag}`" class="session-chip session-chip--tag">{{ tag }}</span>
                </div>
              </div>
              <div class="specialist-row__meta">
                <span>{{ phaseLabel(item.phase) }}</span>
                <button
                  v-if="currentSessionId === item.session_id && String(item.phase || '') !== 'closed'"
                  type="button"
                  class="mini-link"
                  @click.stop="closeCurrentSession"
                >
                  关闭
                </button>
              </div>
            </article>
          </div>
          <div v-else class="empty-box">当前患者暂无已保存 MDT 会话。</div>
        </a-card>
      </aside>

      <main :class="['mdt-content', `mdt-content--${viewMode}`]">
        <section class="mdt-moderator-board">
          <div class="mdt-primary-lane">
            <a-card :bordered="false" class="mdt-panel mdt-guide-panel">
              <div class="guide-header">
                <div>
                  <div class="section-kicker">今日会诊路径</div>
                  <h2>{{ primaryGuidanceTitle }}</h2>
                  <p>{{ primaryGuidanceText }}</p>
                </div>
                <div class="guide-score">
                  <span>闭环率</span>
                  <strong>{{ closurePercent }}%</strong>
                </div>
              </div>
              <div class="guide-actions">
                <a-button type="primary" :loading="loading" @click="loadAssessment(true)">
                  {{ selectedPatientId ? '刷新 MDT 会诊' : '先选择患者' }}
                </a-button>
                <a-button :disabled="isSessionClosed || !syncableAiActions.length" @click="syncDecisionsFromMetaActions">同步 AI 动作</a-button>
                <a-button :loading="savingWorkspace" :disabled="isSessionClosed" @click="saveWorkspace">保存会话</a-button>
              </div>
            </a-card>

            <a-card :bordered="false" class="mdt-panel" title="1. 总控结论">
              <div class="clinical-summary-layout">
                <div class="summary-box summary-box--hero">
                  {{ isGeneratingAssessment ? '总控智能体正在汇总专科意见、冲突焦点与优先级动作。' : metaSummary }}
                </div>
                <div class="clinical-facts">
                  <div class="clinical-fact">
                    <span>风险等级</span>
                    <strong>{{ mdtSeverityLabel }}</strong>
                  </div>
                  <div class="clinical-fact">
                    <span>当前阶段</span>
                    <strong>{{ currentPhaseLabel }}</strong>
                  </div>
                  <div class="clinical-fact">
                    <span>聚焦系统</span>
                    <strong>{{ activeSystemLabel }}</strong>
                  </div>
                </div>
              </div>
            </a-card>

            <a-card :bordered="false" class="mdt-panel" title="2. 冲突焦点与专科意见">
              <div class="mdt-review-grid">
                <section>
                  <div class="detail-label">需要主持人裁决</div>
                  <div v-if="conflictRows.length" class="conflict-list">
                    <article v-for="(item, idx) in conflictRows.slice(0, 4)" :key="`${item.type || 'conflict'}-${idx}`" class="conflict-card">
                      <div class="conflict-card__title">{{ item.summary || '存在跨专科冲突' }}</div>
                      <div class="conflict-card__agents">{{ (item.agents || []).map(domainLabel).join(' / ') || '多专科' }}</div>
                      <div class="conflict-card__meta">{{ item.resolution_focus || '需结合动态病情进一步裁决。' }}</div>
                    </article>
                  </div>
                  <div v-else-if="isGeneratingAssessment" class="empty-box">会诊生成中，正在汇总冲突焦点。</div>
                  <div v-else class="empty-box">当前没有明显冲突，可直接进入执行闭环。</div>
                </section>
                <section>
                  <div class="detail-label">当前专科意见 · {{ activeSystemLabel }}</div>
                  <div v-if="activeSpecialist" class="detail-stack">
                    <div class="summary-box">{{ activeSpecialist.summary || '暂无摘要' }}</div>
                    <div class="detail-block">
                      <div class="detail-label">建议动作</div>
                      <ul class="action-list">
                        <li v-for="(item, idx) in (activeSpecialist.recommendations || []).slice(0, 4)" :key="`moderator-rec-${idx}`">{{ item }}</li>
                      </ul>
                    </div>
                  </div>
                  <div v-else class="empty-box">点击左侧七大系统，查看对应专科意见。</div>
                </section>
              </div>
            </a-card>

            <a-card :bordered="false" class="mdt-panel" title="3. 决议记录与闭环">
              <div class="decision-command-strip">
                <div>
                  <div class="section-kicker">执行闭环</div>
                  <strong>{{ pendingConfirmationCount }} 项需医生确认</strong>
                  <span>{{ pendingDecisionCount + inProgressDecisionCount }} 项确认后推进，{{ completedDecisionCount }} 项已完成</span>
                </div>
                <div class="decision-command-actions">
                  <a-button size="small" :disabled="isSessionClosed || !decisionRows.length" @click="fillDecisionDefaults">补全字段</a-button>
                  <a-button size="small" @click="addDecision" :disabled="isSessionClosed">新增决议</a-button>
                  <a-button size="small" type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="saveWorkspace">保存决议</a-button>
                </div>
              </div>
              <div class="decision-summary-row">
                <div class="sheet-item">
                  <span>待医生确认</span>
                  <strong>{{ pendingConfirmationCount }}</strong>
                </div>
                <div class="sheet-item">
                  <span>确认后待执行</span>
                  <strong>{{ pendingDecisionCount }}</strong>
                </div>
                <div class="sheet-item">
                  <span>进行中</span>
                  <strong>{{ inProgressDecisionCount }}</strong>
                </div>
                <div class="sheet-item">
                  <span>已完成</span>
                  <strong>{{ completedDecisionCount }}</strong>
                </div>
                <div class="sheet-item">
                  <span>已取消</span>
                  <strong>{{ dismissedDecisionCount }}</strong>
                </div>
              </div>
              <div class="workspace-actions workspace-actions--top">
                <a-button size="small" :disabled="isSessionClosed" @click="setPhase('collecting')">收集中</a-button>
                <a-button size="small" :disabled="isSessionClosed" @click="setPhase('conflict_review')">冲突评审</a-button>
                <a-button size="small" type="primary" :disabled="isSessionClosed" @click="setPhase('finalizing')">裁决定稿</a-button>
                <label class="inline-toggle">
                  <input v-model="decisionOpenOnly" type="checkbox">
                  <span>只看未闭环</span>
                </label>
              </div>
              <div class="decision-list decision-list--guided">
                <article v-for="(item, idx) in guidedDecisionRows" :key="item.id || `guided-decision-${idx}`" class="decision-item">
                  <div class="decision-item__head">
                    <strong>决议 {{ Number(idx) + 1 }}</strong>
                    <span>{{ decisionStatusLabel(item.status) }}</span>
                  </div>
                  <div class="decision-form">
                    <input v-model="item.action" class="field-input" :disabled="isSessionClosed" placeholder="输入 MDT 决议动作" />
                    <div class="decision-form__grid">
                      <input v-model="item.owner" class="field-input" :disabled="isSessionClosed" placeholder="负责人" />
                      <input v-model="item.deadline" class="field-input" :disabled="isSessionClosed" placeholder="执行时限" />
                      <input v-model="item.monitoring" class="field-input" :disabled="isSessionClosed" placeholder="监测指标" />
                      <select v-model="item.status" class="panel-select" :disabled="isSessionClosed">
                        <option value="pending_confirmation">待医生确认</option>
                        <option value="doctor_confirmed">医生已确认</option>
                        <option value="pending">确认后待执行</option>
                        <option value="in_progress">进行中</option>
                        <option value="completed">已完成</option>
                        <option value="rejected">医生不采纳</option>
                        <option value="needs_revision">需修改</option>
                        <option value="dismissed">已取消</option>
                      </select>
                    </div>
                    <div v-if="item.requires_confirmation !== false" class="decision-safety">
                      AI 生成内容仅为待审核建议草案，不能作为医嘱直接执行；必须由执业医生结合床旁情况确认。
                    </div>
                  </div>
                  <div class="decision-item__meta">
                    <button v-if="needsDoctorConfirmation(item)" type="button" class="mini-link" :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)" @click="confirmDecision(item, 'confirm')">医生确认</button>
                    <button v-if="needsDoctorConfirmation(item)" type="button" class="mini-link" :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)" @click="confirmDecision(item, 'reject')">不采纳</button>
                    <button v-if="!needsDoctorConfirmation(item)" type="button" class="mini-link" :disabled="isSessionClosed" @click="markDecisionStatus(item.id, 'completed')">标记完成</button>
                    <button type="button" class="mini-link" :disabled="isSessionClosed" @click="removeDecision(item.id)">删除</button>
                  </div>
                </article>
              </div>
            </a-card>
          </div>

          <aside class="mdt-action-rail">
            <a-card :bordered="false" class="mdt-panel" title="主持人下一步">
              <div class="next-action-box next-action-box--large">{{ nextActionText }}</div>
              <div v-if="todoRows.length" class="todo-list">
                <div v-for="item in todoRows.slice(0, 4)" :key="item.id" class="todo-row">
                  <strong>{{ item.action }}</strong>
                  <small>{{ item.owner }} / {{ item.deadline || '时限未填' }}</small>
                </div>
              </div>
            </a-card>

            <a-card :bordered="false" class="mdt-panel" title="会诊信息">
              <div class="meta-edit-grid">
                <input v-model="tagsText" class="field-input" :disabled="isSessionClosed" placeholder="标签：脓毒症、撤机、高乳酸" />
                <input v-model="participantsText" class="field-input" :disabled="isSessionClosed" placeholder="参与成员：ICU、感染、呼吸、药学" />
                <textarea v-model="finalSummary" class="field-textarea" :disabled="isSessionClosed" rows="4" placeholder="最终纪要（留空则关闭会话时自动生成）"></textarea>
              </div>
            </a-card>

            <a-card :bordered="false" class="mdt-panel" title="文书与归档">
              <div class="doc-status-board doc-status-board--rail">
                <article v-for="item in documentStatusRows" :key="item.key" class="doc-status-card">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.status }}</strong>
                  <small>{{ item.detail }}</small>
                </article>
              </div>
              <div class="workspace-actions">
                <a-button size="small" :loading="generatingDocType === 'consultation_request'" @click="generateDocument('consultation_request')">生成会诊记录</a-button>
                <a-button size="small" :loading="generatingDocType === 'daily_progress'" @click="generateDocument('daily_progress')">生成病程</a-button>
              </div>
            </a-card>

            <a-card :bordered="false" class="mdt-panel" title="最近会话">
              <div class="workspace-actions workspace-actions--top workspace-actions--sidebar">
                <a-button size="small" @click="startNewSession">新建</a-button>
                <a-button size="small" :disabled="!currentSessionId" @click="duplicateCurrentSession">复制</a-button>
                <a-button size="small" :disabled="!currentSessionId" @click="exportCurrentSession">导出</a-button>
              </div>
              <div v-if="visibleWorkspaceSessions.length" class="session-compact-list">
                <button
                  v-for="item in visibleWorkspaceSessions.slice(0, 5)"
                  :key="item.session_id"
                  type="button"
                  :class="['session-compact-item', { 'is-active': currentSessionId === item.session_id }]"
                  @click="switchSession(String(item.session_id || ''))"
                >
                  <strong>{{ item.title || 'MDT 会话' }}</strong>
                  <span>{{ phaseLabel(item.phase) }} · {{ formatBeijingTime(item.updated_at) }}</span>
                </button>
              </div>
              <div v-else class="empty-box">当前患者暂无已保存 MDT 会话。</div>
            </a-card>
          </aside>
        </section>

        <a-card v-if="viewMode === 'deep'" :bordered="false" class="mdt-panel mdt-panel--hero" :title="`${activeSystemLabel} 详细分析`">
          <div class="section-kicker">专科深度面板</div>
          <div class="summary-box summary-box--hero">{{ isGeneratingAssessment ? '总控智能体正在汇总专科意见、冲突焦点与优先级动作。' : metaSummary }}</div>
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
                      <small>{{ formatBeijingTime(item.time) }}</small>
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
                      <small>{{ formatBeijingTime(item.time) }}</small>
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
                      <strong>{{ item.mode || activeSystemPanel.latest?.mode || '通气支持' }}</strong>
                      <span>FiO2 {{ item.fio2 ?? '—' }} / PEEP {{ item.peep ?? '—' }} / RR {{ item.rr ?? '—' }} / Vte {{ item.vte ?? '—' }}</span>
                      <small>{{ formatBeijingTime(item.time) }}</small>
                    </article>
                  </div>
                </template>
                <template v-else>
                  <div class="assistant-note">
                    <div class="assistant-note__label">类型判断</div>
                    <div class="assistant-note__text">{{ activeSpecialist?.summary || '暂无系统级判断' }}</div>
                  </div>
                  <div class="assistant-note">
                    <div class="assistant-note__label">证据</div>
                    <div class="assistant-note__text">{{ activeSpecialistEvidence }}</div>
                  </div>
                  <div class="assistant-note">
                    <div class="assistant-note__label">建议</div>
                    <div class="assistant-note__text">{{ activeSpecialistSuggestion }}</div>
                  </div>
                </template>
              </div>
            </section>
          </div>
        </a-card>

        <div v-if="viewMode === 'deep'" class="mdt-content-grid">
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
                <div class="impact-card__title">{{ item.mode || activeSystemPanel.latest?.mode || '通气支持' }}</div>
                <div class="impact-card__text">FiO2 {{ item.fio2 ?? '—' }} / PEEP {{ item.peep ?? '—' }} / RR {{ item.rr ?? '—' }} / PIP {{ item.pip ?? '—' }}</div>
                <div class="impact-card__sub">{{ formatBeijingTime(item.time) }}</div>
              </article>
            </div>
            <div v-else-if="filteredDrugs.length" class="impact-list">
              <article v-for="item in filteredDrugs" :key="`${item.drugName}-${item.executeTime}`" class="impact-card">
                <div class="impact-card__title">{{ item.drugName || item.orderName || '用药' }}</div>
                <div class="impact-card__text">
                  {{ item.dose || '--' }}{{ item.doseUnit || '' }} / {{ item.route || '给药途径未记载' }} / {{ item.frequency || '频次未记载' }}
                </div>
                <div class="impact-card__sub">{{ formatBeijingTime(item.executeTime, '执行时间未记载') }}</div>
              </article>
            </div>
            <div v-else class="empty-box">当前系统暂无明显相关结构化事件。</div>
          </a-card>
        </div>

        <div v-if="viewMode === 'deep'" :class="['mdt-content-grid', 'mdt-grid--timeline']">
          <a-card :bordered="false" class="mdt-panel" title="MDT 冲突高亮">
            <div v-if="conflictRows.length" class="conflict-list">
              <article v-for="(item, idx) in conflictRows" :key="`${item.type || 'conflict'}-${idx}`" class="conflict-card">
                <div class="conflict-card__title">{{ item.summary || '存在跨专科冲突' }}</div>
                <div class="conflict-card__agents">{{ (item.agents || []).map(domainLabel).join(' / ') || '多专科' }}</div>
                <div class="conflict-card__meta">{{ item.resolution_focus || '需结合动态病情进一步裁决。' }}</div>
              </article>
            </div>
            <div v-else-if="isGeneratingAssessment" class="empty-box">会诊生成中，正在汇总冲突焦点与总控智能体裁决。</div>
            <div v-else class="empty-box">当前未识别到明显跨专科冲突，可继续按总控智能体裁决跟踪执行。</div>
          </a-card>

          <a-card v-if="viewMode === 'deep'" :bordered="false" class="mdt-panel" title="冲突解释面板">
            <div v-if="conflictExplainRows.length" class="detail-stack">
              <div v-for="item in conflictExplainRows" :key="item.id" class="impact-card">
                <div class="impact-card__title">{{ item.title }}</div>
                <div class="impact-card__text">涉及专科：{{ item.agents }}</div>
                <div class="impact-card__sub">{{ item.focus }}</div>
              </div>
            </div>
            <div v-else class="empty-box">当前没有需要额外解释的跨专科冲突。</div>
          </a-card>

          <a-card :bordered="false" class="mdt-panel" :title="`专科意见与智能预填充 · ${activeSystemLabel}`">
            <div v-if="activeSpecialist" class="detail-stack">
              <div class="summary-box">{{ activeSpecialist.summary || '暂无摘要' }}</div>
              <div class="detail-block">
                <div class="detail-label">该专科视角评估</div>
                <ul class="action-list">
                  <li v-for="(item, idx) in activeSpecialist.concerns || []" :key="`concern-${idx}`">{{ item }}</li>
                </ul>
              </div>
              <div class="detail-block">
                <div class="detail-label">智能预填充建议</div>
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
            <div v-else-if="isGeneratingAssessment" class="empty-box">专科智能体正在生成细化意见与建议动作。</div>
            <div v-else class="empty-box">点击左侧专科卡片后查看详细意见。</div>
          </a-card>
        </div>

        <div v-if="viewMode === 'deep'" :class="['mdt-content-grid', 'mdt-grid--decisions']">
          <a-card :bordered="false" class="mdt-panel" title="会诊活动时间线">
            <div v-if="activityTimelineRows.length" class="detail-timeline">
              <article v-for="item in activityTimelineRows" :key="item.id" class="timeline-item">
                <strong>{{ item.title }}</strong>
                <span>{{ item.detail }}</span>
                <small>{{ item.timeLabel }}</small>
              </article>
            </div>
            <div v-else class="empty-box">当前会话尚未形成活动轨迹，保存、切换阶段或推进决议后会自动沉淀时间线。</div>
          </a-card>

          <a-card :bordered="false" class="mdt-panel" title="会诊模板与归档摘要">
            <div class="impact-list">
              <article v-for="item in sessionTemplates" :key="item.key" class="impact-card">
                <div class="impact-card__title">{{ item.label }}</div>
                <div class="impact-card__text">{{ item.summary }}</div>
                <div class="impact-card__sub">{{ item.tags.join(' / ') || '未设标签' }}</div>
              </article>
              <article v-if="workspaceRecord?.template_name || finalSummary" class="impact-card">
                <div class="impact-card__title">当前会话归档信息</div>
                <div class="impact-card__text">模板：{{ workspaceRecord?.template_name ? templateLabel(workspaceRecord.template_name) : '未使用模板' }}</div>
                <div class="impact-card__sub">{{ finalSummary || '尚未生成最终纪要' }}</div>
              </article>
            </div>
          </a-card>
        </div>

        <div v-if="viewMode === 'deep'" :class="['mdt-content-grid', 'mdt-grid--assessment']">
          <a-card v-if="viewMode === 'deep'" :bordered="false" class="mdt-panel" title="总控智能体全局优先级">
            <div v-if="priorityRows.length" class="priority-row">
              <article v-for="item in priorityRows" :key="`${item.agent}-${item.domain}`" :class="['priority-card', `is-${item.priority || 'medium'}`]">
                <div class="priority-card__head">
                  <strong>{{ domainLabel(item.domain) }}</strong>
                  <span>{{ priorityLabel(item.priority) }}</span>
                </div>
                <div class="priority-card__main">{{ item.summary || '待补充摘要' }}</div>
              </article>
            </div>
            <div v-else class="empty-box">等待总控智能体汇总全局优先级。</div>
          </a-card>

          <a-card :bordered="false" class="mdt-panel" title="决议记录与执行追踪">
            <div class="decision-command-strip">
              <div>
                <div class="section-kicker">执行驾驶舱</div>
              <strong>{{ pendingConfirmationCount }} 项需医生确认</strong>
                <span>{{ pendingDecisionCount + inProgressDecisionCount }} 项确认后推进，{{ completedDecisionCount }} 项已闭环</span>
              </div>
              <div class="decision-command-actions">
                <a-button size="small" :disabled="isSessionClosed || !syncableAiActions.length" @click="syncDecisionsFromMetaActions">同步 AI 动作</a-button>
                <a-button size="small" :disabled="isSessionClosed || !decisionRows.length" @click="fillDecisionDefaults">补全默认字段</a-button>
                <a-button size="small" type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="saveWorkspace">保存</a-button>
              </div>
            </div>
            <div class="decision-summary-row">
              <div class="sheet-item">
                <span>待医生确认</span>
                <strong>{{ pendingConfirmationCount }}</strong>
              </div>
              <div class="sheet-item">
                <span>确认后待执行</span>
                <strong>{{ pendingDecisionCount }}</strong>
              </div>
              <div class="sheet-item">
                <span>进行中</span>
                <strong>{{ inProgressDecisionCount }}</strong>
              </div>
              <div class="sheet-item">
                <span>已完成</span>
                <strong>{{ completedDecisionCount }}</strong>
              </div>
              <div class="sheet-item">
                <span>已取消</span>
                <strong>{{ dismissedDecisionCount }}</strong>
              </div>
            </div>
            <div class="workspace-actions workspace-actions--top">
              <a-button size="small" :disabled="isSessionClosed" @click="setPhase('collecting')">收集中</a-button>
              <a-button size="small" :disabled="isSessionClosed" @click="setPhase('conflict_review')">冲突评审</a-button>
              <a-button size="small" type="primary" :disabled="isSessionClosed" @click="setPhase('finalizing')">裁决定稿</a-button>
              <label class="inline-toggle">
                <input v-model="decisionOpenOnly" type="checkbox">
                <span>只看未闭环</span>
              </label>
            </div>
            <div class="workspace-actions workspace-actions--top workspace-actions--sidebar">
              <select v-model="decisionOwnerFilter" class="panel-select">
                <option value="">全部负责人</option>
                <option v-for="item in decisionOwnerOptions" :key="item" :value="item">{{ item }}</option>
              </select>
              <div class="decision-batch-actions">
                <a-button size="small" :disabled="isSessionClosed || !currentSessionId" @click="markVisibleDecisions('doctor_confirmed')">批量确认</a-button>
                <a-button size="small" type="primary" :disabled="isSessionClosed" @click="markVisibleDecisions('completed')">批量完成</a-button>
              </div>
            </div>
            <div class="decision-buckets">
              <section v-for="bucket in decisionBuckets" :key="bucket.key" class="decision-bucket">
                <div class="decision-bucket__head">
                  <strong>{{ bucket.label }}</strong>
                  <span>{{ bucket.items.length }} 条</span>
                </div>
                <div class="decision-list">
                  <article v-for="(item, idx) in bucket.items" :key="item.id || `decision-${idx}`" class="decision-item">
                    <div class="decision-item__head">
                      <strong>决议 {{ Number(idx) + 1 }}</strong>
                      <span>{{ bucket.label }}</span>
                    </div>
                    <div class="decision-form">
                      <input v-model="item.action" class="field-input" :disabled="isSessionClosed" placeholder="输入 MDT 决议动作" />
                      <div class="decision-form__grid">
                        <input v-model="item.owner" class="field-input" :disabled="isSessionClosed" placeholder="负责人" />
                        <input v-model="item.deadline" class="field-input" :disabled="isSessionClosed" placeholder="执行时限" />
                        <input v-model="item.monitoring" class="field-input" :disabled="isSessionClosed" placeholder="监测指标" />
                        <input v-model="item.review_time" class="field-input" :disabled="isSessionClosed" placeholder="复评时间" />
                        <select v-model="item.status" class="panel-select" :disabled="isSessionClosed">
                          <option value="pending_confirmation">待医生确认</option>
                          <option value="doctor_confirmed">医生已确认</option>
                          <option value="pending">确认后待执行</option>
                          <option value="in_progress">进行中</option>
                          <option value="completed">已完成</option>
                          <option value="rejected">医生不采纳</option>
                          <option value="needs_revision">需修改</option>
                          <option value="dismissed">已取消</option>
                        </select>
                      </div>
                      <div v-if="item.requires_confirmation !== false" class="decision-safety">
                        AI 生成内容仅为待审核建议草案，不能作为医嘱直接执行；必须由执业医生结合床旁情况确认。
                      </div>
                      <textarea v-model="item.note" class="field-textarea" :disabled="isSessionClosed" rows="2" placeholder="补充说明 / 平衡方案"></textarea>
                    </div>
                    <div class="decision-item__meta">
                      <span>状态：{{ decisionStatusLabel(item.status) }}</span>
                      <button
                        v-if="needsDoctorConfirmation(item)"
                        type="button"
                        class="mini-link"
                        :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)"
                        @click="confirmDecision(item, 'confirm')"
                      >
                        医生确认
                      </button>
                      <button
                        v-if="needsDoctorConfirmation(item)"
                        type="button"
                        class="mini-link"
                        :disabled="isSessionClosed || confirmingDecisionIds.has(item.id)"
                        @click="confirmDecision(item, 'reject')"
                      >
                        不采纳
                      </button>
                      <button
                        v-if="!needsDoctorConfirmation(item) && String(item.status || 'pending') !== 'completed'"
                        type="button"
                        class="mini-link"
                        :disabled="isSessionClosed"
                        @click="markDecisionStatus(item.id, 'completed')"
                      >
                        标记完成
                    </button>
                    <button
                        v-else-if="!needsDoctorConfirmation(item)"
                        type="button"
                        class="mini-link"
                        :disabled="isSessionClosed"
                        @click="markDecisionStatus(item.id, 'doctor_confirmed')"
                      >
                        重新打开
                      </button>
                      <button type="button" class="mini-link" :disabled="isSessionClosed" @click="removeDecision(item.id)">删除</button>
                    </div>
                  </article>
                </div>
              </section>
            </div>
            <div class="workspace-actions">
              <a-button size="small" :disabled="isSessionClosed" @click="addDecision">新增决议</a-button>
              <a-button size="small" type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="saveWorkspace">保存决议</a-button>
            </div>
          </a-card>
        </div>

        <div v-if="viewMode === 'deep'" :class="['mdt-content-grid', 'mdt-grid--documents']">
          <a-card :bordered="false" class="mdt-panel" title="会诊记录 / 病程记录">
            <div class="doc-status-board">
              <article v-for="item in documentStatusRows" :key="item.key" class="doc-status-card">
                <span>{{ item.label }}</span>
                <strong>{{ item.status }}</strong>
                <small>{{ item.detail }}</small>
              </article>
            </div>
            <div class="doc-stack">
              <div class="doc-block">
                <div class="detail-label">MDT 会诊记录</div>
                <textarea v-model="consultRecord" class="field-textarea field-textarea--lg" :disabled="isSessionClosed" rows="8" placeholder="可先编辑，再一键保存或用智能生成。"></textarea>
                <div class="workspace-actions">
                  <a-button size="small" :disabled="isSessionClosed" :loading="generatingDocType === 'mdt_summary'" @click="generateDocument('mdt_summary')">智能生成讨论材料</a-button>
                  <a-button size="small" :disabled="isSessionClosed" :loading="generatingDocType === 'consultation_request'" @click="generateDocument('consultation_request')">智能生成会诊记录</a-button>
                </div>
              </div>
              <div class="doc-block">
                <div class="detail-label">病程记录</div>
                <textarea v-model="progressRecord" class="field-textarea field-textarea--lg" :disabled="isSessionClosed" rows="8" placeholder="将 MDT 讨论要点整合进当日病程记录。"></textarea>
                <div class="workspace-actions">
                  <a-button size="small" :disabled="isSessionClosed" :loading="generatingDocType === 'daily_progress'" @click="generateDocument('daily_progress')">智能生成病程记录</a-button>
                  <a-button size="small" type="primary" :loading="savingWorkspace" :disabled="isSessionClosed" @click="saveWorkspace">保存文书</a-button>
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
                  <span>{{ priorityLabel(item.priority) }}</span>
                </div>
                <textarea v-model="item.order_text" class="field-textarea" :disabled="isSessionClosed" rows="3"></textarea>
                <div class="decision-item__meta">
                  <span>状态：{{ ({ pending: '待执行', in_progress: '进行中', completed: '已完成', dismissed: '已取消', draft: '草稿' } as Record<string, string>)[String(item.status || 'draft').toLowerCase()] || '草稿' }}</span>
                  <span>来源：{{ item.source === 'mdt_workspace' ? 'MDT 工作台' : (item.source || 'MDT 工作台') }}</span>
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
import { Button as AButton, Card as ACard, message } from 'ant-design-vue'
import {
  generateAiDocument,
  getAiMdtWorkspace,
  getAiMdtWorkspaceSession,
  getAiMultiAgentAssessment,
  getAiSystemPanels,
  getPatientAlerts,
  getPatientDetail,
  getPatientDrugs,
  getPatientVitalsTrend,
  getPatients,
  listAiMdtWorkspaceSessions,
  postAiMdtDecisionConfirm,
  saveAiMdtWorkspace,
} from '../api'
import OrganHeatmapFigure from '../components/common/OrganHeatmapFigure.vue'
import { formatBeijingTime } from '../utils/time'
import { getOperatorIdentity } from '../utils/operatorIdentity'
import { BODY_MAP_ORGAN_LABELS, bodyMapSeverityText, type BodyMapOrganKey, type BodyMapSeverity } from '../utils/bodyMap'

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
const finalSummary = ref('')
const participantsText = ref('')
const tagsText = ref('')
const savingWorkspace = ref(false)
const generatingDocType = ref('')
const workspaceSessions = ref<any[]>([])
const currentSessionId = ref('')
const viewMode = ref<'moderator' | 'deep'>('moderator')
const sessionListOpenOnly = ref(true)
const decisionOpenOnly = ref(true)
const sessionSearch = ref('')
const sessionPhaseFilter = ref('')
const decisionOwnerFilter = ref('')
const lastSavedSnapshot = ref('')
const selectedTemplateKey = ref('')
const activityLog = ref<any[]>([])
const confirmingDecisionIds = ref<Set<string>>(new Set())

const sessionTemplates = [
  {
    key: 'sepsis',
    label: '脓毒症会诊',
    summary: '围绕感染控制、循环复苏、乳酸下降与器官支持快速形成一轮 MDT 处置。',
    tags: ['脓毒症', '感染', '循环'],
    participants: ['ICU', '感染', '呼吸', '药学'],
    decisions: [
      { action: '1小时内复核血培养与抗菌药覆盖', owner: '感染科', deadline: '1h', monitoring: '培养结果 / PCT / CRP', review_time: '6h' },
      { action: '按乳酸与灌注指标评估复苏目标', owner: 'ICU主治', deadline: '立即', monitoring: 'MAP / 乳酸 / 尿量', review_time: '2h' },
      { action: '评估呼吸支持与撤机窗口', owner: '呼吸治疗师', deadline: '6h', monitoring: 'SpO2 / P/F / RR', review_time: '6h' },
    ],
  },
  {
    key: 'weaning',
    label: '撤机失败复评',
    summary: '聚焦通气参数、镇静谵妄、循环耐受与营养储备，快速定位撤机失败主因。',
    tags: ['撤机', '呼吸', '谵妄'],
    participants: ['ICU', '呼吸治疗', '神经', '营养'],
    decisions: [
      { action: '复核呼吸机参数与自主呼吸试验失败原因', owner: '呼吸治疗师', deadline: '立即', monitoring: 'FiO2 / PEEP / RR / Vte', review_time: '4h' },
      { action: '调整镇静镇痛并筛查谵妄', owner: '值班医生', deadline: '2h', monitoring: 'RASS / CAM-ICU', review_time: '4h' },
      { action: '补齐营养与肌力评估', owner: '营养师', deadline: '12h', monitoring: '蛋白 / 摄入量 / 肌力', review_time: '24h' },
    ],
  },
  {
    key: 'renal',
    label: '肾替代治疗评审',
    summary: '针对 AKI/CRRT 患者统一评审液体平衡、电解质与抗感染剂量调整。',
    tags: ['CRRT', 'AKI', '液体管理'],
    participants: ['ICU', '肾内', '药学'],
    decisions: [
      { action: '复核 CRRT 指征与超滤目标', owner: '肾内科', deadline: '2h', monitoring: '尿量 / 肌酐 / 酸碱', review_time: '6h' },
      { action: '同步调整肾功能相关药物剂量', owner: '临床药师', deadline: '4h', monitoring: '药物暴露 / 肾功能', review_time: '12h' },
      { action: '更新液体出入平衡与血流动力学策略', owner: 'ICU主治', deadline: '立即', monitoring: '净平衡 / MAP / 乳酸', review_time: '6h' },
    ],
  },
] as const

const patientOptions = computed(() =>
  patients.value.map((item: any) => ({
    value: String(item?._id || ''),
    label: `${item?.hisBed || '--'}床 · ${item?.name || item?.hisName || '未知患者'} · ${item?.clinicalDiagnosis || item?.admissionDiagnosis || '暂无诊断'}${item?.__mdtFallbackCurrent ? ' · 当前已选（非当前科室在线）' : ''}`,
  }))
)
const assessmentRecord = computed(() => assessment.value?.assessment || assessment.value || null)
const assessmentResult = computed(() => assessmentRecord.value?.result || assessmentRecord.value || {})
const specialistRows = computed(() => Object.values(assessmentResult.value?.assessments || {}) as any[])
const conflictRows = computed(() => Array.isArray(assessmentResult.value?.conflicts) ? assessmentResult.value.conflicts : [])
const metaSummaryRecord = computed(() => assessmentResult.value?.meta_agent || {})
const metaSummary = computed(() => String(metaSummaryRecord.value?.summary || assessmentRecord.value?.summary || '暂无总控智能体裁决摘要'))
const metaActions = computed(() => Array.isArray(metaSummaryRecord.value?.final_actions) ? metaSummaryRecord.value.final_actions : [])
const metaActionCount = computed(() => metaActions.value.length)
const priorityRows = computed(() => Array.isArray(metaSummaryRecord.value?.top_priorities) ? metaSummaryRecord.value.top_priorities : [])
const activeSpecialist = computed(() => specialistRows.value.find((item: any) => item.agent === activeAgent.value) || specialistRows.value[0] || null)
const syncableAiActions = computed(() => {
  const rows = [
    ...metaActions.value,
    ...priorityRows.value.map((item: any) => item?.action || item?.recommendation || item?.summary || item?.title || ''),
    ...specialistRows.value.flatMap((item: any) => Array.isArray(item?.recommendations) ? item.recommendations : []),
  ]
  const actions = rows.map((item: any) => {
    if (typeof item === 'string') return item.trim()
    return String(item?.action || item?.recommendation || item?.summary || item?.title || '').trim()
  }).filter(Boolean)
  return Array.from(new Set<string>(actions)).slice(0, 8)
})
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
const mdtDomainToOrgan: Record<string, BodyMapOrganKey | ''> = {
  hemodynamic: 'circulatory',
  respiratory: 'respiratory',
  infection: 'circulatory',
  renal: 'renal',
  neuro: 'neurologic',
  nutrition: 'hepatic',
  pharmacy: 'coagulation',
}
const mdtOrganRows = computed(() => systemCards.value.map((item: any) => {
  const severity = priorityToBodySeverity(item.priority)
  return {
    ...item,
    organKey: mdtDomainToOrgan[item.domain] || '',
    severity,
    text: bodyMapSeverityText(severity),
  }
}).sort((a: any, b: any) => bodySeverityRank(b.severity) - bodySeverityRank(a.severity)))
const mdtOrganStates = computed(() => {
  const states: Record<string, BodyMapSeverity> = {
    neurologic: 'normal',
    respiratory: 'normal',
    circulatory: 'normal',
    hepatic: 'normal',
    coagulation: 'normal',
    renal: 'normal',
  }
  for (const row of mdtOrganRows.value) {
    if (!row.organKey) continue
    if (bodySeverityRank(row.severity) > bodySeverityRank(states[row.organKey])) states[row.organKey] = row.severity
  }
  return states
})
const mdtOrganTooltips = computed(() => Object.fromEntries(Object.entries(mdtOrganStates.value).map(([key, severity]) => {
  const row = mdtOrganRows.value.find((item: any) => item.organKey === key)
  return [key, {
    label: BODY_MAP_ORGAN_LABELS[key as BodyMapOrganKey] || key,
    statusText: bodyMapSeverityText(severity),
    detail: row?.summary ? shortMdtText(row.summary, 34) : '暂无突出专科意见',
    severity,
  }]
})))
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
  return `智能${activeSystemLabel.value}顾问`
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
  status: 'pending_confirmation',
  note: '',
  requires_confirmation: true,
  confirmation_status: 'pending',
}])
const pendingConfirmationCount = computed(() => decisionRows.value.filter((item: any) => needsDoctorConfirmation(item)).length)
const pendingDecisionCount = computed(() => decisionRows.value.filter((item: any) => ['doctor_confirmed', 'pending'].includes(String(item.status || '').toLowerCase())).length)
const inProgressDecisionCount = computed(() => decisionRows.value.filter((item: any) => String(item.status || '') === 'in_progress').length)
const completedDecisionCount = computed(() => decisionRows.value.filter((item: any) => String(item.status || '') === 'completed').length)
const dismissedDecisionCount = computed(() => decisionRows.value.filter((item: any) => ['dismissed', 'rejected'].includes(String(item.status || '').toLowerCase())).length)
const decisionOwnerOptions = computed(() => Array.from(new Set(decisionRows.value.map((item: any) => String(item.owner || '').trim()).filter(Boolean))))
const decisionBuckets = computed(() => {
  const owner = decisionOwnerFilter.value.trim()
  const sourceRows = decisionOpenOnly.value
    ? decisionRows.value.filter((item: any) => !['completed', 'dismissed', 'rejected'].includes(String(item.status || 'pending_confirmation').toLowerCase()))
    : decisionRows.value
  const rows = owner ? sourceRows.filter((item: any) => String(item.owner || '').trim() === owner) : sourceRows
  return [
    { key: 'pending_confirmation', label: '待医生确认', items: rows.filter((item: any) => needsDoctorConfirmation(item)) },
    { key: 'doctor_confirmed', label: '确认后待执行', items: rows.filter((item: any) => ['doctor_confirmed', 'pending'].includes(String(item.status || '').toLowerCase())) },
    { key: 'in_progress', label: '进行中', items: rows.filter((item: any) => String(item.status || '') === 'in_progress') },
    { key: 'completed', label: '已完成', items: rows.filter((item: any) => String(item.status || '') === 'completed') },
    { key: 'dismissed', label: '已取消/不采纳', items: rows.filter((item: any) => ['dismissed', 'rejected'].includes(String(item.status || '').toLowerCase())) },
    { key: 'needs_revision', label: '需修改', items: rows.filter((item: any) => String(item.status || '') === 'needs_revision') },
  ].filter((bucket) => bucket.items.length > 0 || !decisionOpenOnly.value)
})
const guidedDecisionRows = computed(() => {
  const rows = decisionOpenOnly.value
    ? decisionRows.value.filter((item: any) => !['completed', 'dismissed', 'rejected'].includes(String(item.status || 'pending_confirmation').toLowerCase()))
    : decisionRows.value
  return rows.slice(0, 6)
})
const moderatorDecisionRows = computed(() => decisionRows.value.slice(0, 3))
const latestGeneratedDocuments = computed(() =>
  workspaceDocuments.value.reduce((acc: Record<string, any>, item: any) => {
    const key = String(item?.doc_type || '')
    if (key && !acc[key]) acc[key] = item
    return acc
  }, {})
)
const topConflictSummary = computed(() => conflictRows.value.length ? (conflictRows.value[0]?.summary || '存在跨专科冲突') : '当前无明显冲突')
const nextActionText = computed(() => metaActions.value[0] || todoRows.value[0]?.action || '等待总控智能体生成行动建议')
const closurePercent = computed(() => {
  const total = decisionRows.value.length
  if (!total) return 0
  return Math.round((completedDecisionCount.value / total) * 100)
})
const cockpitMetricRows = computed(() => [
  { label: '患者', value: patientHeadline.value },
  { label: '阶段', value: currentPhaseLabel.value },
  { label: '参与成员', value: sessionParticipants.value.length ? sessionParticipants.value.slice(0, 4).join('、') : '未设置' },
  { label: '标签', value: sessionTags.value.length ? sessionTags.value.slice(0, 4).join('、') : '未设置' },
])
const documentStatusRows = computed(() => [
  {
    key: 'mdt_summary',
    label: '讨论材料',
    status: latestGeneratedDocuments.value.mdt_summary ? '已生成' : '待生成',
    detail: latestGeneratedDocuments.value.mdt_summary ? '可继续刷新材料' : '建议会前先生成',
  },
  {
    key: 'consultation_request',
    label: '会诊记录',
    status: consultRecord.value ? '已填写' : '待填写',
    detail: consultRecord.value ? `${consultRecord.value.length} 字` : '可由 AI 生成',
  },
  {
    key: 'daily_progress',
    label: '病程记录',
    status: progressRecord.value ? '已填写' : '待填写',
    detail: progressRecord.value ? `${progressRecord.value.length} 字` : '可由 AI 生成',
  },
])
const selectedPatientLabel = computed(() => {
  if (patient.value) {
    const bed = patient.value?.hisBed || patient.value?.bed || '--'
    return `${bed}床 · ${patientHeadline.value}`
  }
  return selectedPatientId.value ? '患者已选择' : '未选择患者'
})
const selectedPatientOutOfDeptHint = computed(() => {
  const selected = patients.value.find((item: any) => String(item?._id || '') === String(selectedPatientId.value || ''))
  if (!selected?.__mdtFallbackCurrent) return ''
  return '当前患者为已带入会诊对象，不在当前科室在线患者列表中。'
})
const currentSessionLabel = computed(() => {
  const hit = workspaceSessions.value.find((item: any) => String(item.session_id || '') === String(currentSessionId.value || ''))
  return hit?.title || '当前会话'
})
const currentPhaseLabel = computed(() => phaseLabel(workspaceRecord.value?.phase || 'finalizing'))
const isSessionClosed = computed(() => String(workspaceRecord.value?.phase || '') === 'closed')
const workspaceDirty = computed(() => {
  const snapshot = JSON.stringify({
    session_id: currentSessionId.value || '',
    phase: workspaceRecord.value?.phase || 'finalizing',
    decisions: decisions.value,
    consult_record: consultRecord.value,
    progress_record: progressRecord.value,
    final_summary: finalSummary.value,
    participants: sessionParticipants.value,
    tags: sessionTags.value,
    order_drafts: generatedOrderDrafts.value,
    template_name: selectedTemplateKey.value,
    activity_log: activityLog.value,
  })
  return Boolean(lastSavedSnapshot.value) && snapshot !== lastSavedSnapshot.value
})
const visibleWorkspaceSessions = computed(() =>
  workspaceSessions.value
    .filter((item: any) => {
      if (sessionListOpenOnly.value && String(item.phase || '') === 'closed') return false
      if (sessionPhaseFilter.value && String(item.phase || '') !== sessionPhaseFilter.value) return false
      const q = sessionSearch.value.trim().toLowerCase()
      if (!q) return true
      const hay = `${item.title || ''} ${item.summary || ''}`.toLowerCase()
      return hay.includes(q)
    })
    .sort((a: any, b: any) => {
      const aClosed = String(a?.phase || '') === 'closed' ? 1 : 0
      const bClosed = String(b?.phase || '') === 'closed' ? 1 : 0
      if (aClosed !== bClosed) return aClosed - bClosed
      const aTime = new Date(a?.updated_at || 0).getTime()
      const bTime = new Date(b?.updated_at || 0).getTime()
      return bTime - aTime
    })
)
const signalSourceRows = computed(() => {
  const rows: Array<{ label: string; value: string }> = []
  const evidenceCount = Array.isArray(activeSpecialist.value?.evidence) ? activeSpecialist.value.evidence.length : 0
  if (evidenceCount) rows.push({ label: '专科证据', value: `${evidenceCount} 条` })
  if (filteredAlerts.value.length) rows.push({ label: '相关告警链', value: `${filteredAlerts.value.length} 条` })
  if (filteredDrugs.value.length) rows.push({ label: '相关用药', value: `${filteredDrugs.value.length} 条` })
  if (trendMetricCards.value.length) rows.push({ label: '趋势指标', value: `${trendMetricCards.value.length} 项` })
  return rows.slice(0, 4)
})
const ownerSummaryRows = computed(() => {
  const map = new Map<string, { owner: string; pending: number; inProgress: number; completed: number }>()
  decisionRows.value.forEach((item: any) => {
    const owner = String(item.owner || '未指定负责人').trim() || '未指定负责人'
    if (!map.has(owner)) {
      map.set(owner, { owner, pending: 0, inProgress: 0, completed: 0 })
    }
    const row = map.get(owner)!
    const status = String(item.status || 'pending')
    if (status === 'completed') row.completed += 1
    else if (status === 'in_progress') row.inProgress += 1
    else row.pending += 1
  })
  return Array.from(map.values()).sort((a, b) => (b.pending + b.inProgress) - (a.pending + a.inProgress))
})
const sessionParticipants = computed(() => participantsText.value.split(/[\n,，;；]+/g).map((item) => item.trim()).filter(Boolean))
const sessionTags = computed(() => tagsText.value.split(/[\n,，;；]+/g).map((item) => item.trim()).filter(Boolean))
const currentTemplate = computed(() => sessionTemplates.find((item) => item.key === selectedTemplateKey.value) || null)
const autoSessionSummary = computed(() => {
  const parts: string[] = []
  if (metaSummary.value) parts.push(`总控结论：${metaSummary.value}`)
  if (conflictRows.value.length) parts.push(`冲突焦点：${conflictRows.value.map((item: any) => item.summary || '跨专科冲突').slice(0, 2).join('；')}`)
  if (metaActions.value.length) parts.push(`关键动作：${metaActions.value.slice(0, 3).join('；')}`)
  if (pendingConfirmationCount.value || pendingDecisionCount.value || inProgressDecisionCount.value || completedDecisionCount.value) {
    parts.push(`执行概况：待医生确认${pendingConfirmationCount.value}，确认后待执行${pendingDecisionCount.value}，进行中${inProgressDecisionCount.value}，已完成${completedDecisionCount.value}`)
  }
  return parts.join('\n')
})
const activityTimelineRows = computed(() =>
  activityLog.value
    .slice()
    .sort((a: any, b: any) => new Date(b?.created_at || 0).getTime() - new Date(a?.created_at || 0).getTime())
    .slice(0, 12)
    .map((item: any, idx: number) => ({
      id: `${item?.created_at || idx}-${idx}`,
      title: String(item?.title || '会诊动作'),
      detail: String(item?.detail || '无附加描述'),
      timeLabel: formatBeijingTime(item?.created_at),
    }))
)
const todoRows = computed(() =>
  decisionRows.value
    .filter((item: any) => ['pending', 'in_progress'].includes(String(item.status || 'pending')))
    .slice(0, 5)
)
const currentWorkflowStep = computed(() => {
  if (!selectedPatientId.value) return 'patient'
  if (isGeneratingAssessment.value || (!conflictRows.value.length && !metaActions.value.length && !decisions.value.length)) return 'review'
  if (pendingConfirmationCount.value || pendingDecisionCount.value || inProgressDecisionCount.value) return 'decision'
  return 'archive'
})
const workflowSteps = computed(() => [
  {
    key: 'patient',
    index: '01',
    title: '选择患者',
    desc: selectedPatientId.value ? selectedPatientLabel.value : '先选床号或从患者详情带入',
    done: Boolean(selectedPatientId.value),
  },
  {
    key: 'review',
    index: '02',
    title: '看结论与冲突',
    desc: conflictRows.value.length ? `${conflictRows.value.length} 个冲突需裁决` : '确认总控结论和专科意见',
    done: Boolean(selectedPatientId.value && !isGeneratingAssessment.value && (conflictRows.value.length || metaActions.value.length || decisions.value.length)),
  },
  {
    key: 'decision',
    index: '03',
    title: '形成决议',
    desc: decisionRows.value.length ? `${decisionRows.value.length} 条建议，${pendingConfirmationCount.value} 条需医生确认` : '同步 AI 动作或新增决议',
    done: Boolean(decisionRows.value.length && completedDecisionCount.value === decisionRows.value.length),
  },
  {
    key: 'archive',
    index: '04',
    title: '生成文书',
    desc: consultRecord.value || progressRecord.value ? '文书已形成，可保存归档' : '生成会诊记录和病程记录',
    done: Boolean(consultRecord.value || progressRecord.value || isSessionClosed.value),
  },
])
const primaryGuidanceTitle = computed(() => {
  if (!selectedPatientId.value) return '先选患者，页面会自动收敛到这次 MDT'
  if (isGeneratingAssessment.value) return '正在生成会诊，先等总控智能体汇总'
  if (conflictRows.value.length) return '先裁决冲突，再下执行动作'
  if (pendingConfirmationCount.value) return '先由医生确认 AI 决议草案'
  if (pendingDecisionCount.value || inProgressDecisionCount.value) return '现在重点是把已确认决议闭环'
  return '会诊基本闭环，可以生成文书归档'
})
const primaryGuidanceText = computed(() => {
  if (!selectedPatientId.value) return '左侧选择患者后，系统会自动拉取专科意见、冲突焦点和历史会话，避免医生先面对一整屏空信息。'
  if (isGeneratingAssessment.value) return '请稍候，生成完成后优先看“总控结论”和“冲突焦点”，不用在所有模块里来回找。'
  if (conflictRows.value.length) return `当前有 ${conflictRows.value.length} 个跨专科冲突，建议先确认主持人裁决，再同步为执行决议。`
  if (pendingConfirmationCount.value) return `还有 ${pendingConfirmationCount.value} 条 AI 建议草案未由医生确认，确认前不能作为医嘱或执行任务。`
  if (pendingDecisionCount.value || inProgressDecisionCount.value) return `还有 ${pendingDecisionCount.value + inProgressDecisionCount.value} 条已确认决议未闭环，优先明确负责人、时限和监测指标。`
  return '决议已基本完成，建议生成会诊记录和病程记录，并保存或关闭当前会话。'
})
const closureTone = computed(() => {
  if (pendingConfirmationCount.value > 0 || pendingDecisionCount.value > 0) return 'warning'
  if (completedDecisionCount.value > 0 && completedDecisionCount.value === decisionRows.value.length) return 'soft'
  return 'soft'
})
const closureLabel = computed(() => {
  const total = decisionRows.value.length
  if (!total) return '未生成决议'
  if (pendingConfirmationCount.value) return `待确认 ${pendingConfirmationCount.value}/${total}`
  if (completedDecisionCount.value === total) return `已闭环 ${completedDecisionCount.value}/${total}`
  return `进行中 ${completedDecisionCount.value}/${total}`
})
const mdtSeverityTone = computed(() => {
  if (conflictRows.value.length >= 2) return 'critical'
  if (priorityRows.value.some((item: any) => String(item.priority || '').toLowerCase() === 'critical')) return 'critical'
  if (conflictRows.value.length || priorityRows.value.some((item: any) => String(item.priority || '').toLowerCase() === 'high')) return 'warning'
  return 'soft'
})
const mdtSeverityLabel = computed(() => {
  const tone = mdtSeverityTone.value
  return ({ critical: '高风险', warning: '需关注', soft: '相对平稳' } as Record<string, string>)[tone] || '相对平稳'
})
const patientHeadline = computed(() => patient.value?.name || patient.value?.hisName || '未选择患者')
const patientSubline = computed(() => {
  if (selectedPatientId.value && loading.value && !patient.value) return '患者信息加载中，请稍候'
  if (!patient.value) return '可从患者详情页带入，或在本页直接选择患者'
  const bed = patient.value?.hisBed || patient.value?.bed || '--'
  const diagnosis = patient.value?.clinicalDiagnosis || patient.value?.admissionDiagnosis || '暂无诊断'
  return `${bed}床 · ${diagnosis}`
})
const conflictExplainRows = computed(() =>
  conflictRows.value.map((item: any, idx: number) => ({
    id: `${item.type || 'conflict'}-${idx}`,
    title: item.summary || '存在跨专科冲突',
    agents: (item.agents || []).map(domainLabel).join(' / ') || '多专科',
    focus: item.resolution_focus || '需结合动态病情与总控裁决继续评审。',
  }))
)

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

function bodySeverityRank(value: any) {
  return ({ normal: 0, warning: 1, high: 2, critical: 3 } as Record<string, number>)[String(value || 'normal')] || 0
}

function priorityToBodySeverity(priority: any): BodyMapSeverity {
  const key = String(priority || 'medium').toLowerCase()
  if (key === 'critical') return 'critical'
  if (key === 'high') return 'high'
  if (key === 'low') return 'normal'
  return 'warning'
}

function shortMdtText(value: any, max = 52) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}...` : text || '暂无'
}

function handleMdtOrganClick(organKey: string) {
  const row = mdtOrganRows.value.find((item: any) => item.organKey === organKey)
  if (row?.agent) selectSpecialist(row.agent)
}

function priorityLabel(priority: any) {
  const key = String(priority || 'medium').toLowerCase()
  return ({ critical: '危急', high: '高优先', medium: '中优先', low: '低优先' } as Record<string, string>)[key] || '中优先'
}

function phaseLabel(phase: any) {
  const key = String(phase || 'finalizing').toLowerCase()
  return ({ collecting: '收集中', conflict_review: '冲突评审', finalizing: '裁决定稿', closed: '已关闭' } as Record<string, string>)[key] || '裁决定稿'
}

function sessionDecisionCount(session: any) {
  return Array.isArray(session?.decisions) ? session.decisions.length : 0
}

function sessionCompletedCount(session: any) {
  return Array.isArray(session?.decisions) ? session.decisions.filter((item: any) => String(item?.status || '') === 'completed').length : 0
}

function sessionCompletionRate(session: any) {
  const total = sessionDecisionCount(session)
  if (!total) return 0
  return Math.round((sessionCompletedCount(session) / total) * 100)
}

function decisionStatusLabel(status: any) {
  return ({
    pending_confirmation: '待医生确认',
    doctor_confirmed: '医生已确认',
    pending: '确认后待执行',
    in_progress: '进行中',
    completed: '已完成',
    rejected: '医生不采纳',
    needs_revision: '需修改',
    dismissed: '已取消',
    draft: '草稿',
  } as Record<string, string>)[String(status || 'pending_confirmation').toLowerCase()] || '待医生确认'
}

function normalizeDecision(item: any, idx = 0) {
  const row = { ...(item || {}) }
  let status = String(row.status || '').trim().toLowerCase()
  if (['pending', 'in_progress', 'completed'].includes(status) && !row.confirmed_at) status = 'pending_confirmation'
  if (!status) status = 'pending_confirmation'
  return {
    ...row,
    id: row.id || `decision-${Date.now()}-${idx}`,
    status,
    owner: String(row.owner || '').trim() || '值班医生',
    deadline: String(row.deadline || '').trim() || (idx === 0 ? '立即' : '6h'),
    monitoring: String(row.monitoring || '').trim() || '按系统指标复评',
    review_time: String(row.review_time || '').trim() || '6h',
    requires_confirmation: row.requires_confirmation === false ? false : true,
    confirmation_status: row.confirmation_status || (row.confirmed_at ? 'confirmed' : 'pending'),
    safety_notice: row.safety_notice || 'AI 生成内容仅为待审核建议草案，不能作为医嘱直接执行；必须由执业医生结合床旁情况确认。',
  }
}

function normalizeDecisionList(rows: any[]) {
  return (Array.isArray(rows) ? rows : []).map((item, idx) => normalizeDecision(item, idx)).filter((item) => String(item.action || '').trim())
}

function needsDoctorConfirmation(item: any) {
  const status = String(item?.status || 'pending_confirmation').toLowerCase()
  return item?.requires_confirmation !== false || ['pending_confirmation', 'needs_revision'].includes(status)
}

function templateLabel(key: any) {
  return sessionTemplates.find((item) => item.key === String(key || ''))?.label || String(key || '未使用模板')
}

function appendActivityLog(title: string, detail: string) {
  activityLog.value = [
    {
      title,
      detail,
      created_at: new Date().toISOString(),
    },
    ...activityLog.value,
  ].slice(0, 80)
}

function buildTemplateDecisions(template: typeof sessionTemplates[number]) {
  return template.decisions.map((item, idx) => ({
    id: `decision-${Date.now()}-${idx}`,
    action: item.action,
    owner: item.owner,
    deadline: item.deadline,
    monitoring: item.monitoring,
    review_time: item.review_time,
    status: 'pending_confirmation',
    note: '',
    requires_confirmation: true,
    confirmation_status: 'pending',
  }))
}

function selectSpecialist(agent: string) {
  activeAgent.value = agent
}

async function loadPatientOptions() {
  const deptCode = String(route.query.deptCode || route.query.dept_code || '')
  const res = await getPatients(deptCode ? { dept_code: deptCode, patient_scope: 'in_dept' } : { patient_scope: 'in_dept' })
  const list = Array.isArray(res.data?.patients) ? res.data.patients : []
  const currentId = String(selectedPatientId.value || route.query.patient_id || route.query.patientId || '').trim()
  if (currentId && !list.some((item: any) => String(item?._id || '') === currentId)) {
    try {
      const detailRes = await getPatientDetail(currentId)
      const currentPatient = detailRes.data?.patient
      if (currentPatient?._id) {
        list.unshift({ ...currentPatient, __mdtFallbackCurrent: true })
      }
    } catch {
      // Ignore fallback failures so the in-dept list can still render normally.
    }
  }
  patients.value = list
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
  workspaceSessions.value = Array.isArray(workspaceRes.data?.sessions) ? workspaceRes.data.sessions : []
  currentSessionId.value = String(workspaceRecord.value?.session_id || workspaceSessions.value[0]?.session_id || '')
  activityLog.value = Array.isArray(workspaceRecord.value?.activity_log) ? workspaceRecord.value.activity_log : []
  selectedTemplateKey.value = String(workspaceRecord.value?.template_name || '')
  systemPanels.value = systemPanelsRes.data?.panels || {}
  decisions.value = Array.isArray(workspaceRecord.value?.decisions) && workspaceRecord.value.decisions.length
    ? normalizeDecisionList(workspaceRecord.value.decisions)
    : metaActions.value.slice(0, 4).map((item: string, idx: number) => ({
        id: `decision-${idx + 1}`,
        action: item,
        owner: '值班医生',
        deadline: idx === 0 ? '立即' : '6h',
        monitoring: '按系统指标复评',
        review_time: '6h',
        status: 'pending_confirmation',
        note: '',
        requires_confirmation: true,
        confirmation_status: 'pending',
      }))
  consultRecord.value = String(workspaceRecord.value?.consult_record || '')
  progressRecord.value = String(workspaceRecord.value?.progress_record || '')
  finalSummary.value = String(workspaceRecord.value?.final_summary || '')
  participantsText.value = Array.isArray(workspaceRecord.value?.participants) ? workspaceRecord.value.participants.join('、') : ''
  tagsText.value = Array.isArray(workspaceRecord.value?.tags) ? workspaceRecord.value.tags.join('、') : ''
  lastSavedSnapshot.value = JSON.stringify({
    session_id: currentSessionId.value || '',
    phase: workspaceRecord.value?.phase || 'finalizing',
    decisions: decisions.value,
    consult_record: consultRecord.value,
    progress_record: progressRecord.value,
    final_summary: finalSummary.value,
    participants: sessionParticipants.value,
    tags: sessionTags.value,
    order_drafts: generatedOrderDrafts.value,
    template_name: selectedTemplateKey.value,
    activity_log: activityLog.value,
  })
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
      decisions.value = metaActions.value.slice(0, 4).map((item: string, idx: number) => normalizeDecision({
        id: `decision-${idx + 1}`,
        action: item,
        owner: '值班医生',
        deadline: idx === 0 ? '立即' : '6h',
        monitoring: '按系统指标复评',
        review_time: '6h',
        status: 'pending_confirmation',
        note: '',
      }, idx))
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
      session_id: currentSessionId.value || undefined,
      phase: workspaceRecord.value?.phase || 'finalizing',
      decisions: decisions.value,
      consult_record: consultRecord.value,
      progress_record: progressRecord.value,
      final_summary: finalSummary.value,
      participants: sessionParticipants.value,
      tags: sessionTags.value,
      order_drafts: generatedOrderDrafts.value,
      template_name: selectedTemplateKey.value || undefined,
      activity_log: activityLog.value,
    })
    workspaceRecord.value = res.data?.workspace || null
    currentSessionId.value = String(workspaceRecord.value?.session_id || currentSessionId.value || '')
    const sessionsRes = await listAiMdtWorkspaceSessions(selectedPatientId.value)
    workspaceSessions.value = Array.isArray(sessionsRes.data?.sessions) ? sessionsRes.data.sessions : workspaceSessions.value
    lastSavedSnapshot.value = JSON.stringify({
      session_id: currentSessionId.value || '',
      phase: workspaceRecord.value?.phase || 'finalizing',
      decisions: decisions.value,
      consult_record: consultRecord.value,
      progress_record: progressRecord.value,
      final_summary: finalSummary.value,
      participants: sessionParticipants.value,
      tags: sessionTags.value,
      order_drafts: generatedOrderDrafts.value,
      template_name: selectedTemplateKey.value,
      activity_log: activityLog.value,
    })
    appendActivityLog('保存会话', `已保存 ${decisions.value.length} 条决议，当前阶段：${phaseLabel(workspaceRecord.value?.phase || 'finalizing')}`)
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
      appendActivityLog('生成文书', `${({ mdt_summary: '讨论材料', daily_progress: '病程记录', consultation_request: '会诊记录' } as Record<string, string>)[docType] || docType} 已更新`)
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
      status: 'pending_confirmation',
      note: '',
      requires_confirmation: true,
      confirmation_status: 'pending',
    },
  ]
  appendActivityLog('新增决议', '已新增 1 条待医生确认的建议草案')
}

function removeDecision(id: string) {
  const hit = decisions.value.find((item: any) => item.id === id)
  decisions.value = decisions.value.filter((item: any) => item.id !== id)
  appendActivityLog('删除决议', hit?.action || '已删除 1 条决议')
}

function markDecisionStatus(id: string, status: 'pending_confirmation' | 'doctor_confirmed' | 'pending' | 'in_progress' | 'completed' | 'dismissed' | 'rejected' | 'needs_revision') {
  let action = ''
  decisions.value = decisions.value.map((item: any) => {
    if (item.id === id) {
      action = item.action || ''
      if (['in_progress', 'completed'].includes(status) && needsDoctorConfirmation(item)) {
        message.warning('该 AI 建议尚未由医生确认，不能直接进入执行状态')
        return item
      }
      return { ...item, status }
    }
    return item
  })
  appendActivityLog('更新决议状态', `${action || '决议'} -> ${decisionStatusLabel(status)}`)
}

function markDecisionDone(row: any) {
  if (isSessionClosed.value) {
    message.warning('当前 MDT 会话已归档，不能修改决议')
    return
  }
  const id = row?.id
  if (!id) return
  if (!decisions.value.length) fillDecisionDefaults()
  if (needsDoctorConfirmation(row)) {
    message.warning('请先完成医生确认，确认后才能标记完成')
    return
  }
  markDecisionStatus(id, 'completed')
  message.success('决议已闭环')
}

async function confirmDecision(row: any, action: 'confirm' | 'reject' | 'revise' = 'confirm') {
  if (!selectedPatientId.value || !currentSessionId.value || !row?.id) {
    message.warning('请先保存 MDT 会话，再进行医生确认')
    return
  }
  const actor = getOperatorIdentity() || 'doctor'
  const id = String(row.id)
  confirmingDecisionIds.value = new Set([...confirmingDecisionIds.value, id])
  try {
    const res = await postAiMdtDecisionConfirm(selectedPatientId.value, currentSessionId.value, id, {
      action,
      actor,
      note: row.note || '',
    })
    if (Number(res.data?.code) !== 0) throw new Error(res.data?.message || '确认失败')
    const next = res.data?.decision || {}
    decisions.value = decisions.value.map((item: any) => item.id === id ? normalizeDecision({ ...item, ...next }, 0) : item)
    appendActivityLog(action === 'confirm' ? '医生确认 AI 决议' : '医生反馈 AI 决议', `${row.action || '决议'} -> ${decisionStatusLabel(next.status)}`)
    message.success(action === 'confirm' ? '医生已确认，可进入执行追踪' : '已记录医生反馈')
  } catch (err: any) {
    message.error(err?.message || '确认失败')
  } finally {
    const nextSet = new Set(confirmingDecisionIds.value)
    nextSet.delete(id)
    confirmingDecisionIds.value = nextSet
  }
}

async function markVisibleDecisions(status: 'doctor_confirmed' | 'in_progress' | 'completed') {
  const ids = new Set(
    decisionBuckets.value.flatMap((bucket: any) => (bucket.items || []).map((item: any) => item.id))
  )
  if (status === 'doctor_confirmed') {
    for (const row of decisionRows.value.filter((item: any) => ids.has(item.id) && needsDoctorConfirmation(item))) {
      await confirmDecision(row, 'confirm')
    }
    return
  }
  decisions.value = decisions.value.map((item: any) =>
    ids.has(item.id) && !needsDoctorConfirmation(item) ? { ...item, status } : item
  )
  appendActivityLog('批量推进决议', `已将 ${ids.size} 条可见决议更新为${decisionStatusLabel(status)}`)
}

function syncDecisionsFromMetaActions() {
  if (isSessionClosed.value) {
    message.warning('当前 MDT 会话已归档，只读状态下不能同步 AI 动作')
    return
  }
  if (!syncableAiActions.value.length) {
    message.info('当前 AI 会诊结果还没有可同步动作，可先生成/刷新 MDT 会诊或手动新增决议')
    return
  }
  const existing = new Set(decisions.value.map((item: any) => String(item.action || '').trim()).filter(Boolean))
  const additions = syncableAiActions.value
    .filter((item: string) => !existing.has(String(item || '').trim()))
    .map((item: string, idx: number) => ({
      id: `decision-ai-${Date.now()}-${idx}`,
      action: item,
      owner: '值班医生',
      deadline: idx === 0 ? '立即' : '6h',
      monitoring: '按系统指标复评',
      review_time: '6h',
      status: 'pending_confirmation',
      note: '由总控智能体动作同步，需医生确认后才能执行',
      requires_confirmation: true,
      confirmation_status: 'pending',
    }))
  if (!additions.length) {
    message.info('AI 动作已全部在决议列表中，无需重复同步')
    return
  }
  decisions.value = [...decisions.value, ...additions]
  appendActivityLog('同步 AI 动作', `已追加 ${additions.length} 条 AI 最终动作到决议列表`)
  message.success(`已同步 ${additions.length} 条 AI 动作到决议列表`)
}

function fillDecisionDefaults() {
  if (isSessionClosed.value) return
  decisions.value = decisionRows.value.map((item: any, idx: number) => ({
    ...item,
    id: item.id || `decision-${Date.now()}-${idx}`,
    owner: String(item.owner || '').trim() || '值班医生',
    deadline: String(item.deadline || '').trim() || (idx === 0 ? '立即' : '6h'),
    monitoring: String(item.monitoring || '').trim() || '按系统指标复评',
    review_time: String(item.review_time || '').trim() || '6h',
    status: String(item.status || '').trim() || 'pending_confirmation',
    requires_confirmation: item.requires_confirmation === false ? false : true,
    confirmation_status: item.confirmation_status || (item.confirmed_at ? 'confirmed' : 'pending'),
  }))
  appendActivityLog('补全决议字段', '已补全负责人、时限、监测指标与复评时间')
}

async function copyText(text: string, successText = '已复制') {
  const value = String(text || '').trim()
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    appendActivityLog('复制内容', successText)
  } catch {
    error.value = '复制失败，请检查浏览器剪贴板权限。'
  }
}

async function switchSession(sessionId: string) {
  if (!selectedPatientId.value || !sessionId) return
  if (workspaceDirty.value && !window.confirm('当前 MDT 会话有未保存变更，确认切换会话吗？')) return
  const res = await getAiMdtWorkspaceSession(selectedPatientId.value, sessionId)
  workspaceRecord.value = res.data?.workspace || null
  workspaceDocuments.value = Array.isArray(res.data?.documents) ? res.data.documents : []
  generatedOrderDrafts.value = Array.isArray(res.data?.order_drafts) ? res.data.order_drafts : []
  currentSessionId.value = sessionId
  decisions.value = Array.isArray(workspaceRecord.value?.decisions) ? normalizeDecisionList(workspaceRecord.value.decisions) : []
  consultRecord.value = String(workspaceRecord.value?.consult_record || '')
  progressRecord.value = String(workspaceRecord.value?.progress_record || '')
  finalSummary.value = String(workspaceRecord.value?.final_summary || '')
  participantsText.value = Array.isArray(workspaceRecord.value?.participants) ? workspaceRecord.value.participants.join('、') : ''
  tagsText.value = Array.isArray(workspaceRecord.value?.tags) ? workspaceRecord.value.tags.join('、') : ''
  activityLog.value = Array.isArray(workspaceRecord.value?.activity_log) ? workspaceRecord.value.activity_log : []
  selectedTemplateKey.value = String(workspaceRecord.value?.template_name || '')
  lastSavedSnapshot.value = JSON.stringify({
    session_id: currentSessionId.value || '',
    phase: workspaceRecord.value?.phase || 'finalizing',
    decisions: decisions.value,
    consult_record: consultRecord.value,
    progress_record: progressRecord.value,
    final_summary: finalSummary.value,
    participants: sessionParticipants.value,
    tags: sessionTags.value,
    order_drafts: generatedOrderDrafts.value,
    template_name: selectedTemplateKey.value,
    activity_log: activityLog.value,
  })
}

function startNewSession() {
  if (workspaceDirty.value && !window.confirm('当前 MDT 会话有未保存变更，确认新建会话吗？')) return
  currentSessionId.value = ''
  workspaceRecord.value = { phase: 'collecting' }
  decisions.value = metaActions.value.slice(0, 4).map((item: string, idx: number) => normalizeDecision({
    id: `decision-${idx + 1}`,
    action: item,
    owner: '值班医生',
    deadline: idx === 0 ? '立即' : '6h',
    monitoring: '按系统指标复评',
    review_time: '6h',
    status: 'pending_confirmation',
    note: '',
  }, idx))
  consultRecord.value = ''
  progressRecord.value = ''
  finalSummary.value = ''
  participantsText.value = ''
  tagsText.value = ''
  selectedTemplateKey.value = ''
  activityLog.value = []
  appendActivityLog('新建会话', '已从当前患者新建一轮 MDT 会诊会话')
  lastSavedSnapshot.value = ''
}

function duplicateCurrentSession() {
  if (!currentSessionId.value) return
  currentSessionId.value = ''
  workspaceRecord.value = { ...(workspaceRecord.value || {}), phase: 'collecting' }
  decisions.value = decisions.value.map((item: any, idx: number) => normalizeDecision({ ...item, id: `decision-${Date.now()}-${idx}`, status: 'pending_confirmation', confirmed_at: null, confirmed_by: null, requires_confirmation: true }, idx))
  generatedOrderDrafts.value = generatedOrderDrafts.value.map((item: any, idx: number) => ({ ...item, id: `order-${Date.now()}-${idx}` }))
  finalSummary.value = finalSummary.value || autoSessionSummary.value
  activityLog.value = [
    {
      title: '复制会话',
      detail: `由会话 ${currentSessionLabel.value} 复制生成新会话`,
      created_at: new Date().toISOString(),
    },
    ...activityLog.value,
  ].slice(0, 80)
  lastSavedSnapshot.value = ''
}

function exportCurrentSession() {
  const payload = {
    session_id: currentSessionId.value || null,
    title: currentSessionLabel.value,
    phase: workspaceRecord.value?.phase || 'finalizing',
    patient: {
      id: selectedPatientId.value,
      name: patientHeadline.value,
      summary: patientSubline.value,
    },
    summary: metaSummary.value,
    template_name: selectedTemplateKey.value || null,
    actions: metaActions.value,
    conflicts: conflictRows.value,
    decisions: decisions.value,
    consult_record: consultRecord.value,
    progress_record: progressRecord.value,
    final_summary: finalSummary.value,
    participants: sessionParticipants.value,
    tags: sessionTags.value,
    activity_log: activityLog.value,
    order_drafts: generatedOrderDrafts.value,
    exported_at: new Date().toISOString(),
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `mdt_session_${currentSessionId.value || Date.now()}.json`
  a.click()
  URL.revokeObjectURL(url)
}

function setPhase(phase: 'collecting' | 'conflict_review' | 'finalizing' | 'closed') {
  workspaceRecord.value = { ...(workspaceRecord.value || {}), phase }
  appendActivityLog('切换阶段', `当前会话进入${phaseLabel(phase)}`)
}

async function closeCurrentSession() {
  if (!consultRecord.value.trim()) consultRecord.value = autoSessionSummary.value
  if (!progressRecord.value.trim()) progressRecord.value = autoSessionSummary.value
  setPhase('closed')
  await saveWorkspace()
}

function reopenCurrentSession() {
  if (!isSessionClosed.value) return
  setPhase('collecting')
  appendActivityLog('复开会话', '已将归档会话恢复为收集中，可继续补充决议与文书')
}

function applySessionTemplate() {
  if (!currentTemplate.value || isSessionClosed.value) return
  const template = currentTemplate.value
  decisions.value = buildTemplateDecisions(template)
  tagsText.value = template.tags.join('、')
  participantsText.value = template.participants.join('、')
  if (!consultRecord.value.trim()) {
    consultRecord.value = `【${template.label}】\n目标：${template.summary}\n重点：${template.decisions.map((item) => item.action).join('；')}`
  }
  appendActivityLog('套用模板', `已套用 ${template.label}，生成 ${template.decisions.length} 条模板决议`)
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

watch(selectedPatientId, (value, oldValue) => {
  if (!value) return
  if (workspaceDirty.value && !window.confirm('当前 MDT 会话有未保存变更，确认切换患者吗？')) {
    selectedPatientId.value = String(oldValue || '')
    return
  }
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
  width: 100%;
  max-width: none;
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
  padding: 2px;
}
.mdt-hero :deep(.ant-card-body) {
  display: grid;
  padding: 14px;
}
.mdt-command-center,
.mdt-hero__copy,.mdt-hero__side {
  position: relative;
  z-index: 1;
}
.mdt-command-center {
  display: grid;
  gap: 12px;
}
.mdt-command-top {
  display: grid;
  grid-template-columns: minmax(320px, .82fr) minmax(0, 1.18fr);
  gap: 18px;
  align-items: start;
}
.mdt-command-title {
  display: grid;
  gap: 5px;
  min-width: 0;
}
.mdt-hero__copy {
  display: grid;
  align-content: start;
  gap: 10px;
  padding: 0;
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
  max-width: 760px;
  font-size: 13px;
  line-height: 1.7;
}
.mdt-hero__badges {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
}
.mdt-flow {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.mdt-flow-step {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: center;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(125, 167, 214, 0.14);
  background: rgba(9, 20, 31, 0.72);
}
.mdt-flow-step__index {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 12px;
  background: rgba(15, 42, 61, 0.9);
  color: #a7dff2;
  font-size: 12px;
  font-weight: 800;
}
.mdt-flow-step strong {
  display: block;
  color: #f3f8fb;
  font-size: 13px;
}
.mdt-flow-step small {
  display: block;
  margin-top: 3px;
  color: #91adbd;
  font-size: 11px;
  line-height: 1.45;
}
.mdt-flow-step.is-active {
  border-color: rgba(34, 211, 238, 0.36);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, .12), transparent 40%),
    rgba(9, 25, 38, 0.9);
}
.mdt-flow-step.is-done .mdt-flow-step__index {
  background: rgba(10, 82, 61, 0.92);
  color: #bbf7d0;
}
.mdt-simple-board {
  display: grid;
  grid-template-columns: minmax(380px, .95fr) minmax(420px, 1.05fr);
  gap: 16px;
  align-items: stretch;
}
.mdt-simple-left,
.mdt-simple-right {
  display: grid;
  gap: 12px;
}
.simple-patient-card,
.mdt-body-card,
.simple-card {
  border: 1px solid rgba(125, 211, 252, .15);
  border-radius: 18px;
  background:
    radial-gradient(circle at 100% 0%, rgba(34, 211, 238, .10), transparent 34%),
    rgba(7, 20, 34, .82);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.03);
}
.simple-patient-card {
  display: grid;
  gap: 12px;
  padding: 16px;
}
.simple-patient-card span,
.simple-card span {
  display: block;
  color: #8aa4b8;
  font-size: 12px;
}
.simple-patient-card strong {
  display: block;
  margin-top: 4px;
  color: #f0fbff;
  font-size: 24px;
}
.simple-patient-card small {
  display: block;
  margin-top: 5px;
  color: #9fc4d7;
  line-height: 1.45;
}
.simple-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.simple-actions.slim {
  margin-top: 8px;
}
.mdt-body-card {
  display: grid;
  place-items: center;
  min-height: 470px;
  padding: 12px;
}
.mdt-body-card :deep(.organ-heatmap) {
  width: min(100%, 430px);
}
.mdt-simple-right {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.simple-card {
  display: grid;
  align-content: start;
  gap: 12px;
  min-height: 170px;
  padding: 16px;
}
.simple-card--summary {
  min-height: 132px;
  background:
    radial-gradient(circle at 96% 0%, rgba(94, 234, 212, .14), transparent 34%),
    linear-gradient(135deg, rgba(8, 64, 84, .72), rgba(7, 20, 34, .86));
}
.simple-card--decisions {
  min-height: 132px;
}
.moderator-metrics {
  display: flex;
  align-items: center;
  gap: 10px;
}
.moderator-metrics i {
  flex: 1;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(255,255,255,.08);
}
.moderator-metrics b {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #22c55e, #67e8f9);
}
.moderator-metrics em {
  color: #a7f3d0;
  font-style: normal;
  font-size: 12px;
}
.simple-card--summary strong,
.simple-card-head strong {
  display: block;
  color: #f0fbff;
  font-size: 22px;
}
.simple-card p {
  margin: 0;
  color: #b7d9ea;
  line-height: 1.55;
}
.simple-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.organ-pill-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.organ-pill {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: 12px;
  padding: 9px 10px;
  color: #dffbff;
  background: rgba(2, 8, 20, .26);
  cursor: pointer;
}
.organ-pill.active {
  border-color: rgba(103, 232, 249, .42);
  background: rgba(14, 116, 144, .24);
}
.organ-pill span,
.organ-pill b {
  font-size: 12px;
}
.organ-pill b {
  color: #67e8f9;
}
.organ-pill.is-high b,
.organ-pill.is-critical b {
  color: #fb7185;
}
.organ-pill.is-warning b {
  color: #fbbf24;
}
.simple-list {
  display: grid;
  gap: 8px;
}
.simple-list div,
.simple-empty {
  padding: 10px;
  border-radius: 12px;
  background: rgba(2, 8, 20, .28);
  border: 1px solid rgba(125, 211, 252, .12);
}
.simple-list strong {
  display: block;
  color: #f0fbff;
  line-height: 1.4;
}
.simple-list span,
.simple-empty {
  color: #8aa4b8;
  font-size: 12px;
}
.decision-pill-row {
  display: grid;
  gap: 8px;
}
.decision-pill {
  display: grid;
  gap: 4px;
  padding: 9px 10px;
  border: 1px solid rgba(125, 211, 252, .14);
  border-radius: 12px;
  color: inherit;
  background: rgba(2, 8, 20, .28);
  text-align: left;
  cursor: pointer;
}
.decision-pill:hover {
  border-color: rgba(103,232,249,.42);
}
.decision-pill.status-completed {
  border-color: rgba(52,211,153,.24);
  background: rgba(20,83,45,.18);
}
.decision-pill strong,
.decision-pill span {
  display: block;
}
.decision-pill strong {
  color: #f0fbff;
  font-size: 13px;
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
.hero-badge--focus {
  background: rgba(12, 45, 68, 0.92);
  border-color: rgba(34, 211, 238, 0.28);
  color: #d4fbff;
}
.hero-badge--critical {
  background: rgba(78, 18, 30, 0.86);
  border-color: rgba(251, 113, 133, 0.28);
  color: #ffd4db;
}
.hero-badge--warning {
  background: rgba(82, 48, 12, 0.86);
  border-color: rgba(251, 191, 36, 0.28);
  color: #ffe9a8;
}
.hero-badge--closed {
  background: rgba(58, 18, 18, 0.86);
  border-color: rgba(248, 113, 113, 0.24);
  color: #ffd7d7;
}
.hero-conclusion-row {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.hero-conclusion-card {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(125, 167, 214, 0.18);
  background: rgba(11, 24, 37, 0.88);
}
.hero-conclusion-card--soft {
  background: rgba(9, 20, 31, 0.86);
}
.hero-conclusion-card span {
  color: #89a6b8;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.hero-conclusion-card strong {
  color: #f3f8fb;
  font-size: 13px;
  line-height: 1.6;
}
.hero-conclusion-card--todo {
  grid-column: 1 / -1;
}
.mdt-clinical-strip {
  display: grid;
  grid-template-columns: minmax(280px, .92fr) minmax(360px, 1.2fr) minmax(260px, .9fr) minmax(300px, .98fr);
  gap: 12px;
  align-items: stretch;
}
.clinical-card {
  display: grid;
  align-content: start;
  gap: 10px;
  min-width: 0;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid rgba(125, 167, 214, 0.16);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, .08), transparent 36%),
    rgba(9, 20, 31, 0.88);
}
.clinical-card--patient {
  border-left: 4px solid rgba(96, 165, 250, .86);
}
.clinical-card--summary {
  border-left: 4px solid rgba(34, 211, 238, .86);
}
.clinical-card--metrics {
  border-left: 4px solid rgba(52, 211, 153, .82);
}
.clinical-card--handoff {
  border-left: 4px solid rgba(251, 191, 36, .82);
}
.clinical-card__head {
  display: grid;
  gap: 5px;
}
.clinical-card__head span,
.clinical-metric span {
  color: #89a6b8;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.clinical-card__head strong {
  color: #f3f8fb;
  font-size: 14px;
  line-height: 1.55;
}
.clinical-card--summary .clinical-card__head strong {
  display: -webkit-box;
  min-height: 44px;
  max-height: 68px;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
}
.clinical-actions {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  align-items: center;
}
.clinical-card--patient .clinical-actions {
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(120px, .9fr);
}
.clinical-metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.clinical-metric {
  display: grid;
  gap: 3px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(7, 17, 27, .62);
}
.clinical-metric strong {
  color: #f3f8fb;
  font-size: 14px;
  line-height: 1.2;
}
.next-action-box {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(251, 191, 36, .18);
  background: rgba(82, 48, 12, .26);
  color: #ffe9a8;
  font-size: 12px;
  line-height: 1.6;
}
.mdt-clinical-meta {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(360px, .9fr);
  gap: 12px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(125, 167, 214, 0.14);
  background: rgba(9, 20, 31, 0.68);
}
.mdt-clinical-meta .meta-edit-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: stretch;
}
.mdt-clinical-meta .field-textarea {
  grid-column: 1 / -1;
  min-height: 58px;
}
.todo-list--inline {
  align-content: stretch;
}
.mdt-cockpit {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, .9fr);
  gap: 12px;
}
.cockpit-main,
.cockpit-card,
.hero-editor-card,
.snapshot-item,
.decision-command-strip,
.doc-status-card {
  border-radius: 12px;
  border: 1px solid rgba(125, 167, 214, 0.16);
  background: rgba(9, 20, 31, 0.88);
}
.cockpit-main {
  display: grid;
  gap: 10px;
  padding: 16px;
}
.cockpit-main span,
.cockpit-card span,
.snapshot-item span,
.doc-status-card span {
  color: #89a6b8;
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.cockpit-main strong {
  color: #f3f8fb;
  font-size: 15px;
  line-height: 1.75;
}
.cockpit-actions,
.decision-command-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.cockpit-side {
  display: grid;
  gap: 10px;
}
.cockpit-card {
  display: grid;
  gap: 7px;
  padding: 12px 14px;
}
.cockpit-card--accent {
  border-color: rgba(34, 211, 238, 0.26);
  background: linear-gradient(180deg, rgba(12, 45, 68, 0.78), rgba(9, 20, 31, 0.9));
}
.cockpit-card strong,
.snapshot-item strong,
.doc-status-card strong {
  color: #f3f8fb;
  font-size: 13px;
  line-height: 1.5;
}
.closure-meter {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(125, 167, 214, 0.12);
}
.closure-meter i {
  display: block;
  height: 100%;
  min-width: 4px;
  border-radius: inherit;
  background: linear-gradient(90deg, #22d3ee, #34d399);
}
.session-snapshot {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.snapshot-item {
  display: grid;
  gap: 4px;
  padding: 12px;
}
.hero-editor-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(280px, .85fr);
  gap: 10px;
}
.hero-editor-card {
  display: grid;
  gap: 10px;
  padding: 12px 14px;
}
.owner-mini-list {
  display: grid;
  gap: 8px;
}
.owner-mini-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(7, 17, 27, 0.7);
  color: #9eb8c7;
  font-size: 12px;
}
.owner-mini-row strong {
  color: #f3f8fb;
}
.empty-box--compact {
  padding: 10px 12px;
}
.meta-edit-grid {
  display: grid;
  gap: 8px;
}
.todo-list {
  display: grid;
  gap: 8px;
}
.todo-row {
  display: grid;
  gap: 2px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(9, 20, 31, 0.78);
  border: 1px solid rgba(125, 167, 214, 0.12);
}
.todo-row strong {
  font-size: 12px;
  line-height: 1.5;
}
.todo-row small {
  color: #9eb8c7;
  font-size: 11px;
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
  align-content: start;
  padding: 0;
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
.toolbar-hint {
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(245, 158, 11, 0.2);
  background: rgba(71, 43, 8, 0.3);
  color: #f7d08a;
  font-size: 12px;
  line-height: 1.5;
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
.mdt-select--compact {
  padding: 8px 10px;
  min-height: 34px;
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
  grid-template-columns: minmax(280px, 320px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
  width: 100%;
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
.mdt-content {
  min-width: 0;
  align-items: start;
}
.mdt-content--moderator {
  grid-template-columns: 1fr;
}
.mdt-content--moderator .mdt-panel {
  min-width: 0;
}
.mdt-content--moderator .mdt-panel :deep(.ant-card-body) {
  padding: 16px;
}
.mdt-content--moderator .mdt-grid--timeline .detail-timeline,
.mdt-content--moderator .mdt-grid--timeline .impact-list,
.mdt-content--moderator .mdt-grid--documents .decision-list {
  max-height: 360px;
  overflow: auto;
  padding-right: 3px;
}
.mdt-content--moderator .mdt-grid--assessment .detail-stack {
  grid-template-columns: minmax(0, .95fr) minmax(0, 1.05fr);
}
.mdt-content--moderator .mdt-grid--assessment .detail-stack .summary-box,
.mdt-content--moderator .mdt-grid--assessment .detail-stack .detail-block:last-child {
  grid-column: 1 / -1;
}
.mdt-content--moderator .conflict-list,
.mdt-content--moderator .detail-stack,
.mdt-content--moderator .impact-list,
.mdt-content--moderator .decision-list {
  gap: 8px;
}
.mdt-moderator-board {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(340px, .7fr);
  gap: 14px;
  align-items: start;
}
.mdt-primary-lane,
.mdt-action-rail {
  display: grid;
  gap: 12px;
  min-width: 0;
}
.mdt-action-rail {
  position: sticky;
  top: 16px;
}
.mdt-guide-panel :deep(.ant-card-body) {
  padding: 18px;
}
.guide-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: start;
}
.guide-header h2 {
  margin: 4px 0 6px;
  color: #f3f8fb;
  font-size: clamp(20px, 1.7vw, 28px);
  line-height: 1.2;
  letter-spacing: -0.03em;
}
.guide-header p {
  margin: 0;
  color: #a8c0ce;
  font-size: 13px;
  line-height: 1.75;
}
.guide-score {
  display: grid;
  gap: 4px;
  justify-items: center;
  min-width: 96px;
  padding: 12px;
  border-radius: 16px;
  border: 1px solid rgba(52, 211, 153, 0.18);
  background: rgba(9, 57, 43, 0.44);
}
.guide-score span {
  color: #9fd8c2;
  font-size: 11px;
}
.guide-score strong {
  color: #d8fff0;
  font-size: 28px;
  line-height: 1;
}
.guide-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.clinical-summary-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, .38fr);
  gap: 12px;
}
.clinical-facts {
  display: grid;
  gap: 8px;
}
.clinical-fact {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(125, 167, 214, 0.14);
  background: rgba(9, 20, 31, 0.74);
}
.clinical-fact span {
  color: #89a6b8;
  font-size: 11px;
  letter-spacing: 0.08em;
}
.clinical-fact strong {
  color: #f3f8fb;
  font-size: 16px;
}
.mdt-review-grid {
  display: grid;
  grid-template-columns: minmax(0, .92fr) minmax(0, 1.08fr);
  gap: 12px;
}
.next-action-box--large {
  font-size: 14px;
  line-height: 1.75;
}
.decision-list--guided {
  max-height: 560px;
  overflow: auto;
  padding-right: 4px;
}
.doc-status-board--rail {
  grid-template-columns: 1fr;
}
.session-compact-list {
  display: grid;
  gap: 8px;
}
.session-compact-item {
  display: grid;
  gap: 4px;
  width: 100%;
  padding: 10px 12px;
  text-align: left;
  border-radius: 12px;
  border: 1px solid rgba(125, 167, 214, 0.12);
  background: rgba(9, 20, 31, 0.78);
  cursor: pointer;
}
.session-compact-item strong {
  color: #f3f8fb;
  font-size: 12px;
}
.session-compact-item span {
  color: #93adbc;
  font-size: 11px;
}
.session-compact-item.is-active {
  border-color: rgba(34, 211, 238, 0.32);
  box-shadow: inset 3px 0 0 rgba(34, 211, 238, .82);
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
.session-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.session-chip {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(14, 34, 50, 0.9);
  border: 1px solid rgba(125, 167, 214, 0.12);
  color: #9eb8c7;
  font-size: 10px;
}
.session-chip--closed {
  color: #ffd7d7;
  border-color: rgba(248, 113, 113, 0.2);
  background: rgba(69, 18, 18, 0.86);
}
.session-chip--tag {
  color: #c9f7ff;
  border-color: rgba(103, 232, 249, 0.18);
  background: rgba(10, 45, 60, 0.88);
}
.session-chip--done {
  color: #d7fff0;
  border-color: rgba(52, 211, 153, 0.2);
  background: rgba(10, 62, 43, 0.88);
}
.session-chip--running {
  color: #ffe9a8;
  border-color: rgba(251, 191, 36, 0.2);
  background: rgba(78, 48, 11, 0.88);
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
.muted-line {
  color: #9eb8c7;
}
.specialist-row__meta {
  display: grid;
  justify-items: end;
  gap: 6px;
  color: #9eb8c7;
  font-size: 11px;
  white-space: nowrap;
}
.row-active-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(12, 45, 68, 0.92);
  border: 1px solid rgba(34, 211, 238, 0.24);
  color: #d4fbff;
  font-size: 10px;
}
.focus-specialist-card {
  display: grid;
  gap: 8px;
  margin-top: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(96, 165, 250, 0.28);
  background: linear-gradient(180deg, rgba(14, 27, 41, 0.96), rgba(9, 19, 30, 0.94));
}
.focus-specialist-card__head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}
.focus-specialist-card__head strong {
  color: #f3f8fb;
  font-size: 13px;
}
.focus-specialist-card__head span {
  color: #9eb8c7;
  font-size: 11px;
}
.focus-specialist-card__summary {
  color: #d7e7f0;
  font-size: 12px;
  line-height: 1.7;
}
.mdt-content-grid {
  grid-template-columns: minmax(0, .95fr) minmax(0, 1.05fr);
}
.mdt-content-grid--single {
  grid-template-columns: minmax(0, .98fr) minmax(340px, .72fr);
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
.decision-buckets {
  display: grid;
  gap: 12px;
}
.mdt-content--moderator .decision-buckets {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: start;
}
.mdt-content--moderator .decision-bucket {
  min-width: 0;
}
.mdt-content--moderator .decision-list {
  max-height: 520px;
  overflow: auto;
  padding-right: 3px;
}
.decision-command-strip {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  padding: 14px;
  margin-bottom: 12px;
}
.decision-command-strip > div:first-child {
  display: grid;
  gap: 4px;
}
.decision-command-strip strong {
  color: #f3f8fb;
  font-size: 16px;
}
.decision-command-strip span {
  color: #9eb8c7;
  font-size: 12px;
}
.decision-bucket {
  display: grid;
  gap: 10px;
}
.decision-bucket__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #dfeef6;
  font-size: 12px;
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
.decision-safety {
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid rgba(245, 158, 11, 0.22);
  background: rgba(82, 48, 12, 0.26);
  color: #ffe9a8;
  font-size: 12px;
  line-height: 1.55;
}
.decision-form,
.decision-form__grid,
.doc-stack,
.doc-block,
.workspace-actions {
  display: grid;
  gap: 10px;
}
.workspace-actions--top {
  grid-template-columns: repeat(4, minmax(0, auto));
  justify-content: start;
  margin-bottom: 10px;
}
.workspace-actions--sidebar {
  grid-template-columns: 1fr;
}
.inline-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(125, 167, 214, 0.14);
  background: rgba(10, 22, 35, 0.86);
  color: #b7cfdb;
  font-size: 12px;
}
.inline-toggle input {
  accent-color: #60a5fa;
}
.workspace-actions--sidebar .field-input,
.workspace-actions--sidebar .panel-select {
  width: 100%;
}
.decision-batch-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.doc-stack--compact .summary-box {
  min-height: 70px;
  display: flex;
  align-items: center;
}
.doc-status-board {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.doc-status-card {
  display: grid;
  gap: 4px;
  padding: 12px;
}
.doc-status-card small {
  color: #9eb8c7;
  font-size: 11px;
}
.decision-form__grid,
.doc-stack {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.mdt-content--moderator .decision-form__grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.mdt-content--moderator .doc-stack--compact {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.mdt-content--moderator .doc-status-board {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.mdt-content-grid--single > .mdt-panel:only-child,
.mdt-content-grid--single > .mdt-panel:nth-child(1):last-child {
  grid-column: 1 / -1;
}
.mdt-content-grid--single > .mdt-panel:nth-child(1):not(:last-child) {
  grid-column: auto;
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
.mini-link:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}
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
html[data-theme='light'] .mdt-page::before {
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.35), transparent 18%),
    linear-gradient(90deg, rgba(187, 204, 220, 0.22) 1px, transparent 1px),
    linear-gradient(rgba(187, 204, 220, 0.18) 1px, transparent 1px);
}
html[data-theme='light'] .mdt-hero,
html[data-theme='light'] .mdt-panel {
  border-color: rgba(187, 204, 220, 0.72);
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), rgba(59, 130, 246, 0) 38%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(245,249,253,.98) 100%);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}
html[data-theme='light'] .hero-badge,
html[data-theme='light'] .mdt-flow-step,
html[data-theme='light'] .mdt-flow-step__index,
html[data-theme='light'] .clinical-fact,
html[data-theme='light'] .guide-score,
html[data-theme='light'] .session-compact-item,
html[data-theme='light'] .hero-conclusion-card,
html[data-theme='light'] .todo-row,
html[data-theme='light'] .cockpit-main,
html[data-theme='light'] .cockpit-card,
html[data-theme='light'] .hero-editor-card,
html[data-theme='light'] .snapshot-item,
html[data-theme='light'] .owner-mini-row,
html[data-theme='light'] .decision-command-strip,
html[data-theme='light'] .doc-status-card,
html[data-theme='light'] .mdt-toolbar,
html[data-theme='light'] .mini-card,
html[data-theme='light'] .sheet-item,
html[data-theme='light'] .system-card,
html[data-theme='light'] .specialist-row,
html[data-theme='light'] .focus-specialist-card,
html[data-theme='light'] .session-chip,
html[data-theme='light'] .deep-panel,
html[data-theme='light'] .trend-metrics__item,
html[data-theme='light'] .assistant-note,
html[data-theme='light'] .timeline-item,
html[data-theme='light'] .alert-chain__item,
html[data-theme='light'] .impact-card,
html[data-theme='light'] .decision-item,
html[data-theme='light'] .inline-toggle,
html[data-theme='light'] .summary-box,
html[data-theme='light'] .empty-box,
html[data-theme='light'] .priority-card,
html[data-theme='light'] .conflict-card,
html[data-theme='light'] .detail-block,
html[data-theme='light'] .chip,
html[data-theme='light'] .panel-select,
html[data-theme='light'] .field-input,
html[data-theme='light'] .field-textarea,
html[data-theme='light'] .mdt-select {
  border-color: rgba(187, 204, 220, 0.72);
  background: rgba(241, 246, 251, 0.96);
  color: #1f3852;
  box-shadow: none;
}
html[data-theme='light'] .mdt-title,
html[data-theme='light'] .mdt-flow-step strong,
html[data-theme='light'] .guide-header h2,
html[data-theme='light'] .guide-score strong,
html[data-theme='light'] .clinical-fact strong,
html[data-theme='light'] .session-compact-item strong,
html[data-theme='light'] .hero-conclusion-card strong,
html[data-theme='light'] .cockpit-main strong,
html[data-theme='light'] .cockpit-card strong,
html[data-theme='light'] .snapshot-item strong,
html[data-theme='light'] .owner-mini-row strong,
html[data-theme='light'] .decision-command-strip strong,
html[data-theme='light'] .doc-status-card strong,
html[data-theme='light'] .mini-card strong,
html[data-theme='light'] .patient-sheet__name,
html[data-theme='light'] .sheet-item strong,
html[data-theme='light'] .system-card__domain,
html[data-theme='light'] .specialist-row__domain,
html[data-theme='light'] .focus-specialist-card__head strong,
html[data-theme='light'] .deep-panel__title,
html[data-theme='light'] .decision-item__head strong,
html[data-theme='light'] .priority-card__head strong,
html[data-theme='light'] .conflict-card__title {
  color: #16324f;
}
html[data-theme='light'] .mdt-kicker,
html[data-theme='light'] .mdt-desc,
html[data-theme='light'] .mdt-flow-step small,
html[data-theme='light'] .guide-header p,
html[data-theme='light'] .guide-score span,
html[data-theme='light'] .clinical-fact span,
html[data-theme='light'] .session-compact-item span,
html[data-theme='light'] .hero-conclusion-card span,
html[data-theme='light'] .cockpit-main span,
html[data-theme='light'] .cockpit-card span,
html[data-theme='light'] .snapshot-item span,
html[data-theme='light'] .owner-mini-row,
html[data-theme='light'] .decision-command-strip span,
html[data-theme='light'] .doc-status-card span,
html[data-theme='light'] .doc-status-card small,
html[data-theme='light'] .todo-row small,
html[data-theme='light'] .toolbar-label,
html[data-theme='light'] .mini-card span,
html[data-theme='light'] .mini-card small,
html[data-theme='light'] .detail-label,
html[data-theme='light'] .conflict-card__agents,
html[data-theme='light'] .patient-sheet__sub,
html[data-theme='light'] .sheet-item span,
html[data-theme='light'] .system-card__priority,
html[data-theme='light'] .system-card__status,
html[data-theme='light'] .system-card__summary,
html[data-theme='light'] .specialist-row__summary,
html[data-theme='light'] .muted-line,
html[data-theme='light'] .specialist-row__meta,
html[data-theme='light'] .focus-specialist-card__head span,
html[data-theme='light'] .focus-specialist-card__summary,
html[data-theme='light'] .section-kicker,
html[data-theme='light'] .trend-placeholder__header,
html[data-theme='light'] .trend-placeholder__caption,
html[data-theme='light'] .trend-metrics__item span,
html[data-theme='light'] .trend-metrics__item strong,
html[data-theme='light'] .assistant-note__label,
html[data-theme='light'] .assistant-note__text,
html[data-theme='light'] .timeline-item span,
html[data-theme='light'] .timeline-item small,
html[data-theme='light'] .decision-bucket__head,
html[data-theme='light'] .alert-chain__time,
html[data-theme='light'] .impact-card__title,
html[data-theme='light'] .alert-chain__text,
html[data-theme='light'] .impact-card__text,
html[data-theme='light'] .decision-item__text,
html[data-theme='light'] .alert-chain__sub,
html[data-theme='light'] .impact-card__sub,
html[data-theme='light'] .decision-item__head span,
html[data-theme='light'] .decision-item__meta span,
html[data-theme='light'] .mini-link,
html[data-theme='light'] .action-list,
html[data-theme='light'] .summary-box,
html[data-theme='light'] .empty-box {
  color: #6f8399;
}
html[data-theme='light'] .hero-badge--focus,
html[data-theme='light'] .row-active-chip {
  background: rgba(219, 234, 254, 0.98);
  border-color: rgba(59, 130, 246, 0.28);
  color: #1d4ed8;
}
html[data-theme='light'] .cockpit-card--accent {
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.12), rgba(59, 130, 246, 0) 45%),
    linear-gradient(180deg, rgba(255,255,255,.98), rgba(239,246,255,.98));
}
html[data-theme='light'] .hero-badge--critical {
  background: rgba(255, 241, 244, 0.98);
  border-color: rgba(251, 113, 133, 0.3);
  color: #be123c;
}
html[data-theme='light'] .hero-badge--warning {
  background: rgba(254, 243, 199, 0.98);
  border-color: rgba(251, 191, 36, 0.3);
  color: #b45309;
}
html[data-theme='light'] .decision-safety {
  border-color: rgba(217, 119, 6, 0.24);
  background: #fff7ed;
  color: #9a3412;
}
html[data-theme='light'] .hero-badge--closed,
html[data-theme='light'] .session-chip--closed {
  background: rgba(255, 241, 242, 0.98);
  border-color: rgba(251, 113, 133, 0.28);
  color: #be123c;
}
html[data-theme='light'] .session-chip--tag {
  background: rgba(219, 234, 254, 0.98);
  border-color: rgba(59, 130, 246, 0.28);
  color: #1d4ed8;
}
html[data-theme='light'] .session-chip--done {
  background: rgba(220, 252, 231, 0.98);
  border-color: rgba(16, 185, 129, 0.28);
  color: #047857;
}
html[data-theme='light'] .session-chip--running {
  background: rgba(254, 243, 199, 0.98);
  border-color: rgba(245, 158, 11, 0.28);
  color: #b45309;
}
html[data-theme='light'] .system-card.is-active,
html[data-theme='light'] .specialist-row.is-active {
  border-color: rgba(59, 130, 246, 0.34);
  box-shadow: inset 3px 0 0 rgba(59, 130, 246, 0.92);
  background: rgba(231, 241, 249, 0.98);
}
html[data-theme='light'] .system-card:hover,
html[data-theme='light'] .specialist-row:hover {
  border-color: rgba(59, 130, 246, 0.28);
}
html[data-theme='light'] .mdt-flow-step.is-active {
  border-color: rgba(14, 165, 233, .32);
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, .12), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(235, 248, 252, .98));
}
html[data-theme='light'] .mdt-flow-step.is-done .mdt-flow-step__index {
  background: rgba(220, 252, 231, .98);
  color: #047857;
}
html[data-theme='light'] .summary-box--hero {
  background: linear-gradient(180deg, rgba(255,255,255,.98), rgba(241,246,251,.98));
}
html[data-theme='light'] .trend-placeholder__chart span {
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.78), rgba(59, 130, 246, 0.2));
}
html[data-theme='light'] .toolbar-hint {
  border-color: rgba(245, 158, 11, 0.28);
  background: rgba(254, 243, 199, 0.98);
  color: #b45309;
}
html[data-theme='light'] .error-box {
  border-color: rgba(251, 113, 133, 0.28);
  background: rgba(255, 241, 242, 0.98);
  color: #be123c;
}

/* Align MDT light mode with the cyan workspace pages: pale shell and true light cards. */
html[data-theme='light'] .mdt-page {
  min-height: calc(100vh - 88px);
  padding: 22px;
  background:
    radial-gradient(circle at 12% 0%, rgba(34, 211, 238, .12), transparent 30%),
    radial-gradient(circle at 88% 8%, rgba(20, 184, 166, .10), transparent 30%),
    linear-gradient(180deg, rgba(236, 252, 255, .92), rgba(245, 250, 255, .96));
  color: #07172b;
}
html[data-theme='light'] .mdt-page::before {
  display: none;
}
html[data-theme='light'] .mdt-hero {
  border-color: rgba(15, 23, 42, .08);
  background: linear-gradient(135deg, rgba(7, 25, 42, .96), rgba(14, 30, 45, .94));
  box-shadow: 0 18px 42px rgba(15, 23, 42, .12);
}
html[data-theme='light'] .mdt-panel {
  border-color: rgba(226, 232, 240, .96);
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 10px 28px rgba(15, 23, 42, .08);
}
html[data-theme='light'] .mdt-panel :deep(.ant-card-head) {
  border-bottom-color: rgba(226, 232, 240, .86);
}
html[data-theme='light'] .mdt-panel :deep(.ant-card-head-title) {
  color: #07172b;
  font-weight: 800;
}
html[data-theme='light'] .mdt-title,
html[data-theme='light'] .cockpit-main strong,
html[data-theme='light'] .cockpit-card strong,
html[data-theme='light'] .snapshot-item strong,
html[data-theme='light'] .sheet-item strong,
html[data-theme='light'] .system-card__domain,
html[data-theme='light'] .specialist-row__domain,
html[data-theme='light'] .focus-specialist-card__head strong,
html[data-theme='light'] .mini-card strong,
html[data-theme='light'] .decision-command-strip strong,
html[data-theme='light'] .decision-item__head strong,
html[data-theme='light'] .priority-card__head strong,
html[data-theme='light'] .conflict-card__title,
html[data-theme='light'] .doc-status-card strong,
html[data-theme='light'] .impact-card__text,
html[data-theme='light'] .alert-chain__text,
html[data-theme='light'] .summary-box {
  color: #f8fbff;
}
html[data-theme='light'] .mdt-kicker,
html[data-theme='light'] .mdt-desc,
html[data-theme='light'] .cockpit-main span,
html[data-theme='light'] .cockpit-card span,
html[data-theme='light'] .snapshot-item span,
html[data-theme='light'] .sheet-item span,
html[data-theme='light'] .system-card__priority,
html[data-theme='light'] .system-card__status,
html[data-theme='light'] .system-card__summary,
html[data-theme='light'] .specialist-row__summary,
html[data-theme='light'] .specialist-row__meta,
html[data-theme='light'] .mini-card span,
html[data-theme='light'] .mini-card small,
html[data-theme='light'] .decision-command-strip span,
html[data-theme='light'] .decision-item__head span,
html[data-theme='light'] .decision-item__meta span,
html[data-theme='light'] .impact-card__title,
html[data-theme='light'] .impact-card__sub,
html[data-theme='light'] .alert-chain__time,
html[data-theme='light'] .alert-chain__sub,
html[data-theme='light'] .doc-status-card span,
html[data-theme='light'] .doc-status-card small,
html[data-theme='light'] .summary-box,
html[data-theme='light'] .empty-box {
  color: #9fc4d7;
}
html[data-theme='light'] .cockpit-main,
html[data-theme='light'] .cockpit-card,
html[data-theme='light'] .mdt-flow-step,
html[data-theme='light'] .clinical-fact,
html[data-theme='light'] .guide-score,
html[data-theme='light'] .session-compact-item,
html[data-theme='light'] .snapshot-item,
html[data-theme='light'] .sheet-item,
html[data-theme='light'] .system-card,
html[data-theme='light'] .specialist-row,
html[data-theme='light'] .focus-specialist-card,
html[data-theme='light'] .mini-card,
html[data-theme='light'] .decision-command-strip,
html[data-theme='light'] .decision-item,
html[data-theme='light'] .priority-card,
html[data-theme='light'] .conflict-card,
html[data-theme='light'] .impact-card,
html[data-theme='light'] .alert-chain__item,
html[data-theme='light'] .doc-status-card,
html[data-theme='light'] .summary-box,
html[data-theme='light'] .empty-box,
html[data-theme='light'] .deep-panel,
html[data-theme='light'] .assistant-note,
html[data-theme='light'] .timeline-item,
html[data-theme='light'] .trend-metrics__item,
html[data-theme='light'] .detail-block {
  border-color: rgba(125, 167, 214, .14);
  background: linear-gradient(135deg, rgba(71, 88, 102, .96), rgba(42, 57, 72, .98));
  box-shadow: none;
}
html[data-theme='light'] .cockpit-card--accent,
html[data-theme='light'] .sheet-item:nth-child(2),
html[data-theme='light'] .doc-status-card:nth-child(2) {
  border-color: rgba(34, 211, 238, .18);
  background: linear-gradient(135deg, rgba(50, 103, 116, .92), rgba(42, 57, 72, .98));
}
html[data-theme='light'] .sheet-item:nth-child(3),
html[data-theme='light'] .doc-status-card:nth-child(3) {
  border-color: rgba(245, 158, 11, .20);
  background: linear-gradient(135deg, rgba(117, 98, 66, .88), rgba(42, 57, 72, .98));
}
html[data-theme='light'] .hero-editor-card,
html[data-theme='light'] .mdt-toolbar,
html[data-theme='light'] .doc-block {
  border-color: rgba(226, 232, 240, .92);
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 8px 22px rgba(15, 23, 42, .06);
}
html[data-theme='light'] .hero-editor-card .detail-label,
html[data-theme='light'] .toolbar-label,
html[data-theme='light'] .patient-sheet__sub {
  color: #64748b;
}
html[data-theme='light'] .patient-sheet__name,
html[data-theme='light'] .hero-editor-card .empty-box,
html[data-theme='light'] .doc-block .detail-label {
  color: #07172b;
}
html[data-theme='light'] .doc-block .summary-box {
  border-color: rgba(203, 213, 225, .78);
  background: rgba(248, 250, 252, .98);
  color: #334155;
}
html[data-theme='light'] .owner-mini-row,
html[data-theme='light'] .todo-row,
html[data-theme='light'] .session-chip,
html[data-theme='light'] .chip,
html[data-theme='light'] .inline-toggle {
  border-color: rgba(203, 213, 225, .86);
  background: rgba(248, 250, 252, .96);
  color: #334155;
}
html[data-theme='light'] .owner-mini-row strong,
html[data-theme='light'] .todo-row strong {
  color: #07172b;
}
html[data-theme='light'] .panel-select,
html[data-theme='light'] .field-input,
html[data-theme='light'] .field-textarea,
html[data-theme='light'] .mdt-select {
  border-color: rgba(203, 213, 225, .92);
  background: rgba(248, 250, 252, .98);
  color: #0f172a;
}
html[data-theme='light'] .panel-select:focus,
html[data-theme='light'] .field-input:focus,
html[data-theme='light'] .field-textarea:focus,
html[data-theme='light'] .mdt-select:focus {
  border-color: rgba(37, 99, 235, .42);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, .10);
  outline: none;
}
html[data-theme='light'] .hero-badge {
  border-color: rgba(125, 167, 214, .22);
  background: rgba(15, 33, 52, .76);
  color: #dff7ff;
}
html[data-theme='light'] .hero-badge--soft {
  background: rgba(255, 255, 255, .10);
  color: #b7d9ea;
}
html[data-theme='light'] .hero-badge--focus,
html[data-theme='light'] .row-active-chip {
  border-color: rgba(103, 232, 249, .28);
  background: rgba(8, 64, 84, .72);
  color: #67e8f9;
}
html[data-theme='light'] .system-card.is-active,
html[data-theme='light'] .specialist-row.is-active {
  border-color: rgba(34, 211, 238, .34);
  background: linear-gradient(135deg, rgba(8, 64, 84, .82), rgba(42, 57, 72, .98));
  box-shadow: inset 3px 0 0 rgba(34, 211, 238, .9);
}
html[data-theme='light'] .system-card:hover,
html[data-theme='light'] .specialist-row:hover {
  border-color: rgba(34, 211, 238, .28);
}
html[data-theme='light'] .mini-link {
  color: #67e8f9;
}
html[data-theme='light'] .action-list,
html[data-theme='light'] .assistant-note__text,
html[data-theme='light'] .trend-placeholder__caption,
html[data-theme='light'] .timeline-item span,
html[data-theme='light'] .timeline-item small {
  color: #c7deea;
}
html[data-theme='light'] .mdt-content--moderator .mdt-grid--assessment > .mdt-panel:last-child,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--decisions > .mdt-panel:last-child,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--documents > .mdt-panel:first-child {
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, .08), transparent 34%),
    rgba(255, 255, 255, .98);
}
html[data-theme='light'] .mdt-content--moderator .mdt-grid--assessment > .mdt-panel:first-child,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--timeline > .mdt-panel,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--documents > .mdt-panel:last-child {
  background:
    radial-gradient(circle at top right, rgba(15, 118, 110, .09), transparent 36%),
    rgba(248, 252, 255, .98);
}
html[data-theme='light'] .mdt-hero {
  border-color: rgba(187, 204, 220, .82);
  background:
    radial-gradient(circle at 10% 0%, rgba(34, 211, 238, .14), transparent 34%),
    radial-gradient(circle at 92% 8%, rgba(59, 130, 246, .10), transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, .98), rgba(241, 248, 253, .98));
  box-shadow: 0 16px 38px rgba(15, 23, 42, .10);
}
html[data-theme='light'] .clinical-card {
  border-color: rgba(191, 219, 254, .82);
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, .10), rgba(56, 189, 248, 0) 42%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(239, 248, 252, .98));
  box-shadow: 0 8px 22px rgba(15, 23, 42, .06);
}
html[data-theme='light'] .clinical-card--patient {
  border-left-color: rgba(37, 99, 235, .72);
}
html[data-theme='light'] .clinical-card--summary {
  border-left-color: rgba(14, 165, 233, .72);
}
html[data-theme='light'] .clinical-card--metrics {
  border-left-color: rgba(16, 185, 129, .72);
}
html[data-theme='light'] .clinical-card--handoff {
  border-left-color: rgba(245, 158, 11, .72);
}
html[data-theme='light'] .clinical-card__head strong,
html[data-theme='light'] .clinical-metric strong {
  color: #16324f;
}
html[data-theme='light'] .clinical-card__head span,
html[data-theme='light'] .clinical-metric span {
  color: #64748b;
}
html[data-theme='light'] .clinical-metric {
  border-color: rgba(203, 213, 225, .82);
  background: rgba(248, 250, 252, .92);
}
html[data-theme='light'] .next-action-box {
  border-color: rgba(245, 158, 11, .30);
  background: rgba(255, 251, 235, .96);
  color: #92400e;
}
html[data-theme='light'] .mdt-title,
html[data-theme='light'] .cockpit-main strong,
html[data-theme='light'] .cockpit-card strong,
html[data-theme='light'] .snapshot-item strong,
html[data-theme='light'] .sheet-item strong,
html[data-theme='light'] .system-card__domain,
html[data-theme='light'] .specialist-row__domain,
html[data-theme='light'] .focus-specialist-card__head strong,
html[data-theme='light'] .mini-card strong,
html[data-theme='light'] .decision-command-strip strong,
html[data-theme='light'] .decision-item__head strong,
html[data-theme='light'] .priority-card__head strong,
html[data-theme='light'] .conflict-card__title,
html[data-theme='light'] .doc-status-card strong,
html[data-theme='light'] .impact-card__text,
html[data-theme='light'] .alert-chain__text,
html[data-theme='light'] .summary-box,
html[data-theme='light'] .patient-sheet__name,
html[data-theme='light'] .deep-panel__title,
html[data-theme='light'] .timeline-item strong {
  color: #16324f;
}
html[data-theme='light'] .mdt-kicker,
html[data-theme='light'] .mdt-desc,
html[data-theme='light'] .cockpit-main span,
html[data-theme='light'] .cockpit-card span,
html[data-theme='light'] .snapshot-item span,
html[data-theme='light'] .sheet-item span,
html[data-theme='light'] .system-card__priority,
html[data-theme='light'] .system-card__status,
html[data-theme='light'] .system-card__summary,
html[data-theme='light'] .specialist-row__summary,
html[data-theme='light'] .specialist-row__meta,
html[data-theme='light'] .mini-card span,
html[data-theme='light'] .mini-card small,
html[data-theme='light'] .decision-command-strip span,
html[data-theme='light'] .decision-item__head span,
html[data-theme='light'] .decision-item__meta span,
html[data-theme='light'] .impact-card__title,
html[data-theme='light'] .impact-card__sub,
html[data-theme='light'] .alert-chain__time,
html[data-theme='light'] .alert-chain__sub,
html[data-theme='light'] .doc-status-card span,
html[data-theme='light'] .doc-status-card small,
html[data-theme='light'] .empty-box,
html[data-theme='light'] .toolbar-label,
html[data-theme='light'] .detail-label,
html[data-theme='light'] .conflict-card__agents,
html[data-theme='light'] .patient-sheet__sub,
html[data-theme='light'] .section-kicker,
html[data-theme='light'] .trend-placeholder__caption,
html[data-theme='light'] .assistant-note__label,
html[data-theme='light'] .assistant-note__text,
html[data-theme='light'] .timeline-item span,
html[data-theme='light'] .timeline-item small,
html[data-theme='light'] .decision-bucket__head,
html[data-theme='light'] .action-list {
  color: #64748b;
}
html[data-theme='light'] .cockpit-main,
html[data-theme='light'] .cockpit-card,
html[data-theme='light'] .snapshot-item,
html[data-theme='light'] .sheet-item,
html[data-theme='light'] .system-card,
html[data-theme='light'] .specialist-row,
html[data-theme='light'] .focus-specialist-card,
html[data-theme='light'] .mini-card,
html[data-theme='light'] .decision-command-strip,
html[data-theme='light'] .decision-item,
html[data-theme='light'] .priority-card,
html[data-theme='light'] .conflict-card,
html[data-theme='light'] .impact-card,
html[data-theme='light'] .alert-chain__item,
html[data-theme='light'] .doc-status-card,
html[data-theme='light'] .summary-box,
html[data-theme='light'] .empty-box,
html[data-theme='light'] .deep-panel,
html[data-theme='light'] .assistant-note,
html[data-theme='light'] .timeline-item,
html[data-theme='light'] .trend-metrics__item,
html[data-theme='light'] .detail-block,
html[data-theme='light'] .hero-conclusion-card,
html[data-theme='light'] .hero-editor-card,
html[data-theme='light'] .mdt-toolbar,
html[data-theme='light'] .doc-block,
html[data-theme='light'] .owner-mini-row,
html[data-theme='light'] .todo-row,
html[data-theme='light'] .mdt-clinical-meta {
  border-color: rgba(203, 213, 225, .82);
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, .08), rgba(56, 189, 248, 0) 38%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(244, 249, 253, .98));
  box-shadow: 0 8px 22px rgba(15, 23, 42, .06);
}
html[data-theme='light'] .cockpit-card--accent,
html[data-theme='light'] .sheet-item:nth-child(2),
html[data-theme='light'] .sheet-item:nth-child(3),
html[data-theme='light'] .doc-status-card:nth-child(2),
html[data-theme='light'] .doc-status-card:nth-child(3),
html[data-theme='light'] .mdt-content--moderator .mdt-grid--assessment > .mdt-panel:last-child,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--decisions > .mdt-panel:last-child,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--documents > .mdt-panel:first-child,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--assessment > .mdt-panel:first-child,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--timeline > .mdt-panel,
html[data-theme='light'] .mdt-content--moderator .mdt-grid--documents > .mdt-panel:last-child {
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, .10), transparent 38%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(239, 248, 252, .98));
}
html[data-theme='light'] .hero-badge {
  border-color: rgba(203, 213, 225, .86);
  background: rgba(248, 250, 252, .94);
  color: #334155;
}
html[data-theme='light'] .hero-badge--soft {
  background: rgba(241, 245, 249, .96);
  color: #475569;
}
html[data-theme='light'] .hero-badge--focus,
html[data-theme='light'] .row-active-chip {
  border-color: rgba(56, 189, 248, .28);
  background: rgba(240, 249, 255, .98);
  color: #0369a1;
}
html[data-theme='light'] .system-card.is-active,
html[data-theme='light'] .specialist-row.is-active {
  border-color: rgba(56, 189, 248, .38);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, .14), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(235, 248, 252, .98));
  box-shadow: inset 3px 0 0 rgba(14, 165, 233, .75);
}
html[data-theme='light'] .mini-link {
  color: #2563eb;
}
html[data-theme='light'] .guide-header h2,
html[data-theme='light'] .clinical-fact strong,
html[data-theme='light'] .session-compact-item strong {
  color: #16324f;
}
html[data-theme='light'] .guide-header p,
html[data-theme='light'] .clinical-fact span,
html[data-theme='light'] .session-compact-item span,
html[data-theme='light'] .mdt-flow-step small {
  color: #64748b;
}
html[data-theme='light'] .guide-score {
  border-color: rgba(16, 185, 129, .24);
  background: rgba(236, 253, 245, .98);
}
html[data-theme='light'] .guide-score span {
  color: #047857;
}
html[data-theme='light'] .guide-score strong {
  color: #065f46;
}
html[data-theme='light'] .mdt-flow-step,
html[data-theme='light'] .clinical-fact,
html[data-theme='light'] .session-compact-item {
  border-color: rgba(203, 213, 225, .82);
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, .08), rgba(56, 189, 248, 0) 38%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(244, 249, 253, .98));
  box-shadow: 0 8px 22px rgba(15, 23, 42, .06);
}
html[data-theme='light'] .mdt-flow-step__index {
  border: 1px solid rgba(186, 230, 253, .92);
  background: rgba(240, 249, 255, .98);
  color: #0369a1;
}
html[data-theme='light'] .mdt-flow-step strong,
html[data-theme='light'] .clinical-fact strong,
html[data-theme='light'] .session-compact-item strong {
  color: #16324f;
}
html[data-theme='light'] .mdt-flow-step small,
html[data-theme='light'] .clinical-fact span,
html[data-theme='light'] .session-compact-item span {
  color: #64748b;
}
html[data-theme='light'] .mdt-flow-step.is-active {
  border-color: rgba(14, 165, 233, .36);
  background:
    radial-gradient(circle at top right, rgba(14, 165, 233, .14), transparent 42%),
    linear-gradient(180deg, rgba(248, 253, 255, .99), rgba(232, 247, 252, .98));
  box-shadow: 0 10px 24px rgba(14, 165, 233, .10);
}
html[data-theme='light'] .mdt-flow-step.is-done {
  background:
    radial-gradient(circle at top right, rgba(16, 185, 129, .10), transparent 40%),
    linear-gradient(180deg, rgba(255, 255, 255, .99), rgba(240, 253, 250, .98));
}
@media (max-width: 1280px) {
  .mdt-hero :deep(.ant-card-body),
  .mdt-command-top,
  .mdt-flow,
  .mdt-clinical-strip,
  .mdt-clinical-meta,
  .mdt-cockpit,
  .hero-editor-grid,
  .mdt-workspace,
  .mdt-moderator-board,
  .clinical-summary-layout,
  .mdt-review-grid,
  .mdt-content--moderator,
  .mdt-content-grid,
  .deep-panel-grid {
    grid-template-columns: 1fr;
  }
  .mdt-content--moderator > .mdt-content-grid {
    display: grid;
  }
  .mdt-content--moderator .mdt-grid--assessment > .mdt-panel,
  .mdt-content--moderator .mdt-grid--decisions > .mdt-panel,
  .mdt-content--moderator .mdt-grid--documents > .mdt-panel,
  .mdt-content--moderator .mdt-grid--timeline > .mdt-panel {
    grid-column: auto;
    grid-row: auto;
  }
  .mdt-content--moderator .mdt-grid--assessment .detail-stack,
  .mdt-content--moderator .decision-buckets {
    grid-template-columns: 1fr;
  }
  .mdt-sidebar {
    position: static;
  }
  .mdt-action-rail {
    position: static;
  }
}
@media (max-width: 1100px) {
  .clinical-metric-grid,
  .hero-conclusion-row,
  .session-snapshot,
  .doc-status-board,
  .priority-row,
  .patient-sheet__grid,
  .trend-metrics,
  .decision-form__grid,
  .doc-stack { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 720px) {
  .clinical-actions,
  .clinical-card--patient .clinical-actions,
  .mdt-clinical-meta .meta-edit-grid,
  .hero-conclusion-row,
  .session-snapshot,
  .doc-status-board,
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
