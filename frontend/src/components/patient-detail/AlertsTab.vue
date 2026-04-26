<template>
  <div>
    <div v-if="latestCompositeAlert" class="modi-panel">
      <div class="modi-head">
        <div>
          <div class="modi-title">多器官恶化指数 (MODI)</div>
          <div class="modi-sub">
            {{ fmtTime(latestCompositeAlert.created_at) || '时间未知' }} · 最近{{ latestCompositeWindowHours }}h
          </div>
        </div>
        <div class="modi-kpi-group">
          <div class="modi-kpi">
            <span>MODI</span>
            <strong>{{ latestCompositeModi ?? '—' }}</strong>
          </div>
          <div class="modi-kpi">
            <span>器官系统</span>
            <strong>{{ latestCompositeOrganCount }}</strong>
          </div>
        </div>
      </div>
      <div class="modi-organs">{{ latestCompositeInvolvedText }}</div>
      <div class="modi-chart">
        <DetailChart :option="compositeRadarOption" autoresize />
      </div>
      <div v-if="compositeClinicalChain(latestCompositeAlert) || compositeGroups(latestCompositeAlert).length" class="composite-suite composite-suite--headline">
        <section v-if="compositeClinicalChain(latestCompositeAlert)" class="composite-chain-card">
          <div class="suite-section-head">
            <span class="suite-tag">病理生理链</span>
            <span class="suite-code">{{ compositeChainLabel(compositeClinicalChain(latestCompositeAlert)?.chain_type) }}</span>
          </div>
          <div class="chain-summary">{{ compositeClinicalChain(latestCompositeAlert)?.summary }}</div>
          <div v-if="compositeClinicalChain(latestCompositeAlert)?.evidence?.length" class="chain-chip-row">
            <span
              v-for="(ev, evIdx) in compositeClinicalChain(latestCompositeAlert)?.evidence || []"
              :key="`headline-chain-${evIdx}`"
              class="chain-chip"
            >
              {{ ev }}
            </span>
          </div>
          <div v-if="compositeClinicalChain(latestCompositeAlert)?.suggestion" class="chain-suggestion">
            {{ compositeClinicalChain(latestCompositeAlert)?.suggestion }}
          </div>
        </section>
        <section v-if="compositeGroups(latestCompositeAlert).length" class="composite-group-section">
          <div class="suite-section-head">
            <span class="suite-tag">聚合主题</span>
            <span class="suite-code">{{ compositeGroups(latestCompositeAlert).length }} 组</span>
          </div>
          <div class="group-grid">
            <article
              v-for="(group, groupIdx) in compositeGroups(latestCompositeAlert)"
              :key="`headline-group-${group.group || groupIdx}`"
              :class="['group-card', `sev-${severityClass(group.severity)}`]"
            >
              <div class="group-card-head">
                <div>
                  <div class="group-name">{{ compositeGroupLabel(group.group) }}</div>
                  <div class="group-sub">{{ group.count || 0 }} 条关联预警</div>
                </div>
                <span :class="['group-pill', `sev-${severityClass(group.severity)}`]">
                  {{ severityText(group.severity) }}
                </span>
              </div>
              <div v-if="Array.isArray(group.alerts) && group.alerts.length" class="group-alert-list">
                <div
                  v-for="(row, rowIdx) in group.alerts.slice(0, 3)"
                  :key="`headline-group-alert-${row.rule_id || rowIdx}`"
                  class="group-alert-item"
                >
                  <span class="group-alert-name">{{ row.name || row.rule_id || '预警' }}</span>
                  <span class="group-alert-time">{{ fmtTime(row.time) || '—' }}</span>
                </div>
              </div>
            </article>
          </div>
        </section>
      </div>
    </div>
    <div v-if="organFocusGroups.length" class="organ-focus-suite">
      <div class="organ-focus-suite__head">
        <div>
          <div class="organ-focus-suite__title">器官关联告警定位</div>
          <div class="organ-focus-suite__sub">点击人体图后将自动滚动到对应器官分组，并列出 MODI 关联源告警。</div>
        </div>
        <span v-if="focusedOrganLabel" class="organ-focus-suite__pill">当前定位 {{ focusedOrganLabel }}</span>
      </div>
      <div class="organ-focus-suite__grid">
        <article
          v-for="group in organFocusGroups"
          :key="group.key"
          :data-organ-group="group.key"
          :class="['organ-focus-card', `sev-${severityClass(group.severity)}`, { 'is-active': props.focusedOrgan === group.key }]"
        >
          <div class="organ-focus-card__head">
            <div>
              <div class="organ-focus-card__name">{{ group.label }}</div>
              <div class="organ-focus-card__meta">{{ group.rows.length }} 条关联源告警</div>
            </div>
            <span :class="['group-pill', `sev-${severityClass(group.severity)}`]">{{ severityText(group.severity) }}</span>
          </div>
          <div class="organ-focus-card__list">
            <button
              v-for="(row, rowIdx) in group.rows.slice(0, 4)"
              :key="`${group.key}-${row.alert_type || rowIdx}`"
              type="button"
              class="organ-focus-card__item"
              @click="scrollToAlertCard(row)"
            >
              <span>{{ sourceAlertDisplayName(row) }}</span>
              <small>{{ fmtTime(row.time) || '—' }}</small>
            </button>
          </div>
        </article>
      </div>
    </div>
    <div v-if="latestWeaningStatus?.weaning?.has_assessment || latestWeaningAlert || latestPostExtubationAlert" class="weaning-brief">
      <div class="weaning-brief-head">
        <div>
          <div class="weaning-brief-title">脱机风险评分卡</div>
          <div class="weaning-brief-sub">
            {{ fmtTime(latestWeaningStatus?.weaning?.updated_at || latestWeaningAlert?.created_at) || '暂无更新时间' }}
          </div>
        </div>
        <div :class="['weaning-brief-score', `sev-${weaningSeverity(latestWeaningStatus?.weaning?.risk_level)}`]">
          <span>{{ weaningRiskLabel(latestWeaningStatus?.weaning?.risk_level) }}</span>
          <strong>{{ latestWeaningStatus?.weaning?.risk_score ?? latestWeaningAlert?.value ?? '—' }}</strong>
        </div>
      </div>
      <div class="weaning-brief-main">
        {{ latestWeaningStatus?.weaning?.recommendation || explanationSummary(latestWeaningAlert) || '暂无脱机评估建议' }}
      </div>
      <div class="weaning-chip-row">
        <span class="weaning-chip">P/F {{ latestWeaningStatus?.weaning?.pf_ratio ?? latestWeaningAlert?.extra?.pf_ratio ?? '—' }}</span>
        <span class="weaning-chip">RSBI {{ latestWeaningStatus?.weaning?.rsbi ?? latestWeaningAlert?.extra?.rsbi ?? '—' }}</span>
        <span class="weaning-chip">FiO₂ {{ latestWeaningStatus?.weaning?.fio2 ?? latestWeaningAlert?.extra?.fio2 ?? '—' }}</span>
        <span class="weaning-chip">PEEP {{ latestWeaningStatus?.weaning?.peep ?? latestWeaningAlert?.extra?.peep ?? '—' }}</span>
        <span class="weaning-chip">MAP {{ latestWeaningStatus?.weaning?.map ?? latestWeaningAlert?.extra?.map ?? '—' }}</span>
      </div>
      <div v-if="weaningEvidence(latestWeaningStatus?.weaning).length" class="weaning-evidence-row">
        <span
          v-for="(ev, idx) in weaningEvidence(latestWeaningStatus?.weaning)"
          :key="`weaning-brief-ev-${idx}`"
          class="weaning-evidence-chip"
        >
          {{ ev }}
        </span>
      </div>
      <div class="weaning-sbt-row">
        <span :class="['weaning-sbt-pill', `is-${String(latestWeaningStatus?.sbt?.result || 'none').toLowerCase()}`]">
          {{ latestWeaningStatus?.sbt?.label || '暂无SBT记录' }}
        </span>
        <span class="weaning-sbt-meta">SBT {{ fmtTime(latestWeaningStatus?.sbt?.trial_time) || '—' }}</span>
        <span v-if="latestWeaningStatus?.sbt?.rsbi != null" class="weaning-sbt-meta">RSBI {{ latestWeaningStatus?.sbt?.rsbi }}</span>
        <span v-if="latestPostExtubationAlert" class="weaning-sbt-meta weaning-sbt-meta--risk">
          拔管后风险 {{ fmtTime(latestPostExtubationAlert?.created_at) || '—' }}
        </span>
      </div>
    </div>
    <div v-if="alerts[0] && itemReasoning(alerts[0])" class="reasoning-brief">
      <div class="reasoning-brief-head">
        <div>
          <div class="reasoning-brief-title">AI 归因摘要</div>
          <div class="reasoning-brief-sub">
            {{ fmtTime(itemReasoning(alerts[0])?.generated_at || alerts[0]?.reasoning_updated_at || alerts[0]?.created_at) || '时间未知' }}
            · 关联 {{ itemReasoning(alerts[0])?.source_alert_count || 0 }} 条活跃报警
          </div>
        </div>
        <div :class="['reasoning-brief-confidence', `is-${reasoningConfidenceLevel(itemReasoning(alerts[0]))}`]">
          <span>置信度</span>
          <strong>{{ reasoningConfidenceText(itemReasoning(alerts[0])) }}</strong>
        </div>
      </div>
      <div class="reasoning-brief-main">{{ itemReasoning(alerts[0])?.root_cause_summary }}</div>
      <div v-if="itemReasoning(alerts[0])?.most_urgent_action" class="reasoning-brief-urgent">
        最紧急 action：{{ itemReasoning(alerts[0])?.most_urgent_action }}
      </div>
      <div v-if="reasoningGroups(alerts[0]).length" class="reasoning-chip-row">
        <span
          v-for="(group, groupIdx) in reasoningGroups(alerts[0])"
          :key="`reasoning-top-group-${groupIdx}`"
          class="reasoning-chip"
        >
          {{ group.label }}<span v-if="group.alert_ids?.length"> · {{ group.alert_ids.length }} 条</span>
        </span>
      </div>
    </div>
    <div v-if="personalizedThresholdRecord || personalizedThresholdLoading || personalizedThresholdError" class="threshold-brief">
      <div class="threshold-brief-head">
        <div>
          <div class="threshold-brief-title">个性化报警阈值建议</div>
          <div class="threshold-brief-sub">
            {{ fmtTime(personalizedThresholdRecord?.calc_time || personalizedThresholdRecord?.updated_at) || '暂无生成时间' }}
            <span v-if="personalizedThresholdHistory?.length"> · 历史 {{ personalizedThresholdHistory.length }} 条</span>
          </div>
        </div>
        <div :class="['threshold-status-pill', `is-${thresholdReviewStatus(personalizedThresholdRecord?.status)}`]">
          {{ thresholdStatusText(personalizedThresholdRecord?.status) }}
        </div>
      </div>
      <div v-if="personalizedThresholdLoading" class="threshold-empty">正在加载个性化阈值建议...</div>
      <div v-else-if="personalizedThresholdError" class="threshold-empty threshold-empty--error">{{ personalizedThresholdError }}</div>
      <template v-else-if="personalizedThresholdRecord">
        <div class="threshold-brief-main">
          {{ personalizedThresholdRecord?.reasoning?.overall_reasoning || '暂无整体推理摘要' }}
        </div>
        <div class="threshold-meta-row">
          <span class="threshold-meta-chip">置信度 {{ thresholdConfidenceText(personalizedThresholdRecord) }}</span>
          <span class="threshold-meta-chip">审核优先级 {{ personalizedThresholdRecord?.reasoning?.review_priority || 'medium' }}</span>
          <span v-if="personalizedThresholdRecord?.reviewer" class="threshold-meta-chip">审核人 {{ personalizedThresholdRecord.reviewer }}</span>
        </div>
        <div v-if="personalizedThresholdApprovedRecord" class="threshold-approved-note">
          <strong>当前生效版本</strong>
          <span>{{ fmtTime(personalizedThresholdApprovedRecord?.reviewed_at || personalizedThresholdApprovedRecord?.updated_at || personalizedThresholdApprovedRecord?.calc_time) || '时间未知' }}</span>
          <span v-if="personalizedThresholdApprovedRecord?._id !== personalizedThresholdRecord?._id">· 与当前展示版本不同</span>
        </div>
        <div v-if="thresholdRows(personalizedThresholdRecord).length" class="threshold-grid">
          <article v-for="row in thresholdRows(personalizedThresholdRecord)" :key="row.key" class="threshold-card">
            <div class="threshold-card-head">
              <span class="threshold-card-name">{{ row.label }}</span>
              <span class="threshold-card-band">{{ row.band }}</span>
            </div>
            <div class="threshold-card-main">
              <span>低警 {{ row.lowWarning }}<em v-if="row.lowWarningDelta"> {{ row.lowWarningDelta }}</em></span>
              <span>低危 {{ row.lowCritical }}<em v-if="row.lowCriticalDelta"> {{ row.lowCriticalDelta }}</em></span>
              <span>高警 {{ row.highWarning }}<em v-if="row.highWarningDelta"> {{ row.highWarningDelta }}</em></span>
              <span>高危 {{ row.highCritical }}<em v-if="row.highCriticalDelta"> {{ row.highCriticalDelta }}</em></span>
            </div>
            <div v-if="row.reasoning" class="threshold-card-reason">{{ thresholdReasoningText(row.reasoning) }}</div>
          </article>
        </div>
        <div v-if="personalizedThresholdRecord?.reasoning?.rejected_thresholds && Object.keys(personalizedThresholdRecord.reasoning.rejected_thresholds).length" class="threshold-footnote">
          存在部分参数因逻辑不一致被系统拒绝写入。
        </div>
        <div v-if="personalizedThresholdRecord?.status === 'pending_review'" class="threshold-action-row">
          <a-button size="small" type="primary" :loading="personalizedThresholdReviewing" @click="reviewPersonalizedThreshold(personalizedThresholdRecord, 'approved')">
            批准
          </a-button>
          <a-button size="small" danger ghost :loading="personalizedThresholdReviewing" @click="reviewPersonalizedThreshold(personalizedThresholdRecord, 'rejected')">
            拒绝
          </a-button>
        </div>
        <div v-else-if="personalizedThresholdRecord?.review_comment" class="threshold-footnote">
          审核备注：{{ personalizedThresholdRecord.review_comment }}
        </div>
      </template>
    </div>
    <div v-if="alerts.length" class="alert-feed">
      <article
        v-for="(item, idx) in alerts"
        :key="item._id || item.created_at || idx"
        :data-alert-type="String(item?.alert_type || '')"
        :data-alert-name="String(item?.name || item?.rule_id || '')"
        :data-alert-created-at="String(item?.created_at || '')"
        :data-alert-card="alertCardKey(item, idx)"
        :class="['alert-card', `sev-${normalizeSeverity(item.severity)}`]"
      >
        <div class="alert-rail">
          <span class="alert-time">{{ fmtTime(item.created_at) || '时间未知' }}</span>
          <span :class="['alert-dot', `sev-${normalizeSeverity(item.severity)}`]"></span>
          <span v-if="idx < alerts.length - 1" class="alert-line"></span>
        </div>
        <div :class="['alert-body', { 'alert-body--rescue': isRescueRiskAlert(item) }]">
          <div class="alert-head">
            <div class="alert-title-row">
              <h4 class="alert-title">{{ item.name || item.rule_id || '预警' }}</h4>
              <span :class="['alert-pill', `sev-${normalizeSeverity(item.severity)}`]">
                {{ alertSeverityText(item.severity) }}
              </span>
            </div>
            <div class="alert-value">{{ formatAlertValue(item) }}</div>
          </div>
          <div class="alert-terminal-line">
            <span class="terminal-tag">事件</span>
            <span class="terminal-id">{{ eventCodeText(item) }}</span>
          </div>
          <div v-if="isPostExtubationAlert(item)" class="post-extub-panel">
            <div class="post-extub-head">
              <span class="post-extub-tag">再插管风险卡</span>
              <span :class="['post-extub-pill', `sev-${normalizeSeverity(item.severity)}`]">{{ alertSeverityText(item.severity) }}</span>
            </div>
            <div class="post-extub-main">{{ postExtubationTitle(item) }}</div>
            <div class="post-extub-chip-row">
              <span class="post-extub-chip">RR {{ postExtubationMetric(item, 'rr') }}</span>
              <span class="post-extub-chip">SpO₂ {{ postExtubationMetric(item, 'spo2', '%') }}</span>
              <span class="post-extub-chip">拔管后 {{ postExtubationHours(item) }}</span>
              <span v-if="postExtubationAccessory(item)" class="post-extub-chip post-extub-chip--warn">辅助呼吸肌动用</span>
            </div>
          </div>
          <div v-if="hasExplanation(item)" :class="['alert-explanation', { 'alert-explanation--rescue': isRescueRiskAlert(item) }]">
            <div v-if="isRescueRiskAlert(item)" class="rescue-headline">
              <span class="rescue-headline-tag">抢救期风险卡</span>
              <span class="rescue-headline-main">{{ rescuePanelTitle(item) }}</span>
            </div>
            <span class="explanation-tag">{{ isRescueRiskAlert(item) ? '三段式评估' : '临床推理' }}</span>
            <div :class="['explanation-grid', { 'explanation-grid--rescue': isRescueRiskAlert(item) }]">
              <div v-if="explanationSummary(item)" :class="['explanation-block', { 'explanation-block--summary': isRescueRiskAlert(item) }]">
                <div class="explanation-label">{{ isRescueRiskAlert(item) ? '当前判断' : '摘要' }}</div>
                <div :class="['explanation-text', { 'explanation-text--summary': isRescueRiskAlert(item) }]">{{ prettyClinicalText(explanationSummary(item)) }}</div>
              </div>
              <div v-if="explanationEvidence(item).length" :class="['explanation-block', { 'explanation-block--evidence': isRescueRiskAlert(item) }]">
                <div class="explanation-label">{{ isRescueRiskAlert(item) ? '主要依据' : '证据' }}</div>
                <div v-if="isRescueRiskAlert(item)" class="rescue-evidence-row">
                  <span
                    v-for="(ev, evIdx) in rescueEvidenceChips(item)"
                    :key="`ev-chip-${evIdx}`"
                    class="rescue-evidence-chip"
                  >
                    {{ ev }}
                  </span>
                </div>
                <ul v-else class="explanation-list">
                  <li v-for="(ev, evIdx) in explanationEvidence(item)" :key="`ev-${evIdx}`">
                    {{ ev }}
                  </li>
                </ul>
              </div>
              <div v-if="explanationSuggestion(item)" :class="['explanation-block', { 'explanation-block--suggestion': isRescueRiskAlert(item) }]">
                <div class="explanation-label">{{ isRescueRiskAlert(item) ? '处置建议' : '建议' }}</div>
                <div :class="['explanation-text', { 'explanation-text--suggestion': isRescueRiskAlert(item) }]">{{ prettyClinicalText(explanationSuggestion(item)) }}</div>
              </div>
            </div>
          </div>
          <div v-if="itemReasoning(item) && (idx === 0 || itemReasoning(item)?.cluster_signature !== itemReasoning(alerts[idx - 1])?.cluster_signature)" class="reasoning-card">
            <div class="reasoning-card-head">
              <div>
                <span class="reasoning-tag">AI 归因摘要</span>
                <div class="reasoning-summary">{{ itemReasoning(item)?.root_cause_summary }}</div>
              </div>
              <span :class="['reasoning-confidence-pill', `is-${reasoningConfidenceLevel(itemReasoning(item))}`]">
                {{ reasoningConfidenceText(itemReasoning(item)) }}
              </span>
            </div>
            <div v-if="itemReasoning(item)?.most_urgent_action" class="reasoning-urgent">
              <strong>最紧急 action</strong> {{ itemReasoning(item)?.most_urgent_action }}
            </div>
            <div v-if="reasoningActions(item).length" class="reasoning-section">
              <div class="reasoning-section-title">优先级排序</div>
              <div
                v-for="(action, actionIdx) in reasoningActions(item)"
                :key="`reasoning-action-${idx}-${actionIdx}`"
                class="reasoning-action"
              >
                <span class="reasoning-rank">#{{ action.rank || actionIdx + 1 }}</span>
                <div class="reasoning-action-body">
                  <div class="reasoning-action-main">{{ action.action }}</div>
                  <div v-if="action.why" class="reasoning-action-why">{{ action.why }}</div>
                </div>
              </div>
            </div>
            <div v-if="reasoningGroups(item).length" class="reasoning-section">
              <div class="reasoning-section-title">建议合并展示</div>
              <div class="reasoning-group-grid">
                <article
                  v-for="(group, groupIdx) in reasoningGroups(item)"
                  :key="`reasoning-group-${idx}-${groupIdx}`"
                  class="reasoning-group-card"
                >
                  <div class="reasoning-group-label">{{ group.label }}</div>
                  <div v-if="group.reason" class="reasoning-group-reason">{{ group.reason }}</div>
                  <div class="reasoning-group-meta">{{ group.alert_ids?.length || 0 }} 条关联报警</div>
                </article>
              </div>
            </div>
            <div v-if="reasoningSafetyIssues(item).length || reasoningHallucinations(item).length" class="reasoning-section">
              <div class="reasoning-section-title">质量护栏</div>
              <ul class="reasoning-list">
                <li v-for="(issue, issueIdx) in reasoningSafetyIssues(item)" :key="`reasoning-safe-${idx}-${issueIdx}`">
                  {{ issue.message || issue.type || '存在安全校验问题' }}
                </li>
                <li v-for="(flag, flagIdx) in reasoningHallucinations(item)" :key="`reasoning-hall-${idx}-${flagIdx}`">
                  {{ flag.metric || '指标' }}: 输出 {{ flag.claimed }} / 实测 {{ flag.observed }}
                </li>
              </ul>
            </div>
          </div>
          <div v-if="hasContextSnapshot(item)" class="context-snapshot">
            <div class="context-head">
              <span class="context-tag">{{ isRescueRiskAlert(item) ? '风险快照' : '微型快照' }}</span>
              <span class="context-time">{{ fmtTime(contextSnapshot(item)?.snapshot_time) || '时间未知' }}</span>
            </div>
            <div v-if="snapshotVitals(item).length" class="context-row">
              <span class="context-row-label">生命体征</span>
              <div class="context-chip-row">
                <span
                  v-for="(chip, chipIdx) in snapshotVitals(item)"
                  :key="`ctx-vital-${idx}-${chipIdx}`"
                  class="context-chip"
                >
                  <span class="context-chip-label">{{ chip.label }}</span>
                  <strong class="context-chip-value">{{ chip.value }}</strong>
                </span>
              </div>
            </div>
            <div v-if="snapshotLabs(item).length" class="context-row">
              <span class="context-row-label">关键检验</span>
              <div class="context-chip-row">
                <span
                  v-for="(chip, chipIdx) in snapshotLabs(item)"
                  :key="`ctx-lab-${idx}-${chipIdx}`"
                  class="context-chip context-chip--lab"
                >
                  <span class="context-chip-label">{{ chip.label }}</span>
                  <strong class="context-chip-value">{{ chip.value }}</strong>
                </span>
              </div>
            </div>
            <div v-if="snapshotVasopressors(item).length" class="context-row">
              <span class="context-row-label">血管活性药</span>
              <div class="context-badge-row">
                <span
                  v-for="(badge, badgeIdx) in snapshotVasopressors(item)"
                  :key="`ctx-vaso-${idx}-${badgeIdx}`"
                  class="context-badge"
                >
                  <span class="context-badge-name">{{ badge.drug }}</span>
                  <span class="context-badge-dose">{{ badge.dose }}</span>
                </span>
              </div>
            </div>
          </div>
          <div v-if="compositeClinicalChain(item) || compositeGroups(item).length" :class="['composite-suite', { 'composite-suite--rescue': isRescueRiskAlert(item) }]">
            <section v-if="compositeClinicalChain(item)" class="composite-chain-card">
              <div class="suite-section-head">
                <span class="suite-tag">{{ isRescueRiskAlert(item) ? '病理生理链' : '临床链' }}</span>
                <span class="suite-code">{{ compositeChainLabel(compositeClinicalChain(item)?.chain_type) }}</span>
              </div>
              <div class="chain-summary">{{ compositeClinicalChain(item)?.summary }}</div>
              <div v-if="compositeClinicalChain(item)?.evidence?.length" class="chain-chip-row">
                <span
                  v-for="(ev, evIdx) in compositeClinicalChain(item)?.evidence || []"
                  :key="`chain-${idx}-${evIdx}`"
                  class="chain-chip"
                >
                  {{ ev }}
                </span>
              </div>
              <div v-if="compositeClinicalChain(item)?.suggestion" class="chain-suggestion">
                {{ compositeClinicalChain(item)?.suggestion }}
              </div>
            </section>
            <section v-if="compositeGroups(item).length" class="composite-group-section">
              <div class="suite-section-head">
                <span class="suite-tag">{{ isRescueRiskAlert(item) ? '聚合主题' : '主题聚合' }}</span>
                <span class="suite-code">{{ compositeGroups(item).length }} 组</span>
              </div>
              <div class="group-grid">
                <article
                  v-for="(group, groupIdx) in compositeGroups(item)"
                  :key="`group-${idx}-${group.group || groupIdx}`"
                  :class="['group-card', `sev-${severityClass(group.severity)}`]"
                >
                  <div class="group-card-head">
                    <div>
                      <div class="group-name">{{ compositeGroupLabel(group.group) }}</div>
                      <div class="group-sub">{{ group.count || 0 }} 条关联预警</div>
                    </div>
                    <span :class="['group-pill', `sev-${severityClass(group.severity)}`]">
                      {{ severityText(group.severity) }}
                    </span>
                  </div>
                  <div v-if="Array.isArray(group.alerts) && group.alerts.length" class="group-alert-list">
                    <div
                      v-for="(row, rowIdx) in group.alerts.slice(0, 3)"
                      :key="`group-alert-${idx}-${row.rule_id || rowIdx}`"
                      class="group-alert-item"
                    >
                      <span class="group-alert-name">{{ row.name || row.rule_id || '预警' }}</span>
                      <span class="group-alert-time">{{ fmtTime(row.time) || '—' }}</span>
                    </div>
                  </div>
                </article>
              </div>
            </section>
          </div>
          <div class="alert-meta">
            <span v-if="item.alert_type">{{ alertTypeText(item.alert_type) }}</span>
            <span v-if="item.category">{{ alertCategoryText(item.category) }}</span>
            <span v-if="item.parameter">{{ parameterText(item.parameter) }}</span>
          </div>
          <div v-if="!isAiRiskAlert(item)" class="alert-action-row">
            <span v-if="item.actionability_score != null" class="alert-action-chip">
              可行动性 {{ item.actionability_score }}
            </span>
            <span v-if="item.acknowledged_at" class="alert-action-chip alert-action-chip--ok">
              已确认 {{ fmtTime(item.acknowledged_at) || '刚刚' }}
              <span v-if="item.ack_disposition" class="ack-disposition-badge">
                {{ ackDispositionText(item.ack_disposition) }}
              </span>
            </span>
            <div v-else class="ack-disposition-bar">
              <a-button size="small" type="primary" ghost @click="acknowledgeAlert(item, 'resolved')">✅ 已处理</a-button>
              <a-button size="small" ghost @click="acknowledgeAlert(item, 'watching')">👁 观察中</a-button>
              <a-button size="small" ghost @click="acknowledgeAlert(item, 'false_positive')">❌ 误报</a-button>
              <a-button size="small" danger ghost @click="acknowledgeAlert(item, 'escalate')">📞 通知医生</a-button>
            </div>
          </div>
          <div
            v-if="item.parameter || item.condition?.operator || item.condition?.threshold"
            class="alert-rule"
          >
            {{ parameterText(item.parameter || '参数') }}
            {{ item.condition?.operator || '' }}
            {{ item.condition?.threshold || '' }}
          </div>
          <div v-if="alertDetailFields(item).length" class="alert-detail-grid">
            <div v-for="f in alertDetailFields(item)" :key="f.label" class="alert-detail-item">
              <span class="detail-label">{{ f.label }}</span>
              <span class="detail-value">{{ f.value ?? '—' }}</span>
            </div>
          </div>
          <div v-if="isAiRiskAlert(item)" class="ai-risk-panel">
            <div class="ai-risk-head">
              <div :class="['ai-risk-summary', aiConfidenceClass(aiRiskConfidenceLevel(item))]">
                <strong>{{ item.extra?.primary_risk || item.name || 'AI综合风险' }}</strong>
                <span>风险等级 {{ aiRiskLevelText(item.extra?.risk_level || item.condition?.risk_level || item.value) }}</span>
                <span v-if="item.ai_feedback?.outcome">反馈 {{ feedbackOutcomeText(item.ai_feedback.outcome) }}</span>
              </div>
              <div class="ai-risk-feedback">
                <a-button size="small" @click="submitAiFeedback(item, 'confirmed')">采纳</a-button>
                <a-button size="small" @click="submitAiFeedback(item, 'dismissed')">忽略</a-button>
                <a-button size="small" danger ghost @click="submitAiFeedback(item, 'inaccurate')">不准确</a-button>
              </div>
            </div>
            <div v-if="aiRiskOrganRows(item).length" class="ai-risk-organ-grid">
              <div
                v-for="row in aiRiskOrganRows(item)"
                :key="row.key"
                :class="['ai-risk-organ', aiConfidenceClass(row.confidence_level)]"
              >
                <div class="ai-risk-organ-top">
                  <span class="ai-risk-organ-name">{{ row.label }}</span>
                  <span class="ai-risk-organ-status">{{ row.status_text }}</span>
                </div>
                <div class="ai-risk-organ-evidence">{{ row.evidence || '未见证据' }}</div>
                <div class="ai-risk-organ-conf">置信度 {{ row.confidence_level }}</div>
              </div>
            </div>
            <div v-if="aiRiskValidationIssues(item).length" class="ai-risk-section">
              <div class="ai-risk-section-title">安全校验</div>
              <ul class="ai-risk-list ai-risk-list-warning">
                <li v-for="(issue, issueIdx) in aiRiskValidationIssues(item)" :key="issueIdx">
                  {{ issue.message || issue.type || '存在校验问题' }}
                </li>
              </ul>
            </div>
            <div v-if="aiRiskHallucinations(item).length" class="ai-risk-section">
              <div class="ai-risk-section-title">幻觉检测</div>
              <ul class="ai-risk-list ai-risk-list-hallucination">
                <li
                  v-for="(flag, flagIdx) in aiRiskHallucinations(item)"
                  :key="flagIdx"
                  :class="['hallucination-pill', `hallucination-${flag.level || 'warning'}`]"
                >
                  {{ flag.metric || '指标' }}: 输出 {{ flag.claimed }} / 实测 {{ flag.observed }}
                </li>
              </ul>
            </div>
            <div v-if="aiRiskEvidenceList(item).length" class="ai-risk-section">
              <div class="ai-risk-section-title">证据脚注</div>
              <ol class="ai-risk-evidence-list">
                <li v-for="(evidence, evidenceIdx) in aiRiskEvidenceList(item)" :key="evidence.chunk_id || evidenceIdx">
                  <a-popover placement="topLeft" overlay-class-name="icu-monitor-popover">
                    <template #content>
                      <div class="ai-evidence-popover">
                        <div><strong>{{ evidence.source || '指南证据' }}</strong></div>
                        <div v-if="evidence.recommendation">{{ evidence.recommendation }}</div>
                        <div class="ai-evidence-quote">{{ evidence.quote || '暂无原文片段' }}</div>
                      </div>
                    </template>
                    <a class="ai-evidence-link" @click.prevent="openEvidence(evidence)">
                      [{{ evidenceIdx + 1 }}] {{ evidence.source || '未知来源' }}<span v-if="evidence.recommendation"> · {{ evidence.recommendation }}</span>
                    </a>
                  </a-popover>
                </li>
              </ol>
            </div>
            <div v-if="aiRiskExplainabilityRows(item).length" class="ai-risk-section">
              <div class="ai-risk-section-title">归因解释</div>
              <ul class="ai-risk-list">
                <li v-for="(factor, factorIdx) in aiRiskExplainabilityRows(item)" :key="factorIdx">
                  {{ factor.factor }}<span v-if="factor.weight != null"> ({{ Math.round(Number(factor.weight || 0) * 100) }}%)</span>
                  <span v-if="factor.evidence">：{{ factor.evidence }}</span>
                </li>
              </ul>
            </div>
          </div>
          <div v-else-if="item.extra && !alertDetailFields(item).length && fallbackExtraRows(item).length" class="alert-detail-grid">
            <div v-for="(f, fIdx) in fallbackExtraRows(item)" :key="`${f.label}-${fIdx}`" class="alert-detail-item">
              <span class="detail-label">{{ f.label }}</span>
              <span class="detail-value">{{ f.value ?? '—' }}</span>
            </div>
          </div>
          <div v-else-if="item.extra && !alertDetailFields(item).length" class="alert-extra alert-extra--muted">
            附加信息已结构化存储，当前类型暂无专用展示模板。
          </div>
        </div>
      </article>
    </div>
    <div v-if="!alerts.length" class="tab-empty">暂无预警记录</div>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, toRefs, watch } from 'vue'
