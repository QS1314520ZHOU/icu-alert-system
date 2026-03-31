<template>
  <div class="mdt-page">
    <a-card :bordered="false" class="mdt-hero">
      <div class="mdt-hero__copy">
        <div class="mdt-kicker">MDT 临床协作工作站</div>
        <h1 class="mdt-title">MDT 多智能体会诊</h1>
        <p class="mdt-desc">以七大生理系统为骨架，以 MDT 讨论流为主线，把患者数字孪生、专科分析、冲突协调与执行决议收敛到一个临床工作站。</p>
        <div class="mdt-hero__badges">
          <span class="hero-badge">{{ loading ? '会诊处理中' : '会诊就绪' }}</span>
          <span v-if="workspaceDirty" class="hero-badge hero-badge--warning">有未保存变更</span>
          <span class="hero-badge hero-badge--soft">{{ selectedPatientLabel }}</span>
          <span class="hero-badge hero-badge--focus">聚焦 {{ activeSystemLabel }}</span>
          <span v-if="currentSessionId" class="hero-badge hero-badge--soft">会话 {{ currentSessionLabel }}</span>
          <span class="hero-badge hero-badge--soft">阶段 {{ currentPhaseLabel }}</span>
          <span :class="['hero-badge', `hero-badge--${mdtSeverityTone}`]">风险 {{ mdtSeverityLabel }}</span>
          <span :class="['hero-badge', `hero-badge--${closureTone}`]">闭环 {{ closureLabel }}</span>
          <span v-if="isSessionClosed" class="hero-badge hero-badge--closed">已归档只读</span>
        </div>
        <div v-if="viewMode === 'moderator'" class="hero-conclusion-row">
          <div class="hero-conclusion-card">
            <span>总控结论</span>
            <strong>{{ metaSummary }}</strong>
          </div>
          <div class="hero-conclusion-card hero-conclusion-card--soft">
            <span>冲突焦点</span>
            <strong>{{ conflictRows.length ? conflictRows[0]?.summary || '存在跨专科冲突' : '当前无明显冲突' }}</strong>
          </div>
          <div class="hero-conclusion-card hero-conclusion-card--soft">
            <span>首要动作</span>
            <strong>{{ metaActions[0] || '等待总控智能体生成行动建议' }}</strong>
          </div>
        </div>
        <div v-if="viewMode === 'moderator' && ownerSummaryRows.length" class="hero-conclusion-row">
          <div class="hero-conclusion-card hero-conclusion-card--soft hero-conclusion-card--todo">
            <span>负责人看板</span>
            <div class="todo-list">
              <div v-for="item in ownerSummaryRows" :key="item.owner" class="todo-row">
                <strong>{{ item.owner }}</strong>
                <small>待执行 {{ item.pending }} / 进行中 {{ item.inProgress }} / 已完成 {{ item.completed }}</small>
              </div>
            </div>
          </div>
        </div>
        <div v-if="viewMode === 'moderator'" class="hero-conclusion-row">
          <div class="hero-conclusion-card hero-conclusion-card--soft hero-conclusion-card--todo">
            <span>会诊元数据编辑</span>
            <div class="meta-edit-grid">
              <input v-model="tagsText" class="field-input" :disabled="isSessionClosed" placeholder="标签：如 脓毒症、撤机、高乳酸" />
              <input v-model="participantsText" class="field-input" :disabled="isSessionClosed" placeholder="参与成员：ICU、感染、呼吸、药学" />
              <textarea v-model="finalSummary" class="field-textarea" :disabled="isSessionClosed" rows="3" placeholder="最终纪要（留空则关闭会话时自动生成）"></textarea>
            </div>
          </div>
        </div>
        <div v-if="viewMode === 'moderator' && linkedDocumentSummaryRows.length" class="hero-conclusion-row">
          <div class="hero-conclusion-card hero-conclusion-card--soft hero-conclusion-card--todo">
            <span>文书联动摘要</span>
            <div class="todo-list">
              <div v-for="item in linkedDocumentSummaryRows" :key="item.label" class="todo-row">
                <strong>{{ item.label }}</strong>
                <small>{{ item.value }}</small>
              </div>
            </div>
          </div>
        </div>
        <div v-if="viewMode === 'moderator'" class="hero-conclusion-row">
          <div class="hero-conclusion-card hero-conclusion-card--soft">
            <span>会诊标签</span>
            <strong>{{ sessionTags.length ? sessionTags.join('、') : '未设置' }}</strong>
          </div>
          <div class="hero-conclusion-card hero-conclusion-card--soft">
            <span>参与成员</span>
            <strong>{{ sessionParticipants.length ? sessionParticipants.join('、') : '未设置' }}</strong>
          </div>
          <div class="hero-conclusion-card hero-conclusion-card--soft">
            <span>最终纪要</span>
            <strong>{{ finalSummary || '未填写，关闭会话时将自动生成摘要' }}</strong>
          </div>
        </div>
        <div v-if="viewMode === 'moderator' && isSessionClosed && finalSummary" class="hero-conclusion-row">
          <div class="hero-conclusion-card hero-conclusion-card--soft hero-conclusion-card--todo">
            <span>归档纪要</span>
            <div class="summary-box">{{ finalSummary }}</div>
          </div>
        </div>
        <div v-if="signalSourceRows.length" class="hero-conclusion-row">
          <div v-for="item in signalSourceRows" :key="item.label" class="hero-conclusion-card hero-conclusion-card--soft">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <div v-if="viewMode === 'moderator' && todoRows.length" class="hero-conclusion-row">
          <div class="hero-conclusion-card hero-conclusion-card--soft hero-conclusion-card--todo">
            <span>待办清单</span>
            <div class="todo-list">
              <div v-for="item in todoRows" :key="item.id" class="todo-row">
                <strong>{{ item.action }}</strong>
                <small>{{ item.owner }} / {{ item.deadline || '时限未填' }}</small>
              </div>
            </div>
          </div>
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
            <div v-if="selectedPatientOutOfDeptHint" class="toolbar-hint">
              {{ selectedPatientOutOfDeptHint }}
            </div>
          </div>
        <div class="mdt-toolbar__actions">
          <a-button size="small" type="primary" :loading="loading" @click="loadAssessment(true)">刷新会诊</a-button>
          <a-button size="small" ghost @click="openPatientDetail" :disabled="!selectedPatientId">打开患者详情</a-button>
        </div>
        <div class="mdt-toolbar__row">
          <select v-model="viewMode" class="mdt-select mdt-select--compact">
            <option value="moderator">主持视图</option>
            <option value="deep">深度视图</option>
          </select>
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
                  <span class="session-chip">{{ item.updated_at ? String(item.updated_at).slice(5, 16).replace('T', ' ') : '时间未记载' }}</span>
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

      <main class="mdt-content">
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
                      <strong>{{ item.mode || activeSystemPanel.latest?.mode || '通气支持' }}</strong>
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

        <div :class="['mdt-content-grid', { 'mdt-content-grid--single': viewMode === 'moderator' }]">
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

        <div :class="['mdt-content-grid', { 'mdt-content-grid--single': viewMode === 'moderator' }]">
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

        <div v-if="viewMode === 'deep'" class="mdt-content-grid">
          <a-card :bordered="false" class="mdt-panel" title="总控智能体全局优先级">
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
            <div class="decision-summary-row">
              <div class="sheet-item">
                <span>待执行</span>
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
                <span>只看待执行</span>
              </label>
            </div>
            <div class="workspace-actions workspace-actions--top workspace-actions--sidebar">
              <select v-model="decisionOwnerFilter" class="panel-select">
                <option value="">全部负责人</option>
                <option v-for="item in decisionOwnerOptions" :key="item" :value="item">{{ item }}</option>
              </select>
              <div class="decision-batch-actions">
                <a-button size="small" :disabled="isSessionClosed" @click="markVisibleDecisions('in_progress')">批量进行中</a-button>
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
                          <option value="pending">待执行</option>
                          <option value="in_progress">进行中</option>
                          <option value="completed">已完成</option>
                          <option value="dismissed">已取消</option>
                        </select>
                      </div>
                      <textarea v-model="item.note" class="field-textarea" :disabled="isSessionClosed" rows="2" placeholder="补充说明 / 平衡方案"></textarea>
                    </div>
                    <div class="decision-item__meta">
                      <span>状态：{{ ({ pending: '待执行', in_progress: '进行中', completed: '已完成', dismissed: '已取消', draft: '草稿' } as Record<string, string>)[String(item.status || 'pending').toLowerCase()] || '待执行' }}</span>
                      <button
                        v-if="String(item.status || 'pending') !== 'completed'"
                        type="button"
                        class="mini-link"
                        :disabled="isSessionClosed"
                        @click="markDecisionStatus(item.id, 'completed')"
                      >
                        标记完成
                    </button>
                    <button
                        v-else
                        type="button"
                        class="mini-link"
                        :disabled="isSessionClosed"
                        @click="markDecisionStatus(item.id, 'pending')"
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

        <div :class="['mdt-content-grid', { 'mdt-content-grid--single': viewMode === 'moderator' }]">
          <a-card :bordered="false" class="mdt-panel" title="会诊记录 / 病程记录">
            <div v-if="viewMode === 'moderator'" class="doc-stack doc-stack--compact">
              <div class="doc-block">
                <div class="detail-label">会诊记录摘要</div>
                <div class="summary-box">{{ consultRecord || '暂无会诊记录，可切换到深度视图编辑完整文书。' }}</div>
                <div class="workspace-actions">
                  <a-button size="small" :loading="generatingDocType === 'consultation_request'" @click="generateDocument('consultation_request')">智能生成会诊记录</a-button>
                  <a-button size="small" type="primary" :loading="savingWorkspace" @click="saveWorkspace">保存摘要</a-button>
                </div>
              </div>
              <div class="doc-block">
                <div class="detail-label">病程记录摘要</div>
                <div class="summary-box">{{ progressRecord || '暂无病程记录，可切换到深度视图编辑完整文书。' }}</div>
              </div>
            </div>
            <div v-else class="doc-stack">
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
import { Button as AButton, Card as ACard } from 'ant-design-vue'
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
  status: 'pending',
  note: '',
}])
const pendingDecisionCount = computed(() => decisionRows.value.filter((item: any) => String(item.status || 'pending') === 'pending').length)
const inProgressDecisionCount = computed(() => decisionRows.value.filter((item: any) => String(item.status || '') === 'in_progress').length)
const completedDecisionCount = computed(() => decisionRows.value.filter((item: any) => String(item.status || '') === 'completed').length)
const dismissedDecisionCount = computed(() => decisionRows.value.filter((item: any) => String(item.status || '') === 'dismissed').length)
const decisionOwnerOptions = computed(() => Array.from(new Set(decisionRows.value.map((item: any) => String(item.owner || '').trim()).filter(Boolean))))
const decisionBuckets = computed(() => {
  const owner = decisionOwnerFilter.value.trim()
  const sourceRows = decisionOpenOnly.value
    ? decisionRows.value.filter((item: any) => String(item.status || 'pending') === 'pending')
    : decisionRows.value
  const rows = owner ? sourceRows.filter((item: any) => String(item.owner || '').trim() === owner) : sourceRows
  return [
    { key: 'pending', label: '待执行', items: rows.filter((item: any) => String(item.status || 'pending') === 'pending') },
    { key: 'in_progress', label: '进行中', items: rows.filter((item: any) => String(item.status || '') === 'in_progress') },
    { key: 'completed', label: '已完成', items: rows.filter((item: any) => String(item.status || '') === 'completed') },
    { key: 'dismissed', label: '已取消', items: rows.filter((item: any) => String(item.status || '') === 'dismissed') },
  ].filter((bucket) => bucket.items.length > 0 || !decisionOpenOnly.value)
})
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
  if (pendingDecisionCount.value || inProgressDecisionCount.value || completedDecisionCount.value) {
    parts.push(`执行概况：待执行${pendingDecisionCount.value}，进行中${inProgressDecisionCount.value}，已完成${completedDecisionCount.value}`)
  }
  return parts.join('\n')
})
const linkedDocumentSummaryRows = computed(() => {
  const rows: Array<{ label: string; value: string }> = []
  rows.push({ label: '会诊记录', value: consultRecord.value ? `已填写 ${consultRecord.value.length} 字` : '未填写，关闭会话时将自动补入纪要摘要' })
  rows.push({ label: '病程记录', value: progressRecord.value ? `已填写 ${progressRecord.value.length} 字` : '未填写，关闭会话时将自动补入纪要摘要' })
  rows.push({ label: '自动纪要', value: autoSessionSummary.value || '等待总控智能体生成可汇总内容' })
  return rows
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
      timeLabel: item?.created_at ? String(item.created_at).slice(0, 16).replace('T', ' ') : '时间未记载',
    }))
)
const todoRows = computed(() =>
  decisionRows.value
    .filter((item: any) => ['pending', 'in_progress'].includes(String(item.status || 'pending')))
    .slice(0, 5)
)
const closureTone = computed(() => {
  if (pendingDecisionCount.value > 0) return 'warning'
  if (completedDecisionCount.value > 0 && completedDecisionCount.value === decisionRows.value.length) return 'soft'
  return 'soft'
})
const closureLabel = computed(() => {
  const total = decisionRows.value.length
  if (!total) return '未生成决议'
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
  return ({ pending: '待执行', in_progress: '进行中', completed: '已完成', dismissed: '已取消', draft: '草稿' } as Record<string, string>)[String(status || 'pending').toLowerCase()] || '待执行'
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
    status: 'pending',
    note: '',
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
      status: 'pending',
      note: '',
    },
  ]
  appendActivityLog('新增决议', '已新增 1 条待执行决议')
}

