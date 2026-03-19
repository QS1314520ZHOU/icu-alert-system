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
            <div v-if="row.reasoning" class="threshold-card-reason">{{ row.reasoning }}</div>
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
            <span class="terminal-tag">EVENT</span>
            <span class="terminal-id">{{ item.rule_id || item.alert_type || item.category || 'monitor.rule' }}</span>
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
                <div :class="['explanation-text', { 'explanation-text--summary': isRescueRiskAlert(item) }]">{{ explanationSummary(item) }}</div>
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
                <div :class="['explanation-text', { 'explanation-text--suggestion': isRescueRiskAlert(item) }]">{{ explanationSuggestion(item) }}</div>
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
            <span v-if="item.parameter">{{ item.parameter }}</span>
          </div>
          <div
            v-if="item.parameter || item.condition?.operator || item.condition?.threshold"
            class="alert-rule"
          >
            {{ item.parameter || '参数' }}
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
          <pre v-else-if="item.extra && !alertDetailFields(item).length" class="alert-extra">{{ formatAlertExtra(item.extra) }}</pre>
        </div>
      </article>
    </div>
    <div v-if="!alerts.length" class="tab-empty">暂无预警记录</div>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { Button as AButton, Popover as APopover } from 'ant-design-vue'

defineProps<{
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
}>()

function explanationPayload(alert: any) {
  const exp = alert?.explanation
  if (typeof exp === 'string') {
    return {
      summary: exp,
      evidence: [] as string[],
      suggestion: '',
    }
  }
  if (exp && typeof exp === 'object') {
    return {
      summary: typeof exp.summary === 'string' ? exp.summary : (typeof exp.text === 'string' ? exp.text : ''),
      evidence: Array.isArray(exp.evidence) ? exp.evidence.filter((x: any) => String(x || '').trim()) : [],
      suggestion: typeof exp.suggestion === 'string' ? exp.suggestion : '',
    }
  }
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

function compositeGroupLabel(raw: any) {
  const key = String(raw || '')
  const map: Record<string, string> = {
    sepsis_group: '脓毒症主题',
    bleeding_group: '出血主题',
    respiratory_group: '呼吸主题',
  }
  return map[key] || key.replace(/_/g, ' ').toUpperCase()
}

function compositeChainLabel(raw: any) {
  const key = String(raw || '')
  const map: Record<string, string> = {
    shock_chain: '休克链',
    respiratory_failure_chain: '呼衰链',
    sepsis_progression_chain: '脓毒症进展链',
    bleeding_chain: '失血链',
    multi_organ_progression: '多器官进展',
  }
  return map[key] || key.replace(/_/g, ' ').toUpperCase()
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
  padding: 8px 9px;
  border-radius: 8px;
  border: 1px solid rgba(80,199,255,.08);
  background: rgba(5, 18, 30, .5);
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
  letter-spacing: .12em;
}
.explanation-label {
  margin-bottom: 4px;
  color: #90e7ff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
}
.explanation-text {
  color: #d9ebff;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}
.explanation-text--summary {
  color: #fff1f3;
  font-size: 15px;
  line-height: 1.5;
  font-weight: 700;
}
.explanation-text--suggestion {
  color: #b4f3ca;
  font-weight: 600;
}
.explanation-list {
  margin: 0;
  padding-left: 16px;
  color: #d9ebff;
  font-size: 12px;
  line-height: 1.6;
}
.explanation-list li + li {
  margin-top: 2px;
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
</style>

