import { Button as AButton, Popover as APopover } from 'ant-design-vue'
import { formatAlertTypeLabel, formatCompositeChainLabel, formatCompositeGroupLabel, formatScenarioGroupLabel } from '../../utils/displayLabels'
import { BODY_MAP_ORGAN_LABELS, BODY_MAP_ORGAN_ORDER, normalizeBodyMapOrganKey } from '../../utils/bodyMap'

const props = defineProps<{
  latestCompositeAlert: any
  latestCompositeWindowHours: any
  latestCompositeModi: any
  latestCompositeOrganCount: any
  latestCompositeInvolvedText: any
  compositeRadarOption: any
  latestWeaningAlert: any
  latestWeaningStatus: any
  latestPostExtubationAlert: any
  personalizedThresholdRecord: any
  personalizedThresholdHistory: any[]
  personalizedThresholdApprovedRecord: any
  personalizedThresholdLoading: boolean
  personalizedThresholdError: string
  personalizedThresholdReviewing: boolean
  reviewPersonalizedThreshold: (record: any, status: 'approved' | 'rejected', meta?: { reviewer?: string; review_comment?: string }) => void | Promise<void>
  alerts: any[]
  fmtTime: (v: any) => string
  normalizeSeverity: (v: any) => string
  alertSeverityText: (v: any) => string
  formatAlertValue: (item: any) => string
  alertTypeText: (v: any) => string
  alertCategoryText: (v: any) => string
  alertDetailFields: (item: any) => any[]
  isAiRiskAlert: (item: any) => boolean
  aiConfidenceClass: (v: any) => string
  aiRiskConfidenceLevel: (item: any) => string
  aiRiskLevelText: (v: any) => string
  feedbackOutcomeText: (v: any) => string
  submitAiFeedback: (item: any, outcome: 'confirmed' | 'dismissed' | 'inaccurate') => void | Promise<void>
  aiRiskOrganRows: (item: any) => any[]
  aiRiskValidationIssues: (item: any) => any[]
  aiRiskHallucinations: (item: any) => any[]
  aiRiskEvidenceList: (item: any) => any[]
  openEvidence: (evidence: any) => void
  aiRiskExplainabilityRows: (item: any) => any[]
  formatAlertExtra: (extra: any) => string
  acknowledgeAlert: (item: any, disposition?: string) => void | Promise<void>
  focusedOrgan?: string
  focusedAlertTypes?: string[]
}>()