function removeDecision(id: string) {
  const hit = decisions.value.find((item: any) => item.id === id)
  decisions.value = decisions.value.filter((item: any) => item.id !== id)
  appendActivityLog('删除决议', hit?.action || '已删除 1 条决议')
}

function markDecisionStatus(id: string, status: 'pending' | 'completed') {
  let action = ''
  decisions.value = decisions.value.map((item: any) => {
    if (item.id === id) {
      action = item.action || ''
      return { ...item, status }
    }
    return item
  })
  appendActivityLog('更新决议状态', `${action || '决议'} -> ${decisionStatusLabel(status)}`)
}

function markVisibleDecisions(status: 'in_progress' | 'completed') {
  const ids = new Set(
    decisionBuckets.value.flatMap((bucket: any) => (bucket.items || []).map((item: any) => item.id))
  )
  decisions.value = decisions.value.map((item: any) =>
    ids.has(item.id) ? { ...item, status } : item
  )
  appendActivityLog('批量推进决议', `已将 ${ids.size} 条可见决议更新为${decisionStatusLabel(status)}`)
}

async function switchSession(sessionId: string) {
  if (!selectedPatientId.value || !sessionId) return
  if (workspaceDirty.value && !window.confirm('当前 MDT 会话有未保存变更，确认切换会话吗？')) return
  const res = await getAiMdtWorkspaceSession(selectedPatientId.value, sessionId)
  workspaceRecord.value = res.data?.workspace || null
  workspaceDocuments.value = Array.isArray(res.data?.documents) ? res.data.documents : []
  generatedOrderDrafts.value = Array.isArray(res.data?.order_drafts) ? res.data.order_drafts : []
  currentSessionId.value = sessionId
  decisions.value = Array.isArray(workspaceRecord.value?.decisions) ? workspaceRecord.value.decisions : []
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
  decisions.value = decisions.value.map((item: any, idx: number) => ({ ...item, id: `decision-${Date.now()}-${idx}`, status: item.status === 'completed' ? 'pending' : item.status }))
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
  grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
}
.mdt-content-grid--single {
  grid-template-columns: minmax(0, 1fr);
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
  min-height: 88px;
  display: flex;
  align-items: center;
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
  .hero-conclusion-row,
  .priority-row,
  .patient-sheet__grid,
  .trend-metrics,
  .decision-form__grid,
  .doc-stack { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 720px) {
  .hero-conclusion-row,
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