const {
  latestCompositeAlert,
  latestCompositeWindowHours,
  latestCompositeModi,
  latestCompositeOrganCount,
  latestCompositeInvolvedText,
  compositeRadarOption,
  latestWeaningAlert,
  latestWeaningStatus,
  latestPostExtubationAlert,
  personalizedThresholdRecord,
  personalizedThresholdHistory,
  personalizedThresholdApprovedRecord,
  personalizedThresholdLoading,
  personalizedThresholdError,
  personalizedThresholdReviewing,
  alerts,
} = toRefs(props)

const {
  reviewPersonalizedThreshold,
  fmtTime,
  normalizeSeverity,
  alertSeverityText,
  formatAlertValue,
  alertTypeText,
  alertCategoryText,
  alertDetailFields,
  isAiRiskAlert,
  aiConfidenceClass,
  aiRiskConfidenceLevel,
  aiRiskLevelText,
  feedbackOutcomeText,
  submitAiFeedback,
  aiRiskOrganRows,
  aiRiskValidationIssues,
  aiRiskHallucinations,
  aiRiskEvidenceList,
  openEvidence,
  aiRiskExplainabilityRows,
  acknowledgeAlert,
} = props

const CODE_LABELS: Record<string, string> = {
  extended_scenarios: '扩展场景',
  hypertensive_emergency: '高血压急症',
  seizure_prophylaxis: '癫痫预防评估',
  hemodynamic_instability: '血流动力学不稳定',
  post_neurosurgery: '神经外科术后',
  actionability: '可行动性',
  route_targets: '路由对象',
  antiepileptic_detected: '抗癫痫药已覆盖',
  nurse: '护士',
  doctor: '医生',
  yes: '是',
  no: '否',
  true: '是',
  false: '否',
}

const EXTRA_FIELD_LABELS: Record<string, string> = {
  scenario_group: '场景组',
  scenario: '场景',
  route_targets: '路由对象',
  actionability: '可行动性',
  antiepileptic_detected: '抗癫痫药已覆盖',
}

function codeText(raw: any): string {
  const text = String(raw || '').trim()
  if (!text) return ''
  const key = text.toLowerCase()
  if (key.startsWith('ext_')) {
    const inner = codeText(key.slice(4))
    return inner ? `扩展场景 · ${inner}` : '扩展场景'
  }
  if (CODE_LABELS[key]) return CODE_LABELS[key]

  const alertLabel = formatAlertTypeLabel(key)
  if (alertLabel && alertLabel !== key.replace(/_/g, ' ')) return alertLabel
  const scenarioGroupLabel = formatScenarioGroupLabel(key)
  if (scenarioGroupLabel && scenarioGroupLabel !== key.replace(/_/g, ' ')) return scenarioGroupLabel

  return text.replace(/_/g, ' ')
}

function extraFieldLabel(raw: any) {
  const key = String(raw || '').trim().toLowerCase()
  if (!key) return ''
  return EXTRA_FIELD_LABELS[key] || codeText(key)
}

function eventCodeText(item: any) {
  return codeText(item?.rule_id || item?.alert_type || item?.category || 'monitor.rule')
}

function parameterText(raw: any) {
  return codeText(raw)
}

function normalizeExplanationObject(exp: any) {
  if (!exp || typeof exp !== 'object') {
    return {
      summary: '',
      evidence: [] as string[],
      suggestion: '',
    }
  }

  const evidence = new Set<string>()
  const checks = exp?.checks && typeof exp.checks === 'object' ? exp.checks : {}
  const context = exp?.context && typeof exp.context === 'object' ? exp.context : {}
  const transferSignal = context?.transfer_signal && typeof context.transfer_signal === 'object'
    ? context.transfer_signal
    : (exp?.transfer_signal && typeof exp.transfer_signal === 'object' ? exp.transfer_signal : {})

  if (Array.isArray(exp.evidence)) {
    exp.evidence.forEach((item: any) => {
      const text = String(item || '').trim()
      if (text) evidence.add(text)
    })
  }

  if (typeof transferSignal?.evidence === 'string' && transferSignal.evidence.trim()) {
    evidence.add(String(transferSignal.evidence).trim())
  }

  Object.entries(checks).forEach(([key, value]) => {
    if (value === true) evidence.add(`${extraFieldLabel(key)}：是`)
    if (value === false) evidence.add(`${extraFieldLabel(key)}：否`)
  })

  const summary = [exp?.summary, exp?.text, exp?.label]
    .find((item: any) => typeof item === 'string' && item.trim()) || ''

  const suggestion = [exp?.suggestion, exp?.action, exp?.recommendation, exp?.advice]
    .find((item: any) => typeof item === 'string' && item.trim()) || ''

  return {
    summary: String(summary || ''),
    evidence: Array.from(evidence).slice(0, 6),
    suggestion: String(suggestion || ''),
  }
}

function parseExplanationPayload(raw: any) {
  if (raw && typeof raw === 'object') return normalizeExplanationObject(raw)
  const text = String(raw || '').trim()
  if (!text) return null
  try {
    return normalizeExplanationObject(JSON.parse(text))
  } catch {
    return null
  }
}

function explanationPayload(alert: any) {
  const exp = alert?.explanation
  const parsedExp = parseExplanationPayload(exp)
  if (parsedExp) return parsedExp
  if (typeof exp === 'string') {
    return {
      summary: exp,
      evidence: [] as string[],
      suggestion: '',
    }
  }
  if (exp && typeof exp === 'object') {
    return normalizeExplanationObject(exp)
  }
  const parsedText = parseExplanationPayload(alert?.explanation_text)
  if (parsedText) return parsedText
  return {
    summary: typeof alert?.explanation_text === 'string' ? alert.explanation_text : '',
    evidence: [] as string[],
    suggestion: '',
  }
}

function hasExplanation(alert: any) {
  const p = explanationPayload(alert)
  return !!(p.summary || p.evidence.length || p.suggestion)
}

function explanationSummary(alert: any) {
  return explanationPayload(alert).summary || ''
}

function explanationEvidence(alert: any) {
  return explanationPayload(alert).evidence || []
}

function explanationSuggestion(alert: any) {
  return explanationPayload(alert).suggestion || ''
}


function prettyClinicalText(raw: any) {
  const text = String(raw || '').trim()
  if (!text) return ''
  return text
    .replace(/\\s+/g, ' ')
    .replace(/([；;。])(?=\\S)/g, ' ')
    .replace(/，(?=\\S{12,})/g, '， ')
    .replace(/\\s+([，。；：])/g, '')
    .trim()
}

function itemReasoning(alert: any) {
  const payload = alert?.reasoning
  return payload && typeof payload === 'object' ? payload : null
}

function reasoningActions(alert: any) {
  const rows = itemReasoning(alert)?.priority_actions
  return Array.isArray(rows) ? rows.filter((x: any) => x && typeof x === 'object') : []
}

function reasoningGroups(alert: any) {
  const rows = itemReasoning(alert)?.merge_display_plan?.groups
  return Array.isArray(rows) ? rows.filter((x: any) => x && typeof x === 'object') : []
}

function reasoningSafetyIssues(alert: any) {
  const rows = itemReasoning(alert)?.safety_validation?.issues
  return Array.isArray(rows) ? rows.filter((x: any) => x && typeof x === 'object') : []
}

function reasoningHallucinations(alert: any) {
  const rows = itemReasoning(alert)?.hallucination_flags
  return Array.isArray(rows) ? rows.filter((x: any) => x && typeof x === 'object') : []
}

function thresholdReviewStatus(status: any) {
  const text = String(status || 'pending_review').toLowerCase()
  if (text === 'approved' || text === 'rejected' || text === 'pending_review') return text
  return 'pending_review'
}

function thresholdStatusText(status: any) {
  return ({ pending_review: '待审核', approved: '已批准', rejected: '已拒绝' } as Record<string, string>)[thresholdReviewStatus(status)] || '待审核'
}

function thresholdConfidenceText(record: any) {
  const value = Number(record?.reasoning?.confidence)
  if (!Number.isFinite(value)) return '—'
  return `${Math.round(value * 100)}%`
}

const thresholdDefaults: Record<string, any> = {
  map: { low_warning: 65, low_critical: 55, high_warning: 110, high_critical: 130 },
  hr: { low_warning: 50, low_critical: 40, high_warning: 120, high_critical: 150 },
  spo2: { low_warning: 90, low_critical: 85, high_warning: null, high_critical: null },
  sbp: { low_warning: 90, low_critical: 70, high_warning: 180, high_critical: 200 },
  rr: { low_warning: 10, low_critical: 6, high_warning: 30, high_critical: 40 },
  temperature: { low_warning: 35.5, low_critical: 34.0, high_warning: 38.5, high_critical: 39.5 },
}

function thresholdDeltaText(paramKey: string, key: string, value: any) {
  const current = Number(value)
  const baseline = Number(thresholdDefaults?.[paramKey]?.[key])
  if (!Number.isFinite(current) || !Number.isFinite(baseline)) return ''
  const delta = Math.round((current - baseline) * 10) / 10
  if (!delta) return '与默认一致'
  return `${delta > 0 ? '+' : ''}${delta}`
}

function thresholdRows(record: any) {
  const thresholds = record?.thresholds && typeof record.thresholds === 'object' ? record.thresholds : {}
  const labels: Record<string, string> = {
    map: 'MAP',
    hr: 'HR',
    spo2: 'SpO₂',
    sbp: 'SBP',
    rr: 'RR',
    temperature: '体温',
  }
  return Object.entries(thresholds)
    .filter(([, value]) => value && typeof value === 'object')
    .map(([key, value]: [string, any]) => ({
      key,
      label: labels[key] || key.toUpperCase(),
      band: [value.low_warning, value.high_warning].filter((x: any) => x != null).join(' ~ ') || '个体化',
      lowCritical: value.low_critical ?? '—',
      lowWarning: value.low_warning ?? '—',
      highWarning: value.high_warning ?? '—',
      highCritical: value.high_critical ?? '—',
      lowCriticalDelta: thresholdDeltaText(key, 'low_critical', value.low_critical),
      lowWarningDelta: thresholdDeltaText(key, 'low_warning', value.low_warning),
      highWarningDelta: thresholdDeltaText(key, 'high_warning', value.high_warning),
      highCriticalDelta: thresholdDeltaText(key, 'high_critical', value.high_critical),
      reasoning: value.reasoning || '',
    }))
}

function thresholdReasoningText(value: any) {
  if (value == null) return ''
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text) return ''
    try {
      const parsed = JSON.parse(text)
      return thresholdReasoningText(parsed)
    } catch {
      return text
    }
  }
  if (typeof value !== 'object') return String(value)
  const summary = [
    value?.summary,
    value?.reason,
    value?.reasoning,
    value?.explanation,
    value?.suggestion,
  ].find((x: any) => typeof x === 'string' && x.trim())
  if (summary) return String(summary).trim()
  const chunks: string[] = []
  Object.entries(value).forEach(([k, v]) => {
    const text = extraValueText(v)
    if (text) chunks.push(`${extraFieldLabel(k)}: ${text}`)
  })
  return chunks.slice(0, 3).join('；')
}

function extraValueText(value: any): string {
  if (value == null) return ''
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return ''
    return Math.abs(value - Math.round(value)) < 0.01 ? String(Math.round(value)) : String(Math.round(value * 100) / 100)
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text) return ''
    if (/^[A-Za-z0-9_]+$/.test(text)) return codeText(text)
    return text
  }
  if (Array.isArray(value)) {
    if (!value.length) return ''
    const primitive = value.filter((x) => x == null || ['string', 'number', 'boolean'].includes(typeof x))
    if (primitive.length === value.length && value.length <= 4) {
      return primitive.map((x) => extraValueText(x)).filter(Boolean).join(' / ')
    }
    return `${value.length}项`
  }
  if (typeof value === 'object') {
    if (value.value != null) {
      const raw = extraValueText(value.value)
      const unit = typeof value.unit === 'string' && value.unit.trim() ? ` ${value.unit.trim()}` : ''
      return `${raw}${unit}`.trim()
    }
    const keys = Object.keys(value)
    if (!keys.length) return ''
    return `${keys.length}项`
  }
  return String(value)
}

function snapshotMetric(snapshot: any, key: string): any {
  const row = snapshot?.[key]
  if (row && typeof row === 'object' && row.value != null) return row.value
  return row
}

function fallbackExtraRows(item: any) {
  const extra = item?.extra && typeof item.extra === 'object' ? item.extra : null
  if (!extra) return []

  const rows: Array<{ label: string; value: string }> = []
  const push = (label: string, value: any) => {
    const text = extraValueText(value)
    if (!text) return
    rows.push({ label, value: text })
  }

  const snapshot = extra?.context_snapshot && typeof extra.context_snapshot === 'object' ? extra.context_snapshot : null
  if (snapshot) {
    const vitals = snapshot?.vitals && typeof snapshot.vitals === 'object' ? snapshot.vitals : {}
    const labs = snapshot?.labs && typeof snapshot.labs === 'object' ? snapshot.labs : {}
    push('快照时间', snapshot?.snapshot_time || snapshot?.time)
    push('HR', snapshotMetric(vitals, 'hr'))
    push('RR', snapshotMetric(vitals, 'rr'))
    push('MAP', snapshotMetric(vitals, 'map'))
    push('SpO2', snapshotMetric(vitals, 'spo2'))
    push('体温', snapshotMetric(vitals, 'temp'))
    push('乳酸', snapshotMetric(labs, 'lac'))
    push('肌酐', snapshotMetric(labs, 'cr'))
    push('PCT', snapshotMetric(labs, 'pct'))
    push('血管活性药', Array.isArray(snapshot?.vasopressors) ? snapshot.vasopressors.length : null)
  }

  const hiddenKeys = new Set([
    'context_snapshot',
    'clinical_chain',
    'aggregated_groups',
    'evidence_sources',
    'organ_assessment',
    'deterioration_signals',
    'syndromes_detected',
    'recommendations',
    'explainability',
    'safety_validation',
    'hallucination_flags',
  ])

  Object.entries(extra).forEach(([key, value]) => {
    if (hiddenKeys.has(key)) return
    if (rows.length >= 12) return
    const label = extraFieldLabel(key)
    push(label, value)
  })

  return rows.slice(0, 12)
}

function ackDispositionText(value: any) {
  const map: Record<string, string> = {
    resolved: '✅ 已处理',
    watching: '👁 观察中',
    false_positive: '❌ 误报',
    escalate: '📞 通知医生',
  }
  const key = String(value || '').toLowerCase()
  return map[key] || String(value || '')
}

function reasoningConfidenceLevel(reasoning: any) {
  return String(reasoning?.confidence?.level || 'medium').toLowerCase()
}

function reasoningConfidenceText(reasoning: any) {
  const level = reasoningConfidenceLevel(reasoning)
  if (level === 'high') return '高'
  if (level === 'low') return '低'
  return '中'
}

function isRescueRiskAlert(alert: any) {
  const sev = severityClass(alert?.severity)
  if (sev !== 'high' && sev !== 'critical') return false
  const alertType = String(alert?.alert_type || '').toLowerCase()
  const ruleId = String(alert?.rule_id || '').toLowerCase()
  const category = String(alert?.category || '').toLowerCase()
  if (alertType === 'ai_risk' || category === 'ai_analysis') return false
  const rescueKeywords = [
    'shock',
    'sepsis',
    'septic',
    'cardiac_arrest',
    'cardiac',
    'pea',
    'pe_',
    'embol',
    'bleed',
    'bleeding',
    'resp',
    'hypoxia',
    'hypotension',
    'deterioration',
    'multi_organ',
    'post_extubation',
  ]
  const haystack = `${alertType} ${ruleId} ${category}`.toLowerCase()
  return rescueKeywords.some((key) => haystack.includes(key)) || hasContextSnapshot(alert) || !!compositeClinicalChain(alert)
}

function isPostExtubationAlert(alert: any) {
  const alertType = String(alert?.alert_type || '').toLowerCase()
  const ruleId = String(alert?.rule_id || '').toLowerCase()
  return alertType.includes('post_extubation') || ruleId.includes('post_extubation')
}

function rescuePanelTitle(alert: any) {
  const alertType = String(alert?.alert_type || '').toLowerCase()
  const ruleId = String(alert?.rule_id || '').toLowerCase()
  const haystack = `${alertType} ${ruleId}`
  if (haystack.includes('cardiac_arrest')) return '心脏骤停前高风险'
  if (haystack.includes('shock') || haystack.includes('sepsis') || haystack.includes('septic')) return '循环衰竭 / 脓毒症抢救风险'
  if (haystack.includes('pe_') || haystack.includes('embol')) return '急性肺栓塞高风险'
  if (haystack.includes('bleed')) return '活动性出血风险'
  if (haystack.includes('post_extubation')) return '拔管后再插管高风险'
  if (haystack.includes('resp') || haystack.includes('hypoxia')) return '呼吸衰竭风险'
  return itemTitle(alert)
}

function postExtubationExtra(alert: any) {
  return alert?.extra && typeof alert.extra === 'object' ? alert.extra : {}
}

function postExtubationMetric(alert: any, key: string, suffix = '') {
  const value = postExtubationExtra(alert)?.[key]
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return `${value}${suffix}`
  const text = Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : num.toFixed(1)
  return `${text}${suffix}`
}

function postExtubationHours(alert: any) {
  const value = postExtubationExtra(alert)?.hours_since_extubation
  if (value == null || value === '') return '—'
  const num = Number(value)
  if (!Number.isFinite(num)) return String(value)
  if (num < 1) return `${Math.max(1, Math.round(num * 60))}min`
  return `${num.toFixed(num >= 10 ? 0 : 1)}h`
}

function postExtubationAccessory(alert: any) {
  return !!postExtubationExtra(alert)?.accessory_muscle_use
}

function postExtubationTitle(alert: any) {
  const rr = postExtubationMetric(alert, 'rr')
  const spo2 = postExtubationMetric(alert, 'spo2', '%')
  const hours = postExtubationHours(alert)
  return `拔管后 ${hours} 出现呼吸恶化信号 · RR ${rr} / SpO₂ ${spo2}`
}

function itemTitle(alert: any) {
  return String(alert?.name || alert?.rule_id || '预警').trim() || '预警'
}

function rescueEvidenceChips(alert: any) {
  const evidence = explanationEvidence(alert)
  if (evidence.length) return evidence.slice(0, 3)
  const chainEvidence = compositeClinicalChain(alert)?.evidence
  if (Array.isArray(chainEvidence) && chainEvidence.length) {
    return chainEvidence.map((x: any) => String(x || '').trim()).filter(Boolean).slice(0, 3)
  }
  return []
}

function severityClass(raw: any) {
  const s = String(raw || '').toLowerCase()
  if (s === 'critical' || s.includes('crit')) return 'critical'
  if (s === 'high' || s.includes('high')) return 'high'
  return 'warning'
}

function severityText(raw: any) {
  const sev = severityClass(raw)
  if (sev === 'critical') return '危急'
  if (sev === 'high') return '高风险'
  return '预警'
}

function weaningSeverity(raw: any) {
  const value = String(raw || '').toLowerCase()
  if (value === 'critical') return 'critical'
  if (value === 'high') return 'high'
  if (value === 'warning') return 'warning'
  return 'stable'
}

function weaningRiskLabel(raw: any) {
  const value = String(raw || '').toLowerCase()
  if (value === 'critical') return '极高风险'
  if (value === 'high') return '高风险'
  if (value === 'warning') return '中风险'
  if (value) return '低风险'
  return '待评估'
}

function weaningEvidence(weaning: any) {
  const rows = Array.isArray(weaning?.factors) ? weaning.factors : []
  return rows
    .map((row: any) => String(row?.evidence || '').trim())
    .filter(Boolean)
    .slice(0, 3)
}

function compositeExtra(alert: any) {
  return alert?.extra && typeof alert.extra === 'object' ? alert.extra : {}
}

function compositeClinicalChain(alert: any) {
  const chain = compositeExtra(alert)?.clinical_chain
  return chain && typeof chain === 'object' ? chain : null
}

function compositeGroups(alert: any) {
  const rows = compositeExtra(alert)?.aggregated_groups
  return Array.isArray(rows) ? rows.filter((x: any) => x && typeof x === 'object') : []
}

function sourceAlertRows(alert: any) {
  const rows = compositeExtra(alert)?.source_alerts
  return Array.isArray(rows) ? rows.filter((x: any) => x && typeof x === 'object') : []
}

const focusedOrganLabel = computed(() => {
  const key = normalizeBodyMapOrganKey(props.focusedOrgan)
  return key ? BODY_MAP_ORGAN_LABELS[key] : ''
})

const organFocusGroups = computed(() => {
  const labels = compositeExtra(latestCompositeAlert.value)?.organ_labels_cn || {}
  const grouped = new Map<string, any[]>()
  for (const row of sourceAlertRows(latestCompositeAlert.value)) {
    const organs = Array.isArray(row?.organs) ? row.organs : []
    for (const rawOrgan of organs) {
      const key = normalizeBodyMapOrganKey(rawOrgan)
      if (!key) continue
      const bucket = grouped.get(key) || []
      bucket.push(row)
      grouped.set(key, bucket)
    }
  }
  return BODY_MAP_ORGAN_ORDER
    .map((key) => {
      const rows = (grouped.get(key) || []).sort((a: any, b: any) => new Date(b?.time || 0).getTime() - new Date(a?.time || 0).getTime())
      const severity = rows.reduce((current, row) => {
        const next = String(row?.severity || 'warning').toLowerCase()
        return severityWeight(next) > severityWeight(current) ? next : current
      }, 'normal')
      return {
        key,
        label: labels[key] || BODY_MAP_ORGAN_LABELS[key],
        rows,
        severity,
      }
    })
    .filter((item) => item.rows.length)
})

function alertCardKey(item: any, idx: number) {
  return String(item?._id || `${item?.alert_type || 'alert'}-${item?.created_at || idx}`)
}

function sourceAlertDisplayName(row: any) {
  return String(row?.name || row?.rule_id || alertTypeText(row?.alert_type || '预警')).trim()
}

function severityWeight(value: any) {
  return ({ normal: 0, warning: 1, high: 2, critical: 3 } as Record<string, number>)[String(value || 'normal').toLowerCase()] || 0
}

function scrollToAlertCard(row: any) {
  focusAlertRow(row)
}

function flashTarget(target: HTMLElement, className: string) {
  target.classList.add(className)
  window.setTimeout(() => target.classList.remove(className), 1800)
}

function findAlertCardByTypes(types: string[]) {
  if (typeof document === 'undefined') return null
  const normalized = new Set(types.map((item) => String(item || '').trim()).filter(Boolean))
  if (!normalized.size) return null
  const cards = Array.from(document.querySelectorAll('[data-alert-type]')) as HTMLElement[]
  return cards.find((card) => normalized.has(String(card.dataset.alertType || '').trim())) || null
}

function findAlertCardByRow(row: any) {
  if (typeof document === 'undefined' || !row) return null
  const type = String(row?.alert_type || '').trim()
  if (!type) return null
  const targetName = String(row?.name || row?.rule_id || '').trim()
  const targetTime = new Date(row?.time || row?.created_at || 0).getTime()
  const candidates = Array.from(document.querySelectorAll(`[data-alert-type="${type}"]`)) as HTMLElement[]
  if (!candidates.length) return null
  if (candidates.length === 1) return candidates[0]
  const scored = candidates
    .map((card) => {
      const cardName = String(card.dataset.alertName || '').trim()
      const cardTime = new Date(card.dataset.alertCreatedAt || 0).getTime()
      const nameMatched = targetName && cardName === targetName ? 1 : 0
      const timeGap = Number.isFinite(targetTime) && Number.isFinite(cardTime) ? Math.abs(cardTime - targetTime) : Number.MAX_SAFE_INTEGER
      return { card, nameMatched, timeGap }
    })
    .sort((a, b) => {
      if (b.nameMatched !== a.nameMatched) return b.nameMatched - a.nameMatched
      return a.timeGap - b.timeGap
    })
  return scored[0]?.card || null
}

function focusAlertTypes(types: string[]) {
  const target = findAlertCardByTypes(types)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    flashTarget(target, 'alert-card--flash')
  }
}

function focusAlertRow(row: any) {
  const target = findAlertCardByRow(row)
  if (target) {
    target.scrollIntoView({ behavior: 'smooth', block: 'center' })
    flashTarget(target, 'alert-card--flash')
    return
  }
  const type = String(row?.alert_type || '').trim()
  if (type) {
    focusAlertTypes([type])
  }
}

watch(
  () => props.focusedOrgan,
  async (next) => {
    const key = normalizeBodyMapOrganKey(next)
    if (!key || typeof document === 'undefined' || (props.focusedAlertTypes || []).length) return
    await nextTick()
    const target = document.querySelector(`[data-organ-group="${key}"]`) as HTMLElement | null
    const group = organFocusGroups.value.find((item) => item.key === key)
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'center' })
      flashTarget(target, 'organ-focus-card--flash')
    }
    const firstRow = group?.rows?.[0]
    if (firstRow) {
      window.setTimeout(() => focusAlertRow(firstRow), target ? 180 : 0)
    }
  },
  { immediate: true }
)

watch(
  () => (props.focusedAlertTypes || []).join('|'),
  async () => {
    const types = Array.isArray(props.focusedAlertTypes) ? props.focusedAlertTypes : []
    if (!types.length) return
    await nextTick()
    focusAlertTypes(types)
  },
  { immediate: true }
)

function compositeGroupLabel(raw: any) {
  return formatCompositeGroupLabel(raw)
}

function compositeChainLabel(raw: any) {
  return formatCompositeChainLabel(raw)
}

function contextSnapshot(alert: any) {
  const ctx = compositeExtra(alert)?.context_snapshot
  return ctx && typeof ctx === 'object' ? ctx : null
}

function hasContextSnapshot(alert: any) {
  const ctx = contextSnapshot(alert)
  if (!ctx) return false
  return snapshotVitals(alert).length > 0 || snapshotLabs(alert).length > 0 || snapshotVasopressors(alert).length > 0
}

function snapshotValue(entry: any, digits = 0) {
  let current = entry
  let raw = entry?.value
  let unit = String(entry?.unit || '').trim()

  // Some snapshot payloads may wrap the actual lab payload in an extra { value } layer.
  while (raw && typeof raw === 'object' && !Array.isArray(raw)) {
    current = raw
    raw = raw?.value
    if (!unit) unit = String(current?.unit || '').trim()
  }

  if (raw == null || raw === '') return ''
  const num = Number(raw)
  if (Number.isFinite(num)) {
    const valueText = digits > 0 ? num.toFixed(digits) : (Math.abs(num - Math.round(num)) < 0.05 ? String(Math.round(num)) : num.toFixed(1))
    return unit ? `${valueText}${unit}` : valueText
  }
  return unit ? `${raw}${unit}` : String(raw)
}

function snapshotVitals(alert: any) {
  const vitals = contextSnapshot(alert)?.vitals || {}
  const defs = [
    { key: 'hr', label: 'HR', digits: 0 },
    { key: 'rr', label: 'RR', digits: 0 },
    { key: 'map', label: 'MAP', digits: 0 },
    { key: 'spo2', label: 'SpO₂', digits: 0 },
    { key: 'temp', label: 'T', digits: 1 },
  ]
  return defs
    .map((def) => {
      const entry = vitals?.[def.key]
      const value = snapshotValue(entry, def.digits)
      return value ? { label: def.label, value } : null
    })
    .filter(Boolean) as Array<{ label: string; value: string }>
}

function snapshotLabs(alert: any) {
  const labs = contextSnapshot(alert)?.labs || {}
  const defs = [
    { key: 'lac', label: 'Lac', digits: 1 },
    { key: 'cr', label: 'Cr', digits: 0 },
    { key: 'pct', label: 'PCT', digits: 2 },
  ]
  return defs
    .map((def) => {
      const entry = labs?.[def.key]
      const value = snapshotValue(entry, def.digits)
      return value ? { label: def.label, value } : null
    })
    .filter(Boolean) as Array<{ label: string; value: string }>
}

function snapshotVasopressors(alert: any) {
  const rows = contextSnapshot(alert)?.vasopressors
  if (!Array.isArray(rows)) return []
  return rows
    .map((row: any) => {
      const drug = String(row?.drug || row?.raw_name || '').trim()
      if (!drug) return null
      const dose = String(row?.dose_display || row?.route || '在用').trim()
      return { drug, dose }
    })
    .filter(Boolean) as Array<{ drug: string; dose: string }>
}

const DetailChart = defineAsyncComponent(async () => {
  await import('../../charts/patient-detail')
  const mod = await import('vue-echarts')
  return mod.default
})
</script>

<style scoped>
.modi-panel {
  margin-bottom: 16px;
  border: 1px solid rgba(80,199,255,.14);
  border-radius: 12px;
  padding: 16px;
  background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.modi-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.modi-title {
  color: #eafcff;
  font-size: 15px;
  font-weight: 800;
  letter-spacing: .06em;
}
.modi-sub,
.modi-organs {
  margin-top: 4px;
  color: #8da4c7;
  font-size: 12px;
}
.modi-kpi-group {
  display: grid;
  grid-template-columns: repeat(2, minmax(100px, 1fr));
  gap: 8px;
}
.modi-kpi {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 10px;
  padding: 10px 12px;
  background: rgba(8,28,44,.78);
  text-align: right;
}
.modi-kpi > span {
  display: block;
  color: #7ecce1;
  font-size: 11px;
  letter-spacing: .08em;
}
.modi-kpi > strong {
  color: #effcff;
  font-size: 20px;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}
.modi-chart {
  height: 300px;
  margin-top: 8px;
}
.composite-suite {
  margin-top: 12px;
  display: grid;
  gap: 12px;
}
.composite-suite--rescue {
  gap: 10px;
}
.composite-suite--headline {
  margin-top: 14px;
}
.organ-focus-suite {
  margin-bottom: 16px;
  border: 1px solid rgba(80,199,255,.14);
  border-radius: 12px;
  padding: 14px;
  background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
}
.organ-focus-suite__head,
.organ-focus-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.organ-focus-suite__title {
  color: #eafcff;
  font-size: 15px;
  font-weight: 800;
}
.organ-focus-suite__sub {
  margin-top: 4px;
  color: #8da4c7;
  font-size: 12px;
}
.organ-focus-suite__pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(80,199,255,.12);
  background: rgba(8,28,44,.78);
  color: #dffbff;
  font-size: 12px;
}
.organ-focus-suite__grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}
.organ-focus-card {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 10px;
  padding: 10px;
  background: rgba(7, 21, 34, .72);
  transition: border-color .2s ease, box-shadow .2s ease, transform .2s ease;
}
.organ-focus-card.sev-high {
  border-color: rgba(249, 115, 22, .3);
  box-shadow: inset 0 0 0 1px rgba(249, 115, 22, .08);
}
.organ-focus-card.sev-critical {
  border-color: rgba(244, 63, 94, .3);
  box-shadow: inset 0 0 0 1px rgba(244, 63, 94, .08);
}
.organ-focus-card.is-active {
  border-color: rgba(110,231,249,.28);
  box-shadow: 0 0 0 1px rgba(110,231,249,.12), 0 10px 18px rgba(0,0,0,.12);
  transform: translateY(-1px);
}
.organ-focus-card--flash {
  animation: organ-focus-flash 1.8s ease;
}
.organ-focus-card__name {
  color: #eafcff;
  font-size: 12px;
  font-weight: 700;
}
.organ-focus-card__meta {
  margin-top: 3px;
  color: #7fa0c5;
  font-size: 11px;
}
.organ-focus-card__list {
  margin-top: 10px;
  display: grid;
  gap: 6px;
}
.organ-focus-card__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  background: rgba(11, 28, 44, .72);
  border: 1px solid rgba(80,199,255,.08);
  cursor: pointer;
}
.organ-focus-card__item span {
  color: #d7e9ff;
  font-size: 11px;
  line-height: 1.4;
  text-align: left;
}
.organ-focus-card__item small {
  color: #7da7c4;
  font-size: 10px;
  flex: 0 0 auto;
}
.composite-chain-card,
.composite-group-section {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 12px;
  padding: 12px;
  background: linear-gradient(180deg, rgba(8,30,46,.8) 0%, rgba(7,22,36,.92) 100%);
}
.suite-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.suite-tag {
  color: #67dff2;
  font-size: 10px;
  letter-spacing: .12em;
}
.suite-code {
  color: #a7d8ff;
  font-size: 10px;
  letter-spacing: .08em;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid rgba(80,199,255,.12);
  background: rgba(6, 22, 36, .76);
}
.chain-summary {
  color: #e8f7ff;
  font-size: 13px;
  line-height: 1.7;
  font-weight: 600;
}
.chain-chip-row {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.chain-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(78, 188, 255, .18);
  background: rgba(14, 44, 66, .72);
  color: #dff7ff;
  font-size: 11px;
}
.chain-suggestion {
  margin-top: 10px;
  color: #9fe8ba;
  font-size: 12px;
  line-height: 1.6;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(55, 199, 147, .16);
  background: rgba(8, 36, 30, .6);
}
.context-snapshot {
  margin-top: 10px;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(80,199,255,.12);
  background: linear-gradient(180deg, rgba(7, 24, 39, .88) 0%, rgba(7, 18, 30, .94) 100%);
  display: grid;
  gap: 8px;
}
.post-extub-panel {
  margin-top: 10px;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid rgba(251, 113, 133, .16);
  background: linear-gradient(180deg, rgba(55, 16, 28, .54) 0%, rgba(18, 17, 30, .78) 100%);
  display: grid;
  gap: 8px;
}
.post-extub-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.post-extub-tag {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(74, 19, 31, 0.86);
  border: 1px solid rgba(251, 113, 133, 0.18);
  color: #fda4af;
  font-size: 9px;
  letter-spacing: .12em;
}
.post-extub-pill {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 9px;
  font-weight: 700;
}
.post-extub-pill.sev-warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.post-extub-pill.sev-high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.post-extub-pill.sev-critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.post-extub-main {
  color: #fff1f3;
  font-size: 12px;
  line-height: 1.5;
  font-weight: 700;
}
.post-extub-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.post-extub-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(96, 165, 250, 0.18);
  background: rgba(12, 31, 50, 0.9);
  color: #e8f5ff;
  font-size: 10px;
}
.post-extub-chip--warn {
  border-color: rgba(251, 146, 60, 0.2);
  background: rgba(72, 30, 11, 0.76);
  color: #ffd8b4;
}
.context-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.context-tag {
  color: #72e4f7;
  font-size: 10px;
  letter-spacing: .12em;
}
.context-time {
  color: #83abc4;
  font-size: 10px;
}
.context-row {
  display: grid;
  grid-template-columns: 42px 1fr;
  gap: 8px;
  align-items: flex-start;
}
.context-row-label {
  color: #8ed8ee;
  font-size: 10px;
  letter-spacing: .1em;
  padding-top: 6px;
  text-transform: uppercase;
}
.context-chip-row,
.context-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.context-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(80,199,255,.12);
  background: rgba(11, 35, 54, .84);
}
.context-chip--lab {
  border-color: rgba(96, 165, 250, .18);
  background: rgba(12, 31, 50, .9);
}
.context-chip-label {
  color: #84bfd7;
  font-size: 10px;
  letter-spacing: .08em;
}
.context-chip-value {
  color: #effbff;
  font-size: 12px;
  font-family: 'Rajdhani', 'JetBrains Mono', 'Consolas', monospace;
  font-weight: 700;
}
.context-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(245, 158, 11, .2);
  background: rgba(51, 27, 7, .66);
}
.context-badge-name {
  color: #fde68a;
  font-size: 11px;
  font-weight: 700;
}
.context-badge-dose {
  color: #ffe9b2;
  font-size: 11px;
  font-family: 'Rajdhani', 'JetBrains Mono', 'Consolas', monospace;
}
.group-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}
.group-card {
  border: 1px solid rgba(80,199,255,.12);
  border-radius: 10px;
  padding: 10px;
  background: rgba(7, 21, 34, .72);
}
.group-card.sev-high {
  border-color: rgba(249, 115, 22, .3);
  box-shadow: inset 0 0 0 1px rgba(249, 115, 22, .08);
}
.group-card.sev-critical {
  border-color: rgba(244, 63, 94, .3);
  box-shadow: inset 0 0 0 1px rgba(244, 63, 94, .08);
}
.group-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.group-name {
  color: #eafcff;
  font-size: 12px;
  font-weight: 700;
}
.group-sub {
  margin-top: 3px;
  color: #7fa0c5;
  font-size: 11px;
}
.group-pill {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 10px;
  font-weight: 700;
  border: 1px solid transparent;
}
.group-pill.sev-warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.group-pill.sev-high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.group-pill.sev-critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.group-alert-list {
  margin-top: 10px;
  display: grid;
  gap: 6px;
}
.group-alert-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(11, 28, 44, .72);
  border: 1px solid rgba(80,199,255,.08);
}
.group-alert-name {
  color: #d7e9ff;
  font-size: 11px;
  line-height: 1.4;
}
.group-alert-time {
  color: #7fb6d6;
  font-size: 10px;
  white-space: nowrap;
}
.weaning-brief {
  margin-bottom: 16px;
  padding: 16px;
  border-radius: 12px;
  border: 1px solid rgba(80,199,255,.14);
  background:
    radial-gradient(circle at top right, rgba(59,130,246,.08), rgba(59,130,246,0) 30%),
    linear-gradient(180deg, rgba(7,20,34,.96) 0%, rgba(4,12,22,.98) 100%);
  display: grid;
  gap: 10px;
}
.weaning-brief-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.weaning-brief-title {
  color: #7ed6eb;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.weaning-brief-sub {
  margin-top: 4px;
  color: #8fb8ca;
  font-size: 12px;
}
.weaning-brief-score {
  min-width: 86px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(80,199,255,.14);
  background: rgba(8,31,49,.86);
  text-align: right;
}
.weaning-brief-score span {
  display: block;
  color: #8fe6f4;
  font-size: 11px;
}
.weaning-brief-score strong {
  display: block;
  color: #effcff;
  font-size: 24px;
  line-height: 1;
  font-family: 'Rajdhani', 'SF Mono', 'Consolas', monospace;
}
.weaning-brief-score.sev-critical { border-color: rgba(251,113,133,.34); }
.weaning-brief-score.sev-high { border-color: rgba(251,146,60,.3); }
.weaning-brief-score.sev-warning { border-color: rgba(245,158,11,.26); }
.weaning-brief-score.sev-stable { border-color: rgba(34,197,94,.24); }
.weaning-brief-main {
  color: #effcff;
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
}
.weaning-chip-row,
.weaning-evidence-row,
.weaning-sbt-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.weaning-chip,
.weaning-evidence-chip,
.weaning-sbt-pill,
.weaning-sbt-meta {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(79,182,219,.18);
  background: rgba(8,28,44,.82);
  color: #dffbff;
  font-size: 12px;
}
.weaning-evidence-chip {
  background: rgba(11,43,63,.72);
}
.weaning-sbt-pill.is-passed { color: #34d399; border-color: rgba(52,211,153,.26); }
.weaning-sbt-pill.is-failed { color: #fb7185; border-color: rgba(251,113,133,.26); }
.weaning-sbt-pill.is-documented { color: #38bdf8; border-color: rgba(56,189,248,.24); }
.weaning-sbt-meta--risk {
  color: #fb923c;
  border-color: rgba(251,146,60,.24);
}
.alert-feed {
  display: grid;
  gap: 12px;
}
.alert-card {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 12px;
}
.alert-card--flash .alert-body {
  animation: alert-card-flash 1.8s ease;
}
.alert-rail {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: 4px;
  gap: 8px;
}
.alert-time {
  font-size: 10px;
  color: #73cde0;
  letter-spacing: .08em;
  writing-mode: vertical-rl;
  transform: rotate(180deg);
}
.alert-dot {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  flex: 0 0 auto;
}
.alert-line {
  width: 2px;
  flex: 1 1 auto;
  margin-top: 8px;
  border-radius: 999px;
  background: linear-gradient(180deg, #1f3c67 0%, #0f233f 100%);
}
.alert-body {
  border: 1px solid rgba(80,199,255,.12);
  border-left: 5px solid #f59e0b;
  border-radius: 12px;
  padding: 14px 18px;
  background: linear-gradient(180deg, rgba(7,20,34,.94) 0%, rgba(4,12,22,.96) 100%);
  box-shadow: inset 0 1px 0 rgba(145,228,255,.04);
}
.alert-body--rescue {
  background:
    radial-gradient(circle at top right, rgba(251, 113, 133, .08), rgba(251, 113, 133, 0) 26%),
    linear-gradient(180deg, rgba(11, 23, 38, .98) 0%, rgba(6, 13, 24, .99) 100%);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 0 0 1px rgba(251, 113, 133, .04);
}
.alert-card.sev-high .alert-body { border-left-color: #f97316; }
.alert-card.sev-critical .alert-body { border-left-color: #f43f5e; }
.alert-card.sev-high .alert-body--rescue {
  border-color: rgba(249,115,22,.18);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 0 0 1px rgba(249,115,22,.08), 0 10px 24px rgba(249,115,22,.06);
}
.alert-card.sev-critical .alert-body--rescue {
  border-color: rgba(244,63,94,.2);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.04), 0 0 0 1px rgba(244,63,94,.1), 0 10px 28px rgba(244,63,94,.08);
}
.alert-dot.sev-warning { background: #f59e0b; box-shadow: 0 0 8px rgba(245,158,11,.55); }
.alert-dot.sev-high { background: #f97316; box-shadow: 0 0 8px rgba(249,115,22,.55); }
.alert-dot.sev-critical { background: #f43f5e; box-shadow: 0 0 10px rgba(244,63,94,.6); }
.alert-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}
@keyframes organ-focus-flash {
  0%, 100% { box-shadow: 0 0 0 0 rgba(110,231,249,0); }
  50% { box-shadow: 0 0 0 4px rgba(110,231,249,.08), 0 14px 22px rgba(0,0,0,.16); }
}
@keyframes alert-card-flash {
  0%, 100% { box-shadow: inset 0 1px 0 rgba(145,228,255,.04); }
  50% { box-shadow: inset 0 1px 0 rgba(145,228,255,.04), 0 0 0 4px rgba(110,231,249,.08), 0 16px 28px rgba(0,0,0,.14); }
}
.alert-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 22px;
}
.alert-title {
  margin: 0;
  color: #eafcff;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.25;
}
.alert-pill {
  display: inline-flex;
  align-items: center;
  height: 20px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .08em;
  border: 1px solid transparent;
}
.alert-pill.sev-warning { color: #fcd34d; background: #3f2d07; border-color: #6a4b0d; }
.alert-pill.sev-high { color: #fdba74; background: #41210b; border-color: #7c3816; }
.alert-pill.sev-critical { color: #fda4af; background: #47131d; border-color: #7f1d32; }
.alert-value {
  font-family: 'Rajdhani', 'JetBrains Mono', 'Consolas', monospace;
  font-size: 18px;
  line-height: 1.2;
  color: #f1f6ff;
  font-weight: 800;
  text-align: right;
  white-space: nowrap;
}
.alert-terminal-line {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.terminal-tag {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(8, 30, 46, 0.88);
  border: 1px solid rgba(80,199,255,.12);
  color: #73d9ee;
  font-size: 10px;
  letter-spacing: .1em;
}
.terminal-id {
  color: #a9c7dd;
  font-size: 11px;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
  line-height: 1.4;
  word-break: break-all;
}
.alert-explanation {
  margin-top: 10px;
  padding: 9px 10px;
  border-radius: 10px;
  border: 1px solid rgba(80,199,255,.12);
  background: linear-gradient(180deg, rgba(8,30,46,.84) 0%, rgba(8,23,38,.92) 100%);
  display: grid;
  gap: 6px;
}
.alert-explanation--rescue {
  padding: 12px;
  border-color: rgba(251, 113, 133, .16);
  background:
    linear-gradient(180deg, rgba(47, 14, 24, .26) 0%, rgba(10, 24, 39, .92) 22%, rgba(7, 20, 34, .96) 100%);
}
.rescue-headline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(251, 113, 133, .12);
}
.rescue-headline-tag {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(74, 19, 31, .9);
  border: 1px solid rgba(251, 113, 133, .18);
  color: #fda4af;
  font-size: 10px;
  letter-spacing: .12em;
}
.rescue-headline-main {
  color: #ffe4ea;
  font-size: 13px;
  font-weight: 700;
}
.explanation-grid {
  display: grid;
  gap: 8px;
}
.explanation-grid--rescue {
  gap: 10px;
}
.explanation-block {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(80,199,255,.08);
  background: rgba(5, 18, 30, .5);
  box-shadow: inset 0 1px 0 rgba(145, 228, 255, .03);
}
.explanation-block--summary {
  background: linear-gradient(180deg, rgba(57, 15, 28, .72) 0%, rgba(22, 19, 33, .78) 100%);
  border-color: rgba(251, 113, 133, .18);
}
.explanation-block--evidence {
  background: rgba(8, 27, 42, .72);
}
.explanation-block--suggestion {
  background: linear-gradient(180deg, rgba(8, 38, 30, .72) 0%, rgba(7, 28, 24, .8) 100%);
  border-color: rgba(55, 199, 147, .16);
}
.explanation-tag {
  color: #67dff2;
  font-size: 10px;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.explanation-label {
  color: #90e7ff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .14em;
  text-transform: uppercase;
}
.explanation-text {
  color: #d9ebff;
  font-size: 12px;
  line-height: 1.8;
  white-space: pre-wrap;
}
.explanation-text--summary {
  color: #fff1f3;
  font-size: 15px;
  line-height: 1.65;
  font-weight: 700;
}
.explanation-text--suggestion {
  color: #b4f3ca;
  font-weight: 600;
}
.explanation-list {
  margin: 0;
  padding-left: 18px;
  color: #d9ebff;
  font-size: 12px;
  line-height: 1.75;
  display: grid;
  gap: 6px;
}
.rescue-evidence-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.rescue-evidence-chip {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(96, 165, 250, .18);
  background: rgba(12, 31, 50, .9);
  color: #e8f5ff;
  font-size: 12px;
  line-height: 1.4;
}
.reasoning-brief,
.reasoning-card {
  margin-top: 10px;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(94, 234, 212, .16);
  background: linear-gradient(180deg, rgba(7, 33, 34, .92) 0%, rgba(7, 21, 27, .96) 100%);
}
.threshold-brief {
  margin: 0 0 18px;
  padding: 16px 18px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(10, 26, 42, 0.96) 0%, rgba(6, 18, 30, 0.98) 100%);
  border: 1px solid rgba(96, 214, 255, 0.18);
  box-shadow: inset 0 1px 0 rgba(178, 241, 255, 0.05), 0 12px 28px rgba(0, 0, 0, 0.18);
}
.threshold-brief-head,
.threshold-action-row,
.threshold-meta-row,
.threshold-card-head,
.threshold-card-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.threshold-brief-title {
  color: #f1fdff;
  font-size: 18px;
  font-weight: 700;
}
.threshold-brief-sub,
.threshold-card-reason,
.threshold-footnote,
.threshold-empty {
  color: #8eb4c4;
}
.threshold-brief-main {
  margin-top: 12px;
  color: #dff7ff;
  line-height: 1.6;
}
.threshold-meta-row {
  margin-top: 10px;
}
.threshold-approved-note {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: #b8d9e5;
  font-size: 12px;
}
.threshold-approved-note strong {
  color: #9df7c7;
}
.threshold-meta-chip,
.threshold-card-band,
.threshold-status-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid rgba(96, 214, 255, 0.18);
  background: rgba(8, 27, 44, 0.9);
  color: #8de7f7;
}
.threshold-status-pill.is-approved {
  color: #9df7c7;
  border-color: rgba(102, 214, 151, 0.28);
}
.threshold-status-pill.is-rejected {
  color: #ffb7b7;
  border-color: rgba(255, 133, 133, 0.24);
}
.threshold-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
  margin-top: 14px;
}
.threshold-card {
  padding: 12px;
  border-radius: 12px;
  background: rgba(10, 30, 48, 0.72);
  border: 1px solid rgba(96, 214, 255, 0.12);
}
.threshold-card-name {
  color: #f1fdff;
  font-weight: 700;
}
.threshold-card-main {
  margin-top: 10px;
  color: #c9edf7;
  font-size: 12px;
}
.threshold-card-reason {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.5;
}
.threshold-card-main em {
  color: #8eb4c4;
  font-style: normal;
  margin-left: 4px;
  font-size: 11px;
}
.threshold-action-row {
  margin-top: 14px;
  justify-content: flex-end;
}
.threshold-empty--error {
  color: #ffb7b7;
}
.reasoning-brief {
  margin-bottom: 16px;
}
.reasoning-brief-head,
.reasoning-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.reasoning-brief-title {
  color: #dffcf8;
  font-size: 15px;
  font-weight: 800;
  letter-spacing: .06em;
}
.reasoning-brief-sub,
.reasoning-group-meta {
  margin-top: 4px;
  color: #8bbab5;
  font-size: 12px;
}
.reasoning-brief-main,
.reasoning-summary {
  margin-top: 10px;
  color: #effffb;
  font-size: 13px;
  line-height: 1.7;
  font-weight: 700;
}
.reasoning-brief-urgent,
.reasoning-urgent {
  margin-top: 10px;
  color: #b9ffd8;
  font-size: 12px;
  line-height: 1.6;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(74, 222, 128, .18);
  background: rgba(10, 45, 31, .52);
}
.reasoning-tag {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  background: rgba(8, 64, 58, .84);
  border: 1px solid rgba(94, 234, 212, .18);
  color: #99f6e4;
  font-size: 9px;
  letter-spacing: .12em;
}
.reasoning-brief-confidence,
.reasoning-confidence-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  font-size: 11px;
  font-weight: 700;
}
.reasoning-brief-confidence > span {
  opacity: .78;
}
.reasoning-brief-confidence.is-high,
.reasoning-confidence-pill.is-high {
  color: #bbf7d0;
  background: rgba(20, 83, 45, .62);
  border-color: rgba(74, 222, 128, .24);
}
.reasoning-brief-confidence.is-medium,
.reasoning-confidence-pill.is-medium {
  color: #fde68a;
  background: rgba(66, 46, 9, .68);
  border-color: rgba(251, 191, 36, .22);
}
.reasoning-brief-confidence.is-low,
.reasoning-confidence-pill.is-low {
  color: #fecaca;
  background: rgba(69, 10, 10, .62);
  border-color: rgba(248, 113, 113, .22);
}
.reasoning-chip-row {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.reasoning-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(94, 234, 212, .14);
  background: rgba(7, 48, 48, .64);
  color: #d7fffb;
  font-size: 11px;
}
.reasoning-section {
  margin-top: 12px;
}
.reasoning-section-title {
  color: #88e7d8;
  font-size: 11px;
  letter-spacing: .08em;
  margin-bottom: 8px;
}
.reasoning-action {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 0;
  border-top: 1px solid rgba(148, 163, 184, .1);
}
.reasoning-action:first-of-type {
  border-top: 0;
}
.reasoning-rank {
  min-width: 30px;
  height: 24px;
  border-radius: 999px;
  background: rgba(13, 148, 136, .16);
  border: 1px solid rgba(94, 234, 212, .16);
  color: #a7f3d0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 800;
}
.reasoning-action-main {
  color: #effcf9;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.5;
}
.reasoning-action-why,
.reasoning-group-reason {
  margin-top: 4px;
  color: #a8c9c5;
  font-size: 12px;
  line-height: 1.6;
}
.reasoning-group-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}
.reasoning-group-card {
  border-radius: 10px;
  border: 1px solid rgba(94, 234, 212, .12);
  background: rgba(8, 34, 38, .78);
  padding: 10px;
}
.reasoning-group-label {
  color: #dffcf8;
  font-size: 12px;
  font-weight: 700;
}
.reasoning-list {
  margin: 0;
  padding-left: 18px;
  color: #e5f7f3;
  font-size: 12px;
  line-height: 1.7;
}
.alert-action-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 10px;
}
.alert-action-chip {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(56, 189, 248, 0.22);
  background: rgba(8, 34, 52, 0.72);
  color: #c8ecff;
  font-size: 12px;
}
.alert-action-chip--ok {
  border-color: rgba(34, 197, 94, 0.28);
  background: rgba(16, 48, 34, 0.7);
  color: #c7f9d4;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.ack-disposition-badge {
  font-size: 11px;
  opacity: 0.85;
  letter-spacing: 0.02em;
}
.ack-disposition-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 2px;
}
.ack-disposition-bar .ant-btn {
  font-size: 11px !important;
  height: 22px !important;
  padding: 0 8px !important;
  border-radius: 999px !important;
}
.alert-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.alert-meta > span {
  font-size: 11px;
  color: #8da4c7;
  padding: 2px 8px;
  border-radius: 999px;
  background: #10233d;
  border: 1px solid #1b3a60;
}
.alert-rule {
  margin-top: 8px;
  font-size: 12px;
  color: #d7e6ff;
  font-family: 'JetBrains Mono', 'Consolas', monospace;
}
.alert-detail-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 8px 10px;
  margin-top: 10px;
}
.alert-detail-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  font-size: 11px;
  color: #9ca3af;
  background: #0f2038;
  border: 1px solid #1c3d64;
  border-radius: 8px;
  padding: 6px 8px;
}
.detail-label { color: #7aa2d6; }
.detail-value { color: #e5e7eb; font-weight: 600; }
.alert-extra {
  margin-top: 10px;
  white-space: pre-wrap;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
  background: #0b1626;
  border: 1px solid #19304d;
  border-radius: 8px;
  padding: 8px;
}
.alert-extra--muted {
  white-space: normal;
  font-size: 12px;
  color: #9eb2cc;
  background: #0d1c2f;
}
.ai-risk-panel {
  margin-top: 12px;
  display: grid;
  gap: 10px;
}
.ai-risk-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.ai-risk-summary,
.ai-risk-card {
  border: 1px solid #214064;
  border-radius: 10px;
  background: #0d2036;
  padding: 10px 12px;
}
.ai-risk-summary {
  display: grid;
  gap: 4px;
  min-width: 240px;
}
.ai-risk-summary strong,
.ai-risk-card strong { color: #eef4ff; }
.ai-risk-summary span,
.ai-risk-card p {
  color: #b9cae8;
  font-size: 12px;
  margin: 0;
}
.ai-risk-feedback { display: flex; gap: 8px; flex-wrap: wrap; }
.ai-risk-feedback :deep(.ant-btn) {
  background: rgba(8,28,44,.78);
  border-color: rgba(80,199,255,.14);
  color: #dffbff;
}
.ai-risk-organ-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 8px;
}
.ai-risk-organ {
  border: 1px solid #1c3a5b;
  border-radius: 10px;
  background: #0c1d31;
  padding: 8px 10px;
  transition: opacity .2s ease;
}
.ai-risk-organ-top {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
}
.ai-risk-organ-name { color: #d9e8ff; font-weight: 700; }
.ai-risk-organ-status,
.ai-risk-organ-conf,
.ai-risk-organ-evidence { font-size: 11px; }
.ai-risk-organ-status { color: #93c5fd; }
.ai-risk-organ-evidence { margin-top: 6px; color: #a9bbda; line-height: 1.5; }
.ai-risk-organ-conf { margin-top: 6px; color: #7fa0d0; }
.ai-risk-section {
  border: 1px solid #1d3554;
  border-radius: 10px;
  background: #0a1829;
  padding: 10px 12px;
}
.ai-risk-section-title {
  color: #dbe9ff;
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 8px;
}
.ai-risk-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  color: #bfd0ec;
  font-size: 12px;
}
.ai-risk-list-warning { color: #fecaca; }
.ai-risk-list-hallucination { list-style: none; padding-left: 0; }
.hallucination-pill {
  display: inline-flex;
  align-items: center;
  padding: 6px 8px;
  border-radius: 999px;
  width: fit-content;
  max-width: 100%;
  border: 1px solid transparent;
}
.hallucination-warning { color: #fde68a; background: #3c2d06; border-color: #6b4f11; }
.hallucination-high { color: #fecaca; background: #47131d; border-color: #7f1d32; }
.ai-risk-evidence-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
}
.ai-evidence-link { color: #93c5fd; cursor: pointer; }
.ai-evidence-link:hover { color: #bfdbfe; }
.ai-evidence-popover {
  max-width: 420px;
  display: grid;
  gap: 6px;
  color: #334155;
}
.ai-evidence-quote {
  max-width: 420px;
  white-space: pre-wrap;
  line-height: 1.6;
}
.ai-confidence-low { opacity: 0.58; }
.ai-confidence-medium { opacity: 0.82; }
.ai-confidence-high { opacity: 1; }
.tab-empty {
  color: #7ccfe4;
  font-size: 12px;
  padding: 12px;
  border-radius: 10px;
  background: rgba(8,28,44,.58);
  border: 1px dashed rgba(80,199,255,.14);
}

@media (max-width: 980px) {
  .weaning-brief-head {
    flex-direction: column;
  }
  .alert-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .alert-value {
    text-align: left;
    font-size: 16px;
  }
  .alert-time {
    writing-mode: initial;
    transform: none;
  }
  .modi-chart {
    height: 260px;
  }
  .group-grid {
    grid-template-columns: 1fr;
  }
  .organ-focus-suite__grid {
    grid-template-columns: 1fr;
  }
  .context-row {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .context-row-label {
    padding-top: 0;
  }
}

@media (max-width: 640px) {
  .alert-card {
    grid-template-columns: 1fr;
    gap: 6px;
  }
  .alert-rail {
    display: none;
  }
  .alert-body {
    padding: 10px;
  }
  .modi-kpi-group {
    width: 100%;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .modi-kpi {
    text-align: left;
  }
  .modi-chart {
    height: 240px;
  }
}

/* Light mode overrides */
html[data-theme='light'] .modi-panel { background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(242,247,252,0.98) 100%); border-color: rgba(187,204,220,0.72); box-shadow: 0 10px 24px rgba(15,23,42,0.06); }
html[data-theme='light'] .organ-focus-suite { background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(242,247,252,0.98) 100%); border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .modi-title { color: #16324f; }
html[data-theme='light'] .organ-focus-suite__title,
html[data-theme='light'] .organ-focus-card__name { color: #16324f; }
html[data-theme='light'] .modi-sub, html[data-theme='light'] .modi-organs { color: #6a8098; }
html[data-theme='light'] .organ-focus-suite__sub, html[data-theme='light'] .organ-focus-card__meta, html[data-theme='light'] .organ-focus-card__item small { color: #6a8098; }
html[data-theme='light'] .modi-kpi { background: rgba(243, 248, 252, 0.96); border-color: rgba(187, 204, 220, 0.72); }
html[data-theme='light'] .modi-kpi > span { color: #47627e; }
html[data-theme='light'] .modi-kpi > strong { color: #1d4ed8; }
html[data-theme='light'] .organ-focus-suite__pill, html[data-theme='light'] .organ-focus-card, html[data-theme='light'] .organ-focus-card__item { background: #ffffff; border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .organ-focus-card__item span { color: #223a54; }
html[data-theme='light'] .composite-chain-card, html[data-theme='light'] .composite-group-section { background: rgba(243, 248, 252, 0.96); border-color: rgba(187, 204, 220, 0.72); }
html[data-theme='light'] .suite-tag { color: #1d4ed8; }
html[data-theme='light'] .suite-code { background: #ffffff; border-color: rgba(187, 204, 220, 0.72); color: #3b82f6; }
html[data-theme='light'] .chain-summary { color: #223a54; }
html[data-theme='light'] .chain-chip { background: #ffffff; border-color: rgba(187,204,220,0.72); color: #47627e; }
html[data-theme='light'] .chain-suggestion { background: rgba(231,241,249,0.96); color: #1e3a8a; border-left-color: #3b82f6; }
html[data-theme='light'] .group-card { background: #ffffff; border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .group-name { color: #16324f; }
html[data-theme='light'] .group-sub { color: #6a8098; }
html[data-theme='light'] .group-alert-name { color: #223a54; }
html[data-theme='light'] .group-alert-time { color: #6f8399; }
html[data-theme='light'] .group-alert-item {
  background: rgba(243,248,252,0.96);
  border-color: rgba(187,204,220,0.72);
}
html[data-theme='light'] .group-pill.sev-warning { color: #b45309; background: rgba(254,243,199,0.98); border-color: rgba(245,158,11,0.28); }
html[data-theme='light'] .group-pill.sev-high { color: #c2410c; background: rgba(255,237,213,0.98); border-color: rgba(251,146,60,0.28); }
html[data-theme='light'] .group-pill.sev-critical { color: #be123c; background: rgba(255,241,242,0.98); border-color: rgba(251,113,133,0.28); }
html[data-theme='light'] .weaning-brief, html[data-theme='light'] .reasoning-brief, html[data-theme='light'] .threshold-brief { background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(242,247,252,0.98) 100%); border-color: rgba(187,204,220,.72); }
html[data-theme='light'] .weaning-brief-title, html[data-theme='light'] .reasoning-brief-title, html[data-theme='light'] .threshold-brief-title { color: #16324f; }
html[data-theme='light'] .weaning-brief-sub, html[data-theme='light'] .reasoning-brief-sub, html[data-theme='light'] .threshold-brief-sub { color: #6a8098; }
html[data-theme='light'] .weaning-brief-main, html[data-theme='light'] .reasoning-brief-main, html[data-theme='light'] .threshold-brief-main { color: #223a54; }
html[data-theme='light'] .weaning-chip, html[data-theme='light'] .reasoning-chip, html[data-theme='light'] .threshold-meta-chip { background: #ffffff; border-color: rgba(187,204,220,.72); color: #47627e; }
html[data-theme='light'] .weaning-evidence-chip { background: rgba(243,248,252,0.96); border-color: rgba(187,204,220,.72); color: #47627e; }
html[data-theme='light'] .weaning-sbt-meta { color: #6f8399; }
html[data-theme='light'] .weaning-sbt-meta--risk { color: #dc2626; }
html[data-theme='light'] .alert-card { background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(242,247,252,0.98) 100%); border-color: rgba(187,204,220,0.72); box-shadow: 0 6px 16px rgba(15,23,42,0.06); }
html[data-theme='light'] .alert-body {
  background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(242,247,252,0.98) 100%);
  border-color: rgba(187,204,220,0.72);
  box-shadow: none;
}
html[data-theme='light'] .alert-body--rescue {
  background:
    radial-gradient(circle at top right, rgba(248, 113, 113, 0.12), rgba(248, 113, 113, 0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(254,242,242,.98) 100%);
}
html[data-theme='light'] .alert-time { color: #6a8098; }
html[data-theme='light'] .alert-line { background: rgba(187,204,220,0.4); }
html[data-theme='light'] .alert-title { color: #16324f; }
html[data-theme='light'] .alert-value { color: #1d4ed8; }
html[data-theme='light'] .terminal-tag {
  color: #47627e;
  background: rgba(243,248,252,0.98);
  border-color: rgba(187,204,220,0.72);
}
html[data-theme='light'] .terminal-id { color: #64748b; }
html[data-theme='light'] .post-extub-panel { border-color: rgba(187,204,220,0.72); background: rgba(243,248,252,0.96); }
html[data-theme='light'] .post-extub-tag { color: #1d4ed8; }
html[data-theme='light'] .post-extub-main { color: #223a54; }
html[data-theme='light'] .post-extub-chip { background: #ffffff; border-color: rgba(187,204,220,0.72); color: #47627e; }
html[data-theme='light'] .post-extub-chip--warn { background: rgba(254,243,199,0.96); border-color: rgba(245,158,11,0.28); color: #b45309; }
html[data-theme='light'] .alert-explanation {
  border-color: rgba(187,204,220,0.72);
  background: rgba(243,248,252,0.96);
}
html[data-theme='light'] .alert-explanation--rescue {
  border-color: rgba(248,113,113,0.22);
  background:
    radial-gradient(circle at top right, rgba(248, 113, 113, 0.12), rgba(248, 113, 113, 0) 34%),
    linear-gradient(180deg, rgba(255,255,255,.98) 0%, rgba(254,242,242,.98) 100%);
}
html[data-theme='light'] .rescue-headline {
  border-bottom-color: rgba(248,113,113,0.2);
}
html[data-theme='light'] .rescue-headline-tag {
  color: #be123c;
  background: rgba(255,241,242,0.98);
  border-color: rgba(251,113,133,0.28);
}
html[data-theme='light'] .rescue-headline-main {
  color: #16324f;
}
html[data-theme='light'] .explanation-block {
  background: #ffffff;
  border-color: rgba(187,204,220,0.72);
  box-shadow: none;
}
html[data-theme='light'] .explanation-block--summary {
  background: linear-gradient(180deg, rgba(255,245,246,.98) 0%, rgba(255,241,242,.99) 100%);
  border-color: rgba(248,113,113,0.22);
}
html[data-theme='light'] .explanation-block--evidence {
  background: #ffffff;
}
html[data-theme='light'] .explanation-block--suggestion {
  background: linear-gradient(180deg, rgba(244,252,247,.98) 0%, rgba(236,253,243,.99) 100%);
  border-color: rgba(74,222,128,.2);
}
html[data-theme='light'] .explanation-label { color: #1d4ed8; }
html[data-theme='light'] .explanation-text, html[data-theme='light'] .explanation-list { color: #223a54; }
html[data-theme='light'] .explanation-text--summary { color: #16324f; }
html[data-theme='light'] .explanation-text--suggestion { color: #047857; }
html[data-theme='light'] .reasoning-card { border-color: rgba(187,204,220,0.72); background: rgba(243,248,252,0.96); }
html[data-theme='light'] .reasoning-tag { color: #1d4ed8; }
html[data-theme='light'] .reasoning-summary { color: #223a54; }
html[data-theme='light'] .reasoning-section-title { color: #47627e; border-bottom-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .reasoning-rank { background: rgba(59,130,246,0.1); color: #2563eb; }
html[data-theme='light'] .reasoning-action-main { color: #223a54; }
html[data-theme='light'] .reasoning-action-why { color: #6f8399; }
html[data-theme='light'] .reasoning-group-card { background: #ffffff; border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .reasoning-group-label { color: #16324f; }
html[data-theme='light'] .reasoning-group-reason { color: #47627e; }
html[data-theme='light'] .reasoning-group-meta { color: #6a8098; }
html[data-theme='light'] .reasoning-list li { color: #47627e; }
html[data-theme='light'] .context-snapshot { border-color: rgba(187,204,220,0.72); background: #ffffff; }
html[data-theme='light'] .context-tag { color: #1d4ed8; }
html[data-theme='light'] .context-time { color: #6f8399; }
html[data-theme='light'] .context-row-label { color: #6f8399; }
html[data-theme='light'] .context-chip { background: rgba(243,248,252,0.96); border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .context-chip-label { color: #47627e; }
html[data-theme='light'] .context-chip-value { color: #223a54; }
html[data-theme='light'] .context-badge { background: rgba(243,248,252,0.96); border-color: rgba(187,204,220,0.72); }
html[data-theme='light'] .context-badge-name { color: #47627e; }
html[data-theme='light'] .context-badge-dose { color: #1d4ed8; }
html[data-theme='light'] .alert-action-chip { background: #ffffff; border-color: rgba(187, 204, 220, 0.72); color: #47627e; }
html[data-theme='light'] .alert-rule { background: rgba(243,248,252,0.96); color: #47627e; }
html[data-theme='light'] .threshold-card { border-color: rgba(187,204,220,0.72); background: rgba(243,248,252,0.96); }
html[data-theme='light'] .threshold-card-name { color: #16324f; }
html[data-theme='light'] .threshold-card-main span { color: #47627e; }
html[data-theme='light'] .threshold-card-reason { color: #6f8399; background: #ffffff; }
</style>

























