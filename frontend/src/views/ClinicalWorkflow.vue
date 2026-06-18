<template>
  <div class="clinical-workflow">
    <section class="hero">
      <div>
        <div class="eyebrow">ICU 智能协同工作台</div>
        <h1>{{ home?.title || '临床工作台' }}</h1>
        <div class="color-legend">
          <span class="is-critical">危急</span>
          <span class="is-high">高危</span>
          <span class="is-warning">关注</span>
          <span class="is-stable">稳定</span>
          <span class="is-info">信息</span>
        </div>
      </div>
      <div class="identity-card">
        <span>当前账号</span>
        <strong>{{ accountLabel }}</strong>
        <em>{{ roleLabel }} · {{ scopeLabel }}</em>
      </div>
    </section>

    <a-alert
      v-if="!loading && home?.account && home.account.found === false && routeUserName"
      class="soft-alert"
      type="warning"
      show-icon
      message="未在 SmartCare.account 中匹配到账号，已按默认医生视角展示。"
    />

    <section class="kpi-grid">
      <div v-for="card in cards" :key="card.key" :class="['kpi-card', `tone-${card.tone || 'info'}`]">
        <span>{{ card.label }}</span>
        <strong>{{ card.value }}</strong>
      </div>
    </section>

    <section v-if="openTaskItems.length" class="open-task-strip">
      <div class="open-task-head">
        <span>当班待办</span>
        <strong>{{ openTaskTotal }}项</strong>
      </div>
      <div class="open-task-row">
        <button
          v-for="task in openTaskItems.slice(0, 6)"
          :key="task.task_id"
          type="button"
          class="open-task-chip"
          @click="openExistingTask(task)"
        >
          <b>{{ task.bed_label || task.bed || '--' }}床</b>
          <span>{{ task.module_label || '临床' }}</span>
          <em>{{ shortTaskText(task.title || '待处理任务', 18) }}</em>
        </button>
      </div>
    </section>

    <section v-if="isDirector" class="director-morning-screen">
      <div class="director-screen-head">
        <span>主任晨会一屏</span>
        <button type="button" @click="router.push({ path: '/admin/scanner-health', query: route.query })">规则健康</button>
      </div>
      <div class="morning-tile-grid">
        <button
          v-for="tile in directorMorningTiles"
          :key="tile.key"
          type="button"
          :class="['morning-tile', `tone-${tile.tone}`]"
          @click="runDirectorTile(tile)"
        >
          <span>{{ tile.label }}</span>
          <strong>{{ tile.value }}</strong>
          <b>{{ tile.hint }}</b>
        </button>
      </div>
    </section>

    <section v-if="showWorkflowStrip" class="icu-day-section compact-workflow">
      <div class="section-head">
        <div>
          <span class="panel-kicker">ICU 一日节奏</span>
        </div>
      </div>
      <div class="day-flow">
        <article v-for="item in icuDayFlow" :key="item.key" :class="['day-card', `tone-${item.tone || 'info'}`]">
          <div class="day-time">{{ item.time }}</div>
          <strong>{{ item.scene }} · {{ item.title }}</strong>
          <button type="button" class="ghost-link" @click="runFlowAction(item)">{{ item.action }}</button>
        </article>
      </div>
    </section>

    <section v-if="showWorkflowStrip" class="ai-toolbox compact-toolbox">
      <div class="section-head compact">
        <div>
          <span class="panel-kicker">AI 工具箱</span>
        </div>
      </div>
      <div class="tool-row">
        <button v-for="tool in aiToolbox" :key="tool.key" type="button" class="tool-card" @click="runAiTool(tool)">
          <span>{{ tool.title }}</span>
          <strong>{{ tool.count || 0 }}</strong>
          <b>{{ tool.action }}</b>
        </button>
      </div>
    </section>

    <section class="visual-command">
      <div class="visual-body-card">
        <div class="visual-head">
          <span>{{ organPanelTitle }}</span>
        </div>
        <div class="body-visual-wrap">
          <HumanBodyDiagram compact :organ-states="visualOrganStates" :metric-badges="visualMetricBadges" :show-legend="false" />
          <div class="organ-mini-panel">
            <OrganRiskRadar :scores="visualRadarScores" :size="132" />
            <div class="organ-risk-list">
              <button v-for="organ in visualOrganList" :key="organ.key" type="button" :class="`is-${organ.severity}`" @click="applySignalFilter(organ.key)">
                <span>{{ organ.label }}</span>
                <b>{{ organ.text }}</b>
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="visual-chart-card">
        <div class="visual-head">
          <span>任务构成</span>
        </div>
        <div class="donut-wrap">
          <div class="donut-chart" :style="donutStyle">
            <div>
              <strong>{{ visualTotalTasks }}</strong>
              <span>任务</span>
            </div>
          </div>
          <div class="donut-legend">
            <button v-for="item in visualTaskMix" :key="item.key" type="button" @click="applySignalFilter(item.key)">
              <i :style="{ background: item.color }" />
              <span>{{ item.label }}</span>
              <b>{{ item.value }}</b>
            </button>
          </div>
        </div>
      </div>

      <div class="visual-chart-card">
        <div class="visual-head">
          <span>角色工作量</span>
        </div>
        <div class="role-bars">
          <button v-for="row in visualRoleBars" :key="row.key" type="button" @click="applySignalFilter(row.key)">
            <span>{{ row.label }}</span>
            <div><i :style="{ width: `${row.percent}%`, background: row.color }" /></div>
            <b>{{ row.value }}</b>
          </button>
        </div>
      </div>
    </section>

    <section class="clinical-visual-grid">
      <article class="visual-panel bed-wall-panel">
        <div class="visual-panel-head">
          <span>床位风险</span>
          <b>{{ bedHeatmap.length }}床</b>
        </div>
        <div class="panel-subline">数字=风险分</div>
        <div v-if="bedHeatmap.length" class="bed-heatmap">
          <button
            v-for="bed in bedHeatmap"
            :key="`bed-${bed.patient_id || bed.bed}`"
            type="button"
            :class="['bed-cell', `tone-${bed.tone || 'stable'}`]"
            @click="goPatientDetail(String(bed.patient_id || ''))"
          >
            <strong>{{ bed.bed || '--' }}</strong>
            <span>{{ bed.value || 0 }}</span>
          </button>
        </div>
        <div v-else class="visual-empty">暂无风险床位</div>
      </article>

      <article class="visual-panel">
        <div class="visual-panel-head">
          <span>护理漏项</span>
          <b>{{ nursingTodoCount }}项</b>
        </div>
        <div class="panel-subline">闭环 {{ nursingCompletion.percent ?? 100 }}%</div>
        <div class="mini-progress"><i :style="{ width: `${nursingCompletion.percent ?? 100}%` }" /></div>
        <div class="omission-grid">
          <button
            v-for="item in nursingOmissions"
            :key="item.key"
            type="button"
            :class="['omission-cell', item.status === 'todo' ? 'is-todo' : 'is-ok']"
            @click="applySignalFilter(item.key)"
          >
            <i>{{ item.status === 'todo' ? '!' : '✓' }}</i>
            <span>{{ item.label }}</span>
          </button>
        </div>
        <div v-if="nursingCompletion.tasks?.length" class="mini-task-row">
          <button v-for="task in nursingCompletion.tasks.slice(0, 3)" :key="task.key" type="button" @click="applySignalFilter('nursing')">
            {{ task.title }}
          </button>
        </div>
      </article>

      <article class="visual-panel antibiotic-panel">
        <div class="visual-panel-head">
          <span>{{ antibioticPanelTitle }}</span>
          <b>{{ activeAntibioticSummary.today || 0 }}</b>
        </div>
        <div class="antibiotic-stats">
          <span>增 {{ activeAntibioticSummary.today || 0 }}</span>
          <span>减 {{ activeAntibioticSummary.decrease_today || 0 }}</span>
          <span>净 {{ activeAntibioticSummary.net_today || 0 }}</span>
        </div>
        <div v-if="antibioticIntensity.available" class="antibiotic-chart">
          <button
            v-for="bar in activeAntibioticBars"
            :key="bar.date"
            type="button"
            class="antibiotic-bar"
            @click="applySignalFilter('antibiotic')"
          >
            <i :style="{ height: `${bar.percent}%` }" />
            <span>{{ bar.date }}</span>
          </button>
        </div>
        <div v-else class="visual-empty">抗菌强度待同步</div>
        <div v-if="antibioticTasks.length" class="antibiotic-task-list">
          <button
            v-for="task in antibioticTasks.slice(0, 3)"
            :key="`${task.hisPid}-${task.title}`"
            type="button"
            :class="['antibiotic-task', `prio-${task.priority}`]"
            @click="applySignalFilter('antibiotic')"
          >
            <strong>{{ task.patient || '患者' }}</strong>
            <span>{{ task.title }}</span>
          </button>
        </div>
        <div class="source-chip">{{ antibioticIntensity.source || '抗菌强度' }}</div>
      </article>

      <article class="visual-panel swimlane-panel">
        <div class="visual-panel-head">
          <span>医嘱闭环</span>
          <b>{{ orderSwimlanes.length }}人</b>
        </div>
        <div class="panel-subline">每床：告警→医嘱→执行→复查→结果</div>
        <div v-if="orderSwimlanes.length" class="swimlane-list">
          <button
            v-for="lane in orderSwimlanes"
            :key="`lane-${lane.patient_id}`"
            type="button"
            class="swimlane-row"
            @click="showVisualPatient(lane, 'order_gap')"
          >
            <strong>{{ lane.bed || '--' }}床</strong>
            <span v-for="step in lane.steps" :key="`${lane.patient_id}-${step.label}`" :class="`is-${step.status}`">{{ step.label }}</span>
          </button>
        </div>
        <div v-else class="visual-empty">暂无闭环泳道</div>
      </article>

      <article class="visual-panel lights-panel">
        <div class="visual-panel-head">
          <span>撤机灯</span>
          <b>{{ weaningLights.length }}人</b>
        </div>
        <div class="panel-subline">每床 5 项条件</div>
        <div class="light-list">
          <button
            v-for="row in weaningLights"
            :key="`wean-${row.patient_id}`"
            type="button"
            class="light-row"
            @click="showVisualPatient(row, 'weaning')"
          >
            <strong>{{ row.bed || '--' }}床</strong>
            <i v-for="light in row.lights" :key="light.label" :class="light.ok ? 'ok' : 'bad'" :title="light.label" />
          </button>
        </div>
      </article>

      <article class="visual-panel lights-panel">
        <div class="visual-panel-head">
          <span>转出灯</span>
          <b>{{ dischargeLights.length }}人</b>
        </div>
        <div class="light-list">
          <button
            v-for="row in dischargeLights"
            :key="`discharge-${row.patient_id}`"
            type="button"
            class="light-row"
            @click="showVisualPatient(row, 'discharge')"
          >
            <strong>{{ row.bed || '--' }}床</strong>
            <span class="light-percent">{{ row.percent || 0 }}%</span>
            <i v-for="light in row.lights" :key="light.label" :class="light.ok ? 'ok' : 'bad'" :title="light.label" />
          </button>
        </div>
      </article>

      <article class="visual-panel compact-panel">
        <div class="visual-panel-head">
          <span>抢救线</span>
          <b>{{ rescueTimeline.length }}</b>
        </div>
        <div v-if="rescueTimeline.length" class="rescue-line">
          <button v-for="item in rescueTimeline" :key="`${item.time}-${item.title}`" type="button" @click="applySignalFilter('rescue')">
            <i />
            <span>{{ item.title }}</span>
          </button>
        </div>
        <div v-else class="visual-empty">暂无抢救线索</div>
      </article>

      <article class="visual-panel compact-panel family-panel">
        <div class="visual-panel-head">
          <span>家属沟通</span>
          <b>{{ familyCards.length }}</b>
        </div>
        <div v-if="familyCards.length" class="family-grid">
          <button
            v-for="card in familyCards"
            :key="`family-${card.patient_id}`"
            type="button"
            @click="showVisualPatient(card, 'family')"
          >
            <strong>{{ card.bed || '--' }}床</strong>
            <em>{{ card.readiness || 0 }}%</em>
            <span>{{ card.task || '生成沟通卡' }}</span>
          </button>
        </div>
        <div v-else class="visual-empty">暂无沟通卡</div>
      </article>
    </section>

    <section ref="stickySectionRef" class="sticky-section">
      <div class="section-head">
        <div>
          <span class="panel-kicker">临床离不开的每日功能</span>
        </div>
      </div>
      <div class="feature-grid">
        <article v-for="feature in stickyFeatureCards" :key="feature.key" :class="['feature-panel', `tone-${feature.tone || 'info'}`]">
          <div class="feature-head">
            <div class="feature-meta">
              <span>{{ feature.owner }}</span>
              <b>{{ feature.totalCount }}项</b>
            </div>
            <strong>{{ feature.title }}</strong>
          </div>
          <div class="feature-list">
            <button
              v-for="item in feature.visibleItems"
              :key="`${feature.key}-${item.patient_id || item.title}-${item.detail}`"
              type="button"
              class="feature-item"
              @click="runFeatureAction(item, feature)"
            >
              <div>
                <strong>{{ item.displayTitle || item.title }}</strong>
              </div>
              <span>{{ item.action || feature.action }}</span>
            </button>
            <button
              v-if="feature.moreCount > 0"
              type="button"
              class="feature-more"
              @click="toggleFeatureExpanded(feature.key)"
            >
              {{ expandedFeatureKeys.has(feature.key) ? '收起列表' : `还有 ${feature.moreCount} 条，展开查看` }}
            </button>
          </div>
        </article>
      </div>
    </section>

    <section class="content-grid">
      <section class="queue-board">
        <div class="queue-board-head">
          <div>
            <span class="panel-kicker">优先队列</span>
            <strong>今日优先队列</strong>
            <small>按高危告警、未闭环、床位和最近事件排序</small>
          </div>
          <a-button size="small" ghost @click="loadHome">刷新</a-button>
        </div>
        <div v-if="loading" class="queue-loading">正在从 SmartCare 和告警闭环整理今日队列...</div>
        <div v-else-if="filteredPriorityQueue.length" class="patient-card-grid">
          <article v-for="record in filteredPriorityQueue" :key="record.patient_id" class="patient-task-card">
            <div class="patient-task-top">
              <RouterLink class="patient-link" :to="{ path: `/patient/${record.patient_id}`, query: route.query }" @click="selectPatient(record.patient_id, 'story')">
                {{ record.bed || '--' }}床 {{ record.name || '未知患者' }}
              </RouterLink>
              <span :class="['risk-pill', riskTone(record.risk_score)]">风险 {{ record.risk_score || 0 }}</span>
            </div>
            <div class="patient-task-metrics">
              <span>高危 {{ record.critical_alerts || 0 }}</span>
              <span>未闭环 {{ record.unacked_alerts || 0 }}</span>
              <span>{{ record.nursing_level || '护理级别待核' }}</span>
            </div>
            <div class="latest-alert">
              <span>最近</span>
              <strong>{{ record.latest_alert?.name || record.latest_alert?.alert_type || '暂无近期告警，可作为常规查房入口' }}</strong>
            </div>
            <div class="card-actions">
              <a-button type="primary" class="story-action primary" @click.stop="openStory(record.patient_id)">看事件链</a-button>
              <a-button class="story-action" @click.stop="openHandoff(record.patient_id)">交班摘要</a-button>
            </div>
          </article>
        </div>
        <div v-else class="queue-empty">
          <strong>当前没有形成高优先级队列</strong>
          <p>系统已经识别到 {{ cards.find((card: any) => card.key === 'patients')?.value || 0 }} 位在科患者，但近 24 小时告警与患者 ID 可能尚未闭合，或当前科室暂未产生需要优先处理的任务。</p>
          <div class="empty-actions">
            <a-button type="primary" ghost @click="loadHome">重新整理</a-button>
            <RouterLink :to="{ path: '/', query: route.query }">去患者总览</RouterLink>
            <RouterLink :to="{ path: '/admin/scanner-health', query: route.query }">看规则健康</RouterLink>
          </div>
        </div>
      </section>

      <div class="side-stack">
        <a-card v-if="selectedPatient" :bordered="false" class="panel story-inline-panel">
          <template #title>
            <div class="panel-title">
              <span>{{ selectedPatient.bed || '--' }}床 {{ selectedPatient.name || '患者' }}</span>
              <small>{{ inlinePanelTitle }}</small>
            </div>
          </template>
          <a-spin :spinning="storyLoading">
            <div class="inline-actions">
              <a-button type="primary" @click="goPatientDetail(selectedPatient.patient_id)">进入患者详情</a-button>
              <a-button @click="openStory(selectedPatient.patient_id)">事件链</a-button>
              <a-button @click="openHandoff(selectedPatient.patient_id)">交班摘要</a-button>
            </div>
            <div v-if="featureDetail" class="feature-detail-panel inline">
              <div class="feature-detail-head">
                <span>{{ featureDetail.owner || '临床任务' }}</span>
                <strong>{{ featureDetail.title }}</strong>
              </div>
              <p>{{ featureDetail.detail }}</p>
              <div class="feature-detail-checklist">
                <div v-for="line in featureDetail.checklist" :key="line">{{ line }}</div>
              </div>
              <button v-if="featureTaskId" type="button" class="task-close-btn" @click="closeCurrentFeatureTask">完成任务</button>
            </div>
            <div v-if="handoffText" class="handoff-text inline">{{ dedupedHandoffText }}</div>
            <div v-else-if="story?.summary" class="story-summary inline">{{ story.summary }}</div>
            <div class="treatment-card inline">
              <div class="treatment-card__head">
                <span>AI 建议剂量</span>
                <button type="button" :disabled="treatmentLoading || !selectedPatient?.patient_id" @click="loadTreatmentRecommendation(selectedPatient.patient_id)">
                  {{ treatmentLoading ? '计算中' : '刷新' }}
                </button>
              </div>
              <div v-if="treatmentRecommendation?.available" class="treatment-card__body">
                <strong>{{ treatmentRecommendation.recommendation?.action || '建议待复核' }}</strong>
                <div class="treatment-metrics">
                  <span>补液 {{ treatmentRecommendation.recommendation?.fluid_bolus_ml ?? 0 }}mL</span>
                  <span>去甲 {{ treatmentRecommendation.recommendation?.norepinephrine_ug_kg_min ?? '--' }} μg/kg/min</span>
                  <span>Q差 {{ treatmentRecommendation.q_value_delta ?? '--' }}</span>
                </div>
              </div>
              <div v-else class="treatment-card__empty">
                {{ treatmentRecommendation?.reason || '选择患者后显示 CQL 策略建议。' }}
              </div>
            </div>
            <div v-if="storyClusters.length" class="story-list inline">
              <div v-for="cluster in storyClusters" :key="`inline-${cluster.start_time}-${cluster.headline}`" class="story-cluster">
                <strong>{{ clinicalText(cluster.headline) || '临床事件簇' }}</strong>
                <p>{{ clinicalText(cluster.summary) }}</p>
              </div>
            </div>
            <div v-else-if="!storyLoading" class="story-empty inline">
              <strong>暂未形成事件簇</strong>
              <p>系统已打开该患者任务面板。可以先进入患者详情查看完整生命体征、检验、用药和告警记录。</p>
            </div>
          </a-spin>
        </a-card>

        <a-card :bordered="false" class="panel">
          <template #title>
            <div class="panel-title">
              <span>{{ roleLabel }}作战卡</span>
              <small>把系统价值落到每天动作</small>
            </div>
          </template>
          <div class="playbook">
            <div v-for="item in playbook" :key="item.title" class="playbook-item">
              <strong>{{ item.title }}</strong>
              <p>{{ item.detail }}</p>
            </div>
          </div>
        </a-card>

        <a-card :bordered="false" class="panel">
          <template #title>
            <div class="panel-title">
              <span>规则复核线索</span>
              <small>主任/质控可直接追踪噪音规则</small>
            </div>
          </template>
          <div v-if="scannerReview.length" class="scanner-list">
            <div v-for="row in scannerReview" :key="row.scanner_name || row.name" class="scanner-row">
              <strong>{{ row.scanner_name || row.name }}</strong>
              <span>阳性预测值 {{ pct(row.ppv) }} · 覆盖率 {{ pct(row.override_rate) }}</span>
            </div>
          </div>
          <a-empty v-else :image="simpleImage" description="暂无需人工复核的规则" />
        </a-card>
      </div>
    </section>

    <section class="action-grid">
      <article class="action-panel nurse-panel">
        <div class="action-panel-head">
          <span>护士使用</span>
          <strong>护士班内待办</strong>
          <small>从高危未闭环、护理级别和风险场景自动整理</small>
        </div>
        <div v-if="nursingTasks.length" class="action-list">
          <div v-for="task in nursingTasks" :key="`${task.patient_id}-${task.task_type}-${task.title}`" :class="['action-item', `tone-${task.tone || 'info'}`]">
            <div>
              <strong>{{ task.bed || '--' }}床 {{ task.name || '未知患者' }} · {{ task.title }}</strong>
              <p>{{ task.detail }}</p>
            </div>
            <a-button size="small" class="story-action compact" @click.stop="openStory(task.patient_id)">看事件</a-button>
          </div>
        </div>
        <div v-else class="mini-empty">暂无护理高优先级待办，可从优先队列抽查交班摘要。</div>
      </article>

      <article class="action-panel doctor-panel">
        <div class="action-panel-head">
          <span>医生使用</span>
          <strong>医生查房缺口</strong>
          <small>把告警转成查房时要补齐的证据链</small>
        </div>
        <div v-if="doctorGaps.length" class="action-list">
          <div v-for="gap in doctorGaps" :key="`${gap.patient_id}-${gap.gap_type}-${gap.title}`" :class="['action-item', `tone-${gap.tone || 'info'}`]">
            <div>
              <strong>{{ gap.title }}</strong>
              <p>{{ gap.detail }}</p>
            </div>
            <a-button size="small" class="story-action compact" @click.stop="openRoundingSheet(gap.patient_id)">开查房单</a-button>
          </div>
        </div>
        <div v-else class="mini-empty">暂无明确查房缺口，建议按风险分数打开事件链做常规核对。</div>
      </article>

      <article class="action-panel quality-panel">
        <div class="action-panel-head">
          <span>管理者使用</span>
          <strong>质控 / 主任晨会</strong>
          <small>{{ directorDigest.headline || '把闭环、噪音规则和典型病例变成晨会材料' }}</small>
        </div>
        <div class="digest-strip">
          <span>30d触发 {{ directorDigest.total_fired_30d || 0 }}</span>
          <span>规则复核 {{ directorDigest.review_required || 0 }}</span>
          <span>阳性预测值 {{ pct(directorDigest.avg_ppv) }}</span>
        </div>
        <div v-if="qualityActions.length" class="action-list compact">
          <div v-for="action in qualityActions" :key="action.title" :class="['action-item', `tone-${action.tone || 'info'}`]">
            <div>
              <strong>{{ action.title }}</strong>
              <p>{{ action.detail }}</p>
            </div>
            <b>{{ action.metric }}</b>
          </div>
        </div>
        <div v-else class="mini-empty">暂无质控动作，适合抽查规则健康和典型病例闭环。</div>
      </article>
    </section>

    <a-drawer v-model:open="storyOpen" width="860px" title="患者事件链 / 交班摘要" class="story-drawer">
      <a-spin :spinning="storyLoading">
        <div v-if="featureDetail" class="feature-detail-panel">
          <div class="feature-detail-head">
            <span>{{ featureDetail.owner || '临床任务' }}</span>
            <strong>{{ featureDetail.title }}</strong>
          </div>
          <p>{{ featureDetail.detail }}</p>
          <div class="feature-detail-checklist">
            <div v-for="line in featureDetail.checklist" :key="line">{{ line }}</div>
          </div>
          <button v-if="featureTaskId" type="button" class="task-close-btn" @click="closeCurrentFeatureTask">完成任务</button>
        </div>
        <div v-if="handoffText" class="handoff-text">{{ dedupedHandoffText }}</div>
        <div v-if="story?.summary" class="story-summary">{{ story.summary }}</div>
        <div v-if="!storyLoading && !handoffText && story && !storyClusters.length" class="story-empty">
          <strong>{{ story.bed || '--' }}床 {{ story.patient_name || '患者' }} 暂未形成事件簇</strong>
          <p>已经完成点击和接口加载，但过去窗口内没有可聚类事件。系统匹配过的ID：{{ (story.matched_ids || []).join(' / ') || '无' }}</p>
        </div>
        <div v-if="!storyLoading && !story && !handoffText" class="story-empty">
          <strong>请选择一位患者查看事件链或交班摘要</strong>
          <p>点击患者卡片底部按钮后，这里会显示过去 24 小时事件链。</p>
        </div>
        <div class="story-list">
          <div v-for="cluster in storyClusters" :key="`${cluster.start_time}-${cluster.headline}`" class="story-cluster">
            <strong>{{ clinicalText(cluster.headline) || '临床事件簇' }}</strong>
            <p>{{ clinicalText(cluster.summary) }}</p>
          </div>
        </div>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import {
  Alert as AAlert,
  Button as AButton,
  Card as ACard,
  Drawer as ADrawer,
  Empty as AEmpty,
  Spin as ASpin,
  message,
} from 'ant-design-vue'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { closeClinicalTask, getClinicalPatientHandoff, getClinicalPatientStory, getClinicalRoleHome, getTreatmentRecommendation, postClinicalTask } from '../api'
import HumanBodyDiagram from '../components/common/HumanBodyDiagram.vue'
import OrganRiskRadar from '../components/common/OrganRiskRadar.vue'

const route = useRoute()
const router = useRouter()
const loading = ref(false)
const home = ref<any>(null)
const storyOpen = ref(false)
const storyLoading = ref(false)
const story = ref<any>(null)
const handoffText = ref('')
const selectedPatient = ref<any>(null)
const activeStoryMode = ref<'story' | 'handoff'>('story')
const featureDetail = ref<any>(null)
const featureTaskId = ref('')
const treatmentRecommendation = ref<any>(null)
const treatmentLoading = ref(false)
const expandedFeatureKeys = ref(new Set<string>())
const stickySectionRef = ref<HTMLElement | null>(null)
const activeSignalFilter = ref('')
const simpleImage = AEmpty.PRESENTED_IMAGE_SIMPLE
let homeRequestSeq = 0
const roleHomeCache = new Map<string, any>()
const roleHomeInflight = new Map<string, Promise<any>>()

function firstRouteQuery(...keys: string[]) {
  for (const key of keys) {
    const value = route.query[key]
    const text = String(Array.isArray(value) ? value[0] : value || '').trim()
    if (text) return text
  }
  return ''
}

const routeUserName = computed(() => firstRouteQuery('userName', 'useName', 'username', 'user_id', 'userId'))
const routeRole = computed(() => firstRouteQuery('role', 'userRole'))
const routeDeptCode = computed(() => firstRouteQuery('dept_code', 'deptCode'))
const routeDept = computed(() => firstRouteQuery('dept', 'department'))
const cards = computed(() => home.value?.cards || [])
const priorityQueue = computed(() => home.value?.priority_queue || [])
const playbook = computed(() => home.value?.playbook || [])
const scannerReview = computed(() => home.value?.scanner_review || [])
const storyClusters = computed(() => story.value?.clusters || [])
const nursingTasks = computed(() => home.value?.nursing_tasks || [])
const doctorGaps = computed(() => home.value?.doctor_gaps || [])
const qualityActions = computed(() => home.value?.quality_actions || [])
const directorDigest = computed(() => home.value?.director_digest || {})
const isDirector = computed(() => home.value?.role === 'director')
const showWorkflowStrip = computed(() => !isDirector.value)
const icuDayFlow = computed(() => home.value?.icu_day_flow || [])
const aiToolbox = computed(() => home.value?.ai_toolbox || [])
const stickyFeatures = computed(() => home.value?.sticky_features || {})
const roleDistribution = computed(() => home.value?.role_distribution || [])
const openTasks = computed(() => home.value?.open_tasks || {})
const openTaskItems = computed(() => openTasks.value?.items || [])
const openTaskTotal = computed(() => openTasks.value?.total || openTaskItems.value.length || 0)
const clinicalVisuals = computed(() => home.value?.clinical_visuals || {})
const bedHeatmap = computed(() => clinicalVisuals.value?.bed_heatmap || [])
const nursingOmissions = computed(() => clinicalVisuals.value?.nursing_omissions || [])
const nursingCompletion = computed(() => clinicalVisuals.value?.nursing_completion || {})
const orderSwimlanes = computed(() => clinicalVisuals.value?.order_swimlanes || [])
const antibioticIntensity = computed(() => clinicalVisuals.value?.antibiotic_intensity || {})
const antibioticSummary = computed(() => antibioticIntensity.value?.summary || {})
const antibioticPatients = computed(() => antibioticIntensity.value?.patients || [])
const antibioticTasks = computed(() => antibioticIntensity.value?.tasks || [])
const weaningLights = computed(() => clinicalVisuals.value?.weaning_lights || [])
const dischargeLights = computed(() => clinicalVisuals.value?.discharge_lights || [])
const rescueTimeline = computed(() => clinicalVisuals.value?.rescue_timeline || [])
const familyCards = computed(() => clinicalVisuals.value?.family_cards || [])
const nursingTodoCount = computed(() => nursingOmissions.value.filter((item: any) => item.status === 'todo').length)
const activeAntibioticPatient = computed(() => {
  const patient = selectedPatient.value
  if (!patient?.hisPid && !patient?.patient_id) return null
  const label = `${patient?.bed || ''}床`
  return antibioticPatients.value.find((row: any) =>
    String(row.hisPid || '') === String(patient.hisPid || '') ||
    String(row.patient || '').includes(label)
  ) || null
})
const activeAntibioticSummary = computed(() => activeAntibioticPatient.value?.summary || antibioticSummary.value || {})
const activeAntibioticRows = computed(() => activeAntibioticPatient.value?.daily || antibioticIntensity.value?.daily || [])
const activeAntibioticBars = computed(() => {
  const rows = activeAntibioticRows.value || []
  const max = Math.max(...rows.map((row: any) => Number(row.value || 0)), 1)
  return rows.map((row: any) => ({
    ...row,
    percent: Math.max(8, Math.round((Number(row.value || 0) / max) * 100)),
  }))
})
const antibioticPanelTitle = computed(() => activeAntibioticPatient.value ? `${selectedPatient.value?.bed || '--'}床 抗菌药强度` : '全科抗菌药强度')
const filteredPriorityQueue = computed(() => {
  const rows = priorityQueue.value || []
  const key = activeSignalFilter.value
  if (!key) return rows
  const roleKeys: Record<string, string[]> = {
    nurse: ['护理', 'nursing', '管路', '尿量', '压疮', '谵妄', '镇静'],
    doctor: ['查房', '医嘱', '感染', '撤机', '抗菌', '肾', '呼吸', '循环'],
    director: ['未闭环', '规则', '质控', '高危'],
    focus: ['高危', '未闭环'],
    nursing: ['护理', '管路', '尿量', '压疮', '谵妄', '镇静'],
    quality: ['未闭环', '重复', '规则'],
    antibiotic: ['抗菌', '感染', '脓毒'],
    rescue: ['抢救', '休克', '循环', '乳酸'],
    respiratory: ['呼吸', '氧', 'vent', '撤机', '拔管', 'ards', 'spo2'],
    circulatory: ['循环', '休克', '血压', '乳酸', 'sepsis', '脓毒'],
    renal: ['肾', '尿量', '肌酐', 'aki', 'crrt'],
    coagulation: ['凝血', '出血', '血小板', '抗凝'],
    neurologic: ['谵妄', '神经', '意识', '镇静', 'rass'],
    hepatic: ['肝', '胆红素', '转氨酶'],
  }
  const tokens = roleKeys[key] || [key]
  const matched = rows.filter((row: any) => tokens.some((token) => patientSignalText(row).includes(String(token).toLowerCase())))
  return matched.length ? matched : rows
})
const directorMorningTiles = computed(() => [
  { key: 'night', label: '昨夜事件', value: priorityQueue.value.filter((row: any) => Number(row.risk_score || 0) > 0).length, hint: '看事件链', tone: 'info' },
  { key: 'open', label: '未闭环', value: cards.value.find((card: any) => card.key === 'unacked')?.value || 0, hint: '筛选床位', tone: Number(cards.value.find((card: any) => card.key === 'unacked')?.value || 0) ? 'warning' : 'stable' },
  { key: 'discharge', label: '可转出', value: dischargeLights.value.filter((row: any) => (row.lights || []).every((light: any) => light.ok)).length, hint: '看转出灯', tone: 'stable' },
  { key: 'antibiotic', label: '抗菌药', value: antibioticSummary.value.today || 0, hint: '强度', tone: antibioticIntensity.value?.available ? 'info' : 'warning' },
  { key: 'rules', label: '规则噪音', value: scannerReview.value.length, hint: '规则健康', tone: scannerReview.value.length ? 'warning' : 'stable' },
  { key: 'case', label: '典型病例', value: priorityQueue.value[0]?.bed || '--', hint: priorityQueue.value[0]?.name || '暂无', tone: priorityQueue.value.length ? 'high' : 'stable' },
])
const inlinePanelTitle = computed(() => {
  if (featureDetail.value?.title) return '任务详情已经展开'
  return activeStoryMode.value === 'handoff' ? '交班摘要已经展开' : '事件链已经展开'
})
const dedupedHandoffText = computed(() => dedupeHandoffLines(handoffText.value))
const stickyFeatureCards = computed(() => {
  const features = stickyFeatures.value || {}
  const fallbackPatient = priorityQueue.value?.[0] || {}
  const fallbackItem = (title: string, detail: string, kind = 'handoff') => [{
    patient_id: fallbackPatient.patient_id || '',
    title,
    detail,
    action: kind === 'scanner_review' ? '打开规则健康' : kind === 'story' ? '看事件链' : '生成摘要',
    kind,
    tone: 'info',
  }]
  const compactItems = (items: any[], mode: string) => items.map((item: any) => ({
    ...item,
    displayTitle: compactTitle(item, mode),
    displayDetail: compactDetail(item, mode),
  }))
  const cards = [
    {
      key: 'todays_focus',
      owner: '全员',
      title: '今日重点患者榜',
      subtitle: '打开系统先知道谁最危险、谁最容易漏。',
      action: '看事件链',
      detailMode: 'story',
      tone: 'danger',
      items: compactItems(features.todays_focus?.length ? features.todays_focus : fallbackItem('今日重点患者榜', '等待患者与告警同步后自动生成高危床位排序。', 'story'), 'story'),
    },
    {
      key: 'rounding_checklist',
      owner: '医生',
      title: '查房问题清单',
      subtitle: '把告警翻译成诊疗问题，而不是让医生猜。',
      action: '看代表病例',
      detailMode: 'rounding',
      tone: 'warn',
      items: compactItems(features.rounding_checklist?.length ? features.rounding_checklist : fallbackItem('每日查房五问', '减镇静、能否撤机、抗菌药降阶梯、营养活动、能否转出 ICU。'), 'rounding'),
    },
    {
      key: 'nursing_radar',
      owner: '护士/护士长',
      title: '护士任务雷达',
      subtitle: '压疮、管路、镇静、谵妄、出入量、感染执行一起看。',
      action: '看护理事件',
      detailMode: 'nursing',
      tone: 'stable',
      items: compactItems(features.nursing_radar?.length ? features.nursing_radar : fallbackItem('护理风险雷达', '暂无高优先级护理待办，建议抽查高护理级别床位。', 'story'), 'nursing'),
    },
    {
      key: 'order_gaps',
      owner: '医生',
      title: '医嘱缺口检查',
      subtitle: '自动找“该有但没有”的医嘱与复查。',
      action: '看缺口',
      detailMode: 'order_gap',
      tone: 'warn',
      items: compactItems(features.order_gaps?.length ? features.order_gaps : fallbackItem('医嘱缺口自动检查', '固定检查 VTE、营养、镇静目标、抗菌药疗程和转出条件。'), 'order_gap'),
    },
    {
      key: 'discharge_candidates',
      owner: '主任/医生',
      title: '转出 ICU 评估',
      subtitle: '床位紧张时，系统先给出可评估人群。',
      action: '看依据',
      detailMode: 'discharge',
      tone: 'stable',
      items: compactItems(features.discharge_candidates?.length ? features.discharge_candidates : fallbackItem('转出 ICU 评估池', '暂未形成低风险候选，建议主任查房确认床位占用延迟。'), 'discharge'),
    },
    {
      key: 'family_summaries',
      owner: '医生',
      title: '家属沟通摘要',
      subtitle: '把专业病情变成可解释的沟通稿。',
      action: '生成摘要',
      detailMode: 'family',
      tone: 'info',
      items: compactItems(features.family_summaries?.length ? features.family_summaries : fallbackItem('家属沟通摘要', '生成目前问题、今天变化、主要风险、下一步计划的白话版本。'), 'family'),
    },
    {
      key: 'medication_safety',
      owner: '医生/药师',
      title: '用药安全管家',
      subtitle: '盯肾功能剂量、抗菌药疗程、镇静、抗凝和相互作用。',
      action: '看风险',
      detailMode: 'medication',
      tone: 'warn',
      items: compactItems(features.medication_safety?.length ? features.medication_safety : fallbackItem('用药安全管家', '每日复核肾功能剂量、抗菌药疗程、血管活性药、镇静镇痛、胰岛素和抗凝。', 'story'), 'medication'),
    },
    {
      key: 'event_previews',
      owner: '医生/护士',
      title: '24小时不良事件预演',
      subtitle: '如果这个患者要出事，最可能卡在哪里。',
      action: '看预演',
      detailMode: 'preview',
      tone: 'danger',
      items: compactItems(features.event_previews?.length ? features.event_previews : fallbackItem('不良事件预演', '等待足够事件链后，系统会给出未来24小时最可能风险。', 'story'), 'preview'),
    },
    {
      key: 'director_dashboard',
      owner: '主任/质控',
      title: '主任质控驾驶舱',
      subtitle: '晨会、质控会、规则复核都有抓手。',
      action: '打开规则健康',
      detailMode: 'scanner_review',
      tone: 'stable',
      items: compactItems(features.director_dashboard?.length ? features.director_dashboard : fallbackItem('主任质控驾驶舱', '汇总规则健康、告警闭环、典型病例和延迟响应。', 'scanner_review'), 'scanner_review'),
    },
  ]
  const role = home.value?.role || 'doctor'
  const orderMap: Record<string, string[]> = {
    nurse: ['nursing_radar', 'todays_focus', 'family_summaries', 'event_previews', 'order_gaps', 'rounding_checklist', 'medication_safety', 'discharge_candidates', 'director_dashboard'],
    head_nurse: ['nursing_radar', 'director_dashboard', 'todays_focus', 'event_previews', 'order_gaps', 'family_summaries', 'rounding_checklist', 'medication_safety', 'discharge_candidates'],
    doctor: ['todays_focus', 'rounding_checklist', 'order_gaps', 'medication_safety', 'discharge_candidates', 'event_previews', 'family_summaries', 'nursing_radar', 'director_dashboard'],
    director: ['director_dashboard', 'todays_focus', 'discharge_candidates', 'medication_safety', 'event_previews', 'order_gaps', 'nursing_radar', 'rounding_checklist', 'family_summaries'],
  }
  const order = orderMap[role] ?? orderMap.doctor ?? []
  return cards.sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key)).map((card) => {
    const items = Array.isArray(card.items) ? card.items : []
    const expanded = expandedFeatureKeys.value.has(card.key)
    return {
      ...card,
      visibleItems: expanded ? items : items.slice(0, 2),
      moreCount: Math.max(items.length - 2, 0),
      totalCount: items.length,
    }
  })
})
const visualTaskMix = computed(() => [
  { key: 'focus', label: '重点', value: stickyFeatures.value?.todays_focus?.length || 0, color: '#fb7185' },
  { key: 'nursing', label: '护理', value: stickyFeatures.value?.nursing_radar?.length || 0, color: '#5eead4' },
  { key: 'doctor', label: '查房', value: stickyFeatures.value?.rounding_checklist?.length || 0, color: '#60a5fa' },
  { key: 'quality', label: '质控', value: stickyFeatures.value?.director_dashboard?.length || 0, color: '#fbbf24' },
])
const visualTotalTasks = computed(() => visualTaskMix.value.reduce((sum, item) => sum + Number(item.value || 0), 0))
const donutStyle = computed(() => {
  const total = Math.max(visualTotalTasks.value, 1)
  let cursor = 0
  const parts = visualTaskMix.value.map((item) => {
    const start = cursor
    cursor += (Number(item.value || 0) / total) * 100
    return `${item.color} ${start}% ${cursor}%`
  })
  return { background: `conic-gradient(${parts.join(', ') || '#123044 0 100%'})` }
})
const visualRoleBars = computed(() => {
  const colors: Record<string, string> = {
    nurse: '#5eead4',
    doctor: '#60a5fa',
    head_nurse: '#fbbf24',
    director: '#fb7185',
  }
  const fallbackRows = [
    { key: 'nurse', label: '护士', value: nursingTasks.value.length },
    { key: 'doctor', label: '医生', value: doctorGaps.value.length + (stickyFeatures.value?.order_gaps?.length || 0) },
    { key: 'head_nurse', label: '护士长', value: qualityActions.value.length },
    { key: 'director', label: '主任', value: scannerReview.value.length + (directorDigest.value?.review_required || 0) },
  ]
  const sourceRows = roleDistribution.value.length ? roleDistribution.value : fallbackRows
  const rows = sourceRows.map((row: any) => ({ ...row, color: colors[row.key] || '#67e8f9' }))
  const max = Math.max(...rows.map((row: any) => Number(row.value || 0)), 1)
  return rows.map((row: any) => ({ ...row, percent: Math.max(8, Math.round((Number(row.value || 0) / max) * 100)) }))
})
const visualOrganStates = computed(() => {
  const states: Record<string, string> = {
    neurologic: 'normal',
    respiratory: 'normal',
    circulatory: 'normal',
    hepatic: 'normal',
    coagulation: 'normal',
    renal: 'normal',
  }
  const target = selectedPatient.value?.patient_id ? findPatientInHome(String(selectedPatient.value.patient_id)) : null
  const text = target
    ? patientSignalText(target)
    : JSON.stringify({
      alerts: priorityQueue.value.slice(0, 12),
      tasks: nursingTasks.value.slice(0, 12),
      gaps: doctorGaps.value.slice(0, 8),
    }).toLowerCase()
  if (/呼吸|氧|vent|撤机|拔管|ards|spo2/.test(text)) states.respiratory = 'high'
  if (/循环|休克|血压|乳酸|sepsis|脓毒|升压/.test(text)) states.circulatory = 'critical'
  if (/肾|尿量|肌酐|aki|crrt|renal/.test(text)) states.renal = 'high'
  if (/凝血|出血|血小板|抗凝|dic/.test(text)) states.coagulation = 'warning'
  if (/谵妄|神经|意识|镇静|rass|delir/.test(text)) states.neurologic = 'warning'
  if (/肝|胆红素|转氨酶|hepatic|liver/.test(text)) states.hepatic = 'warning'
  return states
})
const visualRadarScores = computed(() => ['neurologic', 'respiratory', 'circulatory', 'hepatic', 'coagulation', 'renal'].map((key) => ({
  normal: 0,
  warning: 1,
  high: 2,
  critical: 3,
}[visualOrganStates.value[key] || 'normal'] || 0)))
const visualOrganList = computed(() => [
  { key: 'respiratory', label: '呼吸', severity: visualOrganStates.value.respiratory },
  { key: 'circulatory', label: '循环', severity: visualOrganStates.value.circulatory },
  { key: 'renal', label: '肾脏', severity: visualOrganStates.value.renal },
  { key: 'coagulation', label: '凝血', severity: visualOrganStates.value.coagulation },
  { key: 'neurologic', label: '神经', severity: visualOrganStates.value.neurologic },
  { key: 'hepatic', label: '肝脏', severity: visualOrganStates.value.hepatic },
].map((item) => ({
  ...item,
  text: ({
    normal: '稳',
    warning: '黄',
    high: '橙',
    critical: '红',
  } as Record<string, string>)[item.severity || 'normal'] || '稳',
})))
const visualMetricBadges = computed(() => [
  { key: 'high', label: '高危', value: String(cards.value.find((card: any) => card.key === 'high_alerts')?.value || 0), anchor: 'respiratory', tone: 'high' },
  { key: 'open', label: '未闭环', value: String(cards.value.find((card: any) => card.key === 'unacked')?.value || 0), anchor: 'circulatory', tone: 'critical' },
  { key: 'patients', label: '在科', value: String(cards.value.find((card: any) => card.key === 'patients')?.value || 0), anchor: 'renal', tone: 'normal' },
])
const organPanelTitle = computed(() => selectedPatient.value?.patient_id ? `${selectedPatient.value.bed || '--'}床器官风险` : '全科器官风险')
const labelMap: Record<string, string> = {
  clinical_document: '临床文书记录',
  prone_position_monitor: '俯卧位通气监测',
  'PRE-DELIRIC': '谵妄高风险',
  'pre-deliric': '谵妄高风险',
  DELIRIC: '谵妄风险',
  deliric: '谵妄风险',
  SOFA: 'SOFA 器官功能评分',
  qSOFA: 'qSOFA 感染风险评分',
  sofa: 'SOFA 器官功能评分',
  qsofa: 'qSOFA 感染风险评分',
  sepsis: '脓毒症风险',
  septic_shock: '脓毒性休克风险',
  ards: 'ARDS 风险',
  aki: '急性肾损伤风险',
  ventilator_asynchrony: '呼吸机不同步',
  driving_pressure: '驱动压偏高',
  mechanical_power: '机械功率升高',
  lung_protective_ventilation: '肺保护性通气未达标',
  post_extubation_failure_risk: '拔管后失败风险',
  extubation_failure_risk: '拔管失败风险',
  weaning: '撤机评估',
  pplat_high: '平台压升高',
}

const roleLabel = computed(() => ({
  nurse: '护士',
  head_nurse: '护士长',
  doctor: '医生',
  director: '主任',
}[home.value?.role as string] || '临床'))

const accountLabel = computed(() => home.value?.account?.trueName || home.value?.account?.display_name || home.value?.account?.userName || routeUserName.value || '未识别账号')
const scopeLabel = computed(() => home.value?.account?.dept || routeDept.value || home.value?.account?.dept_code || routeDeptCode.value || '当前科室')

function pct(value: any) {
  const num = Number(value || 0)
  return `${Math.round(num * 100)}%`
}

function riskTone(value: any) {
  const score = Number(value || 0)
  if (score >= 8) return 'risk-high'
  if (score >= 4) return 'risk-mid'
  return 'risk-low'
}

function clinicalText(value: any) {
  let text = String(value || '').trim()
  if (!text) return ''
  Object.entries(labelMap)
    .sort(([a], [b]) => b.length - a.length)
    .forEach(([key, label]) => {
      text = text.split(key).join(label)
    })
  text = text.split('->').join('→').split('_').join(' ')
  return text
}

function compactTitle(item: any, mode: string) {
  const bed = String(item?.bed || '').trim()
  const name = String(item?.name || '').trim()
  const title = String(item?.title || '').trim()
  if (bed && name && !title.includes(bed)) return `${bed}床 ${name}`
  if (mode === 'rounding') return title.replace(/（.*?）/g, '') || '查房问题'
  if (mode === 'order_gap') return title.replace(/自动检查/g, '') || '医嘱缺口'
  if (mode === 'preview') return title.replace(/^未来24小时最可能风险：/, '') || '风险预演'
  return title || '临床任务'
}

function compactDetail(item: any, mode: string) {
  const detail = String(item?.detail || '').trim()
  const presets: Record<string, string> = {
    story: '优先看，避免漏掉高危床位。',
    rounding: '查房时核对证据和下一步。',
    nursing: '班内优先巡视与记录。',
    order_gap: '确认是否缺复查或医嘱。',
    discharge: '核对是否具备转出条件。',
    family: '生成可对家属解释的话。',
    medication: '复核剂量、疗程和相互作用。',
    preview: '提前布置观察和复查。',
    scanner_review: '用于晨会和质控复盘。',
  }
  if (!detail) return presets[mode] || '点击查看详情。'
  if (mode === 'story') {
    const high = detail.match(/高危\s*\d+\s*条/)
    const unclosed = detail.match(/未闭环\s*\d+\s*条/)
    return [high?.[0], unclosed?.[0]].filter(Boolean).join('，') || presets.story
  }
  return presets[mode] || detail.slice(0, 18)
}

function shortTaskText(value: any, max = 34) {
  const text = clinicalText(value).replace(/\s+/g, ' ').trim()
  return text.length > max ? `${text.slice(0, max)}...` : text
}

function dedupeHandoffLines(value: any) {
  const seen = new Set<string>()
  const result: string[] = []
  String(value || '').split(/\r?\n/).forEach((line) => {
    const normalized = line.replace(/^-\s*/, '').trim()
    if (normalized && seen.has(normalized)) return
    if (normalized) seen.add(normalized)
    result.push(clinicalText(line))
  })
  return result.join('\n')
}

function findPatientInHome(patientId: string) {
  const id = String(patientId || '')
  const rows = [
    ...priorityQueue.value,
    ...nursingTasks.value,
    ...doctorGaps.value,
    ...bedHeatmap.value,
    ...orderSwimlanes.value,
    ...weaningLights.value,
    ...dischargeLights.value,
    ...familyCards.value,
  ]
  return rows.find((row: any) => String(row?.patient_id || '') === id) || { patient_id: id, name: '患者', bed: '--' }
}

function selectPatient(patientId: string, mode: 'story' | 'handoff') {
  selectedPatient.value = findPatientInHome(patientId)
  activeStoryMode.value = mode
  void loadTreatmentRecommendation(patientId)
}

async function loadTreatmentRecommendation(patientId: string) {
  const id = String(patientId || '')
  if (!id) return
  treatmentLoading.value = true
  try {
    const res = await getTreatmentRecommendation(id)
    treatmentRecommendation.value = res.data || null
  } catch (error: any) {
    treatmentRecommendation.value = { available: false, reason: error?.message || 'AI 治疗策略接口暂不可用' }
  } finally {
    treatmentLoading.value = false
  }
}

function patientSignalText(row: any) {
  return JSON.stringify(row || {}).toLowerCase()
}

function checklistForMode(mode: string, item: any) {
  const patientLine = item?.bed || item?.name ? `关联患者：${item?.bed || '--'}床 ${item?.name || '患者'}` : ''
  const detail = String(item?.detail || '').trim()
  const map: Record<string, string[]> = {
    story: ['按时间顺序查看过去24小时关键事件。', '确认高危告警是否已有医嘱、护理执行或病程记录。', '必要时进入患者详情核对原始数据。'],
    rounding: ['查房时先确认当前主要问题是否变化。', '核对证据链：检验、生命体征、用药、管路和护理记录。', '把缺失复查或医嘱补到今日计划。'],
    nursing: ['先确认患者现场状态和监护趋势。', '复核管路、皮肤、镇静、谵妄、出入量和执行记录。', '交班前把未完成事项继续留给下一班。'],
    order_gap: ['确认系统提示是否确实适用于该患者。', '核对“该有但没有”的复查、预防、治疗或记录。', '由医生决定是否补开医嘱，系统不自动下医嘱。'],
    discharge: ['核对循环、氧合、意识、管路和高级生命支持是否稳定。', '确认护理级别和普通病区承接能力。', '主任或上级医生最终确认是否转出。'],
    family: ['用家属能听懂的话说明目前主要问题。', '说明今天比昨天好转、恶化或持平的地方。', '讲清下一步计划和最需要警惕的风险。'],
    medication: ['复核肾功能、肝功能和 CRRT 状态。', '检查抗菌药疗程、剂量、TDM 和相互作用。', '关注镇静镇痛、抗凝、胰岛素、血管活性药变化。'],
    preview: ['如果未来24小时恶化，先想最可能原因。', '提前布置复查、监测频率和护理观察点。', '把预案写进交班，减少夜班临时追数据。'],
  }
  const checklist = map[mode] ?? map.story ?? []
  return [patientLine, ...checklist, detail].filter(Boolean)
}

async function showFeatureDetail(item: any, feature: any) {
  const mode = String(feature?.detailMode || item?.kind || 'story')
  const patientId = String(item?.patient_id || firstPatientId())
  if (patientId) selectPatient(patientId, mode === 'story' ? 'story' : 'handoff')
  else selectedPatient.value = { patient_id: '', name: '暂无患者', bed: '--' }
  featureDetail.value = {
    owner: feature?.owner,
    title: `${feature?.title || '临床任务'}：${shortTaskText(item?.title || '任务详情', 24)}`,
    detail: shortTaskText(item?.detail || feature?.subtitle || '系统已整理该任务的临床核对重点。', 56),
    checklist: checklistForMode(mode, item),
  }
  featureTaskId.value = ''
  try {
    const { data } = await postClinicalTask({
      patient_id: patientId,
      bed: item?.bed,
      name: item?.name,
      module: 'clinical_workflow',
      task_type: mode,
      title: item?.title || feature?.title || '临床任务',
      detail: item?.detail || feature?.subtitle || '',
      priority: item?.priority || item?.tone || 'medium',
      source: 'ICU智能协同工作台',
    })
    featureTaskId.value = data?.task?.task_id || ''
  } catch {
    message.warning('任务已打开，但写入闭环记录失败')
  }
  storyOpen.value = true
  storyLoading.value = false
  handoffText.value = ''
  story.value = null
}

async function closeCurrentFeatureTask() {
  if (!featureTaskId.value) return
  await closeClinicalTask(featureTaskId.value, { outcome: '已完成' })
  message.success('任务已闭环')
  featureTaskId.value = ''
  await loadHome()
}

function openExistingTask(task: any) {
  const patientId = String(task?.patient_id || '')
  if (patientId) selectPatient(patientId, 'handoff')
  featureTaskId.value = task?.task_id || ''
  featureDetail.value = {
    owner: task?.module_label || '临床任务',
    title: `${task?.bed_label || task?.bed || '--'}床：${task?.title || '待处理任务'}`,
    detail: shortTaskText(task?.detail || '请确认现场状态、处置记录和后续计划。', 56),
    checklist: checklistForMode(task?.task_type || 'story', task),
  }
  storyOpen.value = true
  storyLoading.value = false
  handoffText.value = ''
  story.value = null
}

function goPatientDetail(patientId: string) {
  if (!patientId) {
    message.warning('缺少患者ID，无法进入患者详情')
    return
  }
  void router.push({ path: `/patient/${patientId}`, query: route.query })
}

function openRoundingSheet(patientId?: string) {
  const id = String(patientId || firstPatientId() || '').trim()
  if (!id) {
    message.info('当前暂无可打开的查房患者。')
    return
  }
  void router.push({
    path: '/rounding-sheet',
    query: {
      ...route.query,
      patientId: id,
      focus: 'rounding',
    },
  })
}

function firstPatientId() {
  return String(priorityQueue.value?.[0]?.patient_id || '')
}

function toggleFeatureExpanded(key: string) {
  const next = new Set(expandedFeatureKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedFeatureKeys.value = next
}

function applySignalFilter(key: string) {
  activeSignalFilter.value = activeSignalFilter.value === key ? '' : key
  stickySectionRef.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function runDirectorTile(tile: any) {
  const key = String(tile?.key || '')
  if (key === 'rules') {
    void router.push({ path: '/admin/scanner-health', query: route.query })
    return
  }
  if (key === 'case' && priorityQueue.value?.[0]?.patient_id) {
    void openStory(String(priorityQueue.value[0].patient_id))
    return
  }
  applySignalFilter(key === 'open' ? 'director' : key === 'antibiotic' ? 'antibiotic' : key === 'discharge' ? 'doctor' : '')
}

function runFlowAction(item: any) {
  const key = String(item?.key || '')
  const patientId = firstPatientId()
  if (key === 'director_huddle' || key === 'head_nurse_quality') {
    void router.push({ path: '/admin/scanner-health', query: route.query })
    return
  }
  if (key === 'morning_round' && doctorGaps.value?.[0]?.patient_id) {
    openRoundingSheet(String(doctorGaps.value[0].patient_id))
    return
  }
  if (key === 'nursing_shift' && nursingTasks.value?.[0]?.patient_id) {
    void openStory(String(nursingTasks.value[0].patient_id))
    return
  }
  if (patientId) void openHandoff(patientId)
  else message.info('当前暂无可生成的代表患者，先等待患者/告警数据同步。')
}

function runAiTool(tool: any) {
  const key = String(tool?.key || '')
  const patientId = String(tool?.target_patient_id || firstPatientId())
  if (key === 'scanner_review') {
    void router.push({ path: '/admin/scanner-health', query: route.query })
    return
  }
  if (!patientId) {
    message.info('当前暂无可打开的代表患者。')
    return
  }
  if (key === 'story' || key === 'nursing') void openStory(patientId)
  else void openHandoff(patientId)
}

function runFeatureAction(item: any, feature?: any) {
  const mode = String(feature?.detailMode || item?.kind || '')
  if (mode === 'scanner_review' || String(item?.kind || '') === 'scanner_review') {
    void router.push({ path: '/admin/scanner-health', query: route.query })
    return
  }
  const patientId = String(item?.patient_id || firstPatientId())
  if (!patientId) {
    showFeatureDetail(item, feature)
    return
  }
  if (mode === 'rounding') {
    openRoundingSheet(patientId)
    return
  }
  if (mode === 'story') void openStory(patientId)
  else showFeatureDetail(item, feature)
}

function showVisualPatient(row: any, mode: string) {
  const patientId = String(row?.patient_id || firstPatientId())
  const feature = {
    owner: 'ICU',
    title: ({
      order_gap: '医嘱闭环',
      weaning: '撤机评估',
      discharge: '转出评估',
      family: '家属沟通',
    } as Record<string, string>)[mode] || '临床任务',
    detailMode: mode,
    subtitle: '系统已整理为可点击任务。',
  }
  const item = {
    patient_id: patientId,
    bed: row?.bed,
    name: row?.name,
    title: row?.bed ? `${row.bed}床 ${feature.title}` : feature.title,
    detail: mode === 'weaning'
      ? lightDetail(row, '撤机')
      : mode === 'discharge'
        ? lightDetail(row, '转出')
        : mode === 'family'
          ? '按“问题、变化、风险、计划”生成家属沟通卡。'
          : '按“告警、医嘱、执行、复查、结果”核对闭环状态。',
  }
  showFeatureDetail(item, feature)
}

function lightDetail(row: any, title: string) {
  const lights = Array.isArray(row?.lights) ? row.lights : []
  const bad = lights.filter((light: any) => !light.ok).map((light: any) => light.label)
  return bad.length ? `${title}未达标：${bad.join('、')}` : `${title}灯号全部通过，可进入人工确认。`
}

function normalizeRouteRole(value: string) {
  const raw = String(value || '').toLowerCase()
  if (/head|护士长/.test(raw)) return 'head_nurse'
  if (/nurse|护士/.test(raw)) return 'nurse'
  if (/director|主任/.test(raw)) return 'director'
  if (/doctor|医生/.test(raw)) return 'doctor'
  return raw || 'doctor'
}

function roleHomeCacheKey() {
  return [routeUserName.value, normalizeRouteRole(routeRole.value), routeDeptCode.value, routeDept.value].join('|')
}

function buildFallbackHome() {
  const userName = routeUserName.value
  const role = normalizeRouteRole(routeRole.value)
  const deptCode = routeDeptCode.value
  const dept = routeDept.value
  return {
    code: 0,
    title: '临床工作台',
    role,
    account: {
      userName,
      display_name: userName,
      role,
      dept_code: deptCode,
      dept,
      found: Boolean(userName),
    },
    cards: [],
    priority_queue: [],
    playbook: [],
    scanner_review: [],
    nursing_tasks: [],
    doctor_gaps: [],
    quality_actions: [],
    director_digest: {},
    icu_day_flow: [],
    ai_toolbox: [],
    sticky_features: {},
    role_distribution: [],
    open_tasks: { total: 0, items: [] },
    clinical_visuals: {},
    degraded: true,
  }
}

async function loadHome() {
  const seq = ++homeRequestSeq
  const cacheKey = roleHomeCacheKey()
  const cached = roleHomeCache.get(cacheKey)
  home.value = cached || buildFallbackHome()
  loading.value = !cached
  try {
    let request = roleHomeInflight.get(cacheKey)
    if (!request) {
      request = getClinicalRoleHome({
        userName: routeUserName.value || undefined,
        role: routeRole.value || undefined,
        dept_code: routeDeptCode.value || undefined,
        dept: routeDept.value || undefined,
      }).then((res) => res.data).finally(() => roleHomeInflight.delete(cacheKey))
      roleHomeInflight.set(cacheKey, request)
    }
    const data = await request
    if (seq !== homeRequestSeq) return
    home.value = data
    roleHomeCache.set(cacheKey, data)
  } catch (error: any) {
    if (seq !== homeRequestSeq) return
    const isTimeout = String(error?.code || error?.message || '').toLowerCase().includes('timeout') || error?.code === 'ECONNABORTED'
    if (!cached) home.value = buildFallbackHome()
    message.warning(isTimeout ? '工作台数据加载较慢，已先按当前账号展示，可稍后刷新。' : '工作台数据暂时加载失败，已先按当前账号展示。')
  } finally {
    if (seq === homeRequestSeq) loading.value = false
  }
}

async function openStory(patientId: string) {
  if (!patientId) {
    message.warning('缺少患者ID，无法打开患者事件链')
    return
  }
  selectPatient(patientId, 'story')
  featureDetail.value = null
  message.loading({ content: '正在打开患者事件链...', key: 'clinical-story', duration: 0 })
  storyOpen.value = true
  storyLoading.value = true
  handoffText.value = ''
  story.value = null
  try {
    const { data } = await getClinicalPatientStory(patientId, { hours: 24 })
    story.value = data?.story || data
    message.success({ content: '患者事件链已打开', key: 'clinical-story', duration: 1.5 })
  } catch (error: any) {
    message.error({ content: error?.message || '患者事件链加载失败', key: 'clinical-story' })
  } finally {
    storyLoading.value = false
  }
}

async function openHandoff(patientId: string) {
  if (!patientId) {
    message.warning('缺少患者ID，无法生成交班摘要')
    return
  }
  selectPatient(patientId, 'handoff')
  featureDetail.value = null
  message.loading({ content: '正在生成交班摘要...', key: 'clinical-story', duration: 0 })
  storyOpen.value = true
  storyLoading.value = true
  handoffText.value = ''
  story.value = null
  try {
    const { data } = await getClinicalPatientHandoff(patientId, { role: home.value?.role || 'doctor', hours: 12 })
    handoffText.value = data?.handoff?.handoff_text || ''
    story.value = data?.handoff?.story || null
    message.success({ content: '交班摘要已打开', key: 'clinical-story', duration: 1.5 })
  } catch (error: any) {
    message.error({ content: error?.message || '交班摘要加载失败', key: 'clinical-story' })
  } finally {
    storyLoading.value = false
  }
}

watch(() => [
  route.query.userName, route.query.useName, route.query.username, route.query.user_id, route.query.userId,
  route.query.role, route.query.userRole,
  route.query.deptCode, route.query.dept_code, route.query.dept, route.query.department,
], () => {
  void loadHome()
})

onMounted(() => {
  void loadHome()
})
</script>

<style scoped>
.clinical-workflow {
  --icu-critical: #fb7185;
  --icu-high: #fb923c;
  --icu-warning: #fbbf24;
  --icu-stable: #34d399;
  --icu-info: #67e8f9;
  display: grid;
  gap: 16px;
  padding: 18px;
  font-family: var(--app-display-font);
}
.hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 24px;
  border: 1px solid rgba(125, 211, 252, 0.16);
  border-radius: 22px;
  background:
    radial-gradient(circle at 12% 0%, rgba(34, 211, 238, 0.2), transparent 30%),
    linear-gradient(135deg, rgba(8, 29, 48, 0.96), rgba(7, 18, 31, 0.98));
  box-shadow: 0 18px 44px rgba(0,0,0,.22);
}
.eyebrow { color: #67e8f9; font-size: 12px; letter-spacing: .14em; text-transform: uppercase; }
h1 { margin: 6px 0; color: #ecfeff; font-size: 32px; line-height: 1.1; }
.hero p { margin: 0; color: #9cc7d8; font-size: 14px; }
.color-legend {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}
.color-legend span {
  padding: 4px 9px;
  border-radius: 999px;
  color: #06131b;
  font-size: 12px;
  font-weight: 900;
}
.color-legend .is-critical { background: var(--icu-critical); }
.color-legend .is-high { background: var(--icu-high); }
.color-legend .is-warning { background: var(--icu-warning); }
.color-legend .is-stable { background: var(--icu-stable); }
.color-legend .is-info { background: var(--icu-info); }
.identity-card {
  min-width: 220px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(52, 211, 153, .22);
  background: rgba(6, 78, 59, .2);
}
.identity-card span,.identity-card em,.muted,.panel-title small { display: block; color: #8cb7c9; font-size: 12px; font-style: normal; }
.identity-card strong { display: block; margin: 6px 0; color: #ecfeff; font-size: 20px; }
.soft-alert { border-radius: 14px; }
.kpi-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; }
.kpi-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(125, 211, 252, .14);
  background: linear-gradient(180deg, rgba(11,31,50,.94), rgba(7,18,31,.98));
}
.kpi-card span { color: #8cb7c9; font-size: 12px; }
.kpi-card strong { display: block; margin-top: 8px; color: #ecfeff; font-size: 30px; }
.tone-danger,
.tone-critical { border-color: rgba(251,113,133,.34); }
.tone-high { border-color: rgba(251,146,60,.34); }
.tone-warn,
.tone-warning { border-color: rgba(251,191,36,.32); }
.tone-stable { border-color: rgba(52,211,153,.28); }
.open-task-strip {
  display: grid;
  grid-template-columns: 160px 1fr;
  gap: 12px;
  align-items: stretch;
  padding: 12px;
  border: 1px solid rgba(251,191,36,.22);
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(69, 26, 3, .48), rgba(7,18,31,.96));
}
.open-task-head {
  display: grid;
  place-content: center;
  border-radius: 14px;
  background: rgba(251,191,36,.12);
  color: #fde68a;
}
.open-task-head span { font-size: 13px; font-weight: 900; }
.open-task-head strong { color: #fff7ed; font-size: 28px; line-height: 1.1; }
.open-task-row {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}
.open-task-chip {
  min-height: 76px;
  padding: 10px;
  border: 1px solid rgba(253,230,138,.22);
  border-radius: 14px;
  background: rgba(15,23,42,.68);
  color: #ecfeff;
  text-align: left;
  cursor: pointer;
}
.open-task-chip b,
.open-task-chip span,
.open-task-chip em { display: block; font-style: normal; }
.open-task-chip b { font-size: 16px; }
.open-task-chip span { margin: 3px 0; color: #fbbf24; font-size: 12px; font-weight: 900; }
.open-task-chip em { color: #cbd5e1; font-size: 12px; line-height: 1.35; }
.director-morning-screen {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid rgba(251,191,36,.22);
  background:
    radial-gradient(circle at 6% 0%, rgba(251,191,36,.16), transparent 28%),
    linear-gradient(180deg, rgba(7,20,34,.96), rgba(4,12,22,.98));
}
.director-screen-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.director-screen-head span {
  color: #ecfeff;
  font-size: 18px;
  font-weight: 900;
}
.director-screen-head button {
  border: 1px solid rgba(103,232,249,.28);
  border-radius: 999px;
  padding: 7px 12px;
  color: #67e8f9;
  background: rgba(8,31,49,.72);
  font-weight: 900;
  cursor: pointer;
}
.morning-tile-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 10px;
}
.morning-tile {
  min-height: 112px;
  display: grid;
  align-content: center;
  gap: 6px;
  border: 1px solid rgba(125,211,252,.14);
  border-radius: 18px;
  padding: 14px;
  color: #ecfeff;
  background: rgba(8,31,49,.72);
  text-align: left;
  cursor: pointer;
}
.morning-tile span { color: #8cb7c9; font-size: 12px; }
.morning-tile strong { color: #ecfeff; font-size: 32px; line-height: 1; }
.morning-tile b { color: #67e8f9; font-size: 12px; }
.morning-tile.tone-warning { background: linear-gradient(145deg, rgba(113,63,18,.42), rgba(8,31,49,.72)); }
.morning-tile.tone-high { background: linear-gradient(145deg, rgba(154,52,18,.48), rgba(8,31,49,.72)); }
.morning-tile.tone-stable { background: linear-gradient(145deg, rgba(6,78,59,.36), rgba(8,31,49,.72)); }
.icu-day-section,
.ai-toolbox {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid rgba(125,211,252,.14);
  background:
    radial-gradient(circle at 8% 0%, rgba(20,184,166,.14), transparent 26%),
    linear-gradient(180deg, rgba(7,20,34,.94), rgba(4,12,22,.98));
}
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
}
.section-head strong { display: block; color: #ecfeff; font-size: 20px; margin-top: 2px; }
.section-head small { display: block; color: #8cb7c9; margin-top: 4px; }
.section-head.compact { margin-bottom: 10px; }
.day-flow {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}
.day-card {
  min-height: 112px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 13px;
  border-radius: 16px;
  border: 1px solid rgba(125,211,252,.13);
  background: rgba(8,31,49,.62);
}
.day-time {
  width: fit-content;
  padding: 4px 8px;
  border-radius: 999px;
  color: #99f6e4;
  background: rgba(20,184,166,.18);
  font-size: 12px;
  font-weight: 800;
}
.day-card strong { color: #ecfeff; line-height: 1.35; }
.day-card p { margin: 0; color: #9cc7d8; font-size: 12px; line-height: 1.55; }
.compact-workflow .day-card p,
.compact-workflow .ai-line { display: none; }
.ai-line {
  margin-top: auto;
  padding: 9px;
  border-radius: 12px;
  background: rgba(2,6,23,.28);
}
.ai-line span {
  display: inline-flex;
  margin-right: 6px;
  color: #06131b;
  background: linear-gradient(135deg, #a7f3d0, #67e8f9);
  border-radius: 999px;
  padding: 2px 6px;
  font-size: 11px;
  font-weight: 900;
}
.ai-line em { color: #c7f9ff; font-size: 12px; font-style: normal; line-height: 1.45; }
.ghost-link {
  width: fit-content;
  border: 0;
  padding: 0;
  color: #67e8f9;
  background: transparent;
  font: inherit;
  font-size: 12px;
  font-weight: 900;
  cursor: pointer;
}
.tool-row {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}
.tool-card {
  min-height: 94px;
  text-align: left;
  border: 1px solid rgba(94,234,212,.15);
  border-radius: 16px;
  padding: 12px;
  background: linear-gradient(180deg, rgba(6,78,59,.22), rgba(8,31,49,.68));
  cursor: pointer;
}
.tool-card span { display: block; color: #ecfeff; font-weight: 900; }
.tool-card strong { display: block; margin: 4px 0; color: #99f6e4; font-size: 28px; }
.tool-card em { display: block; min-height: 38px; color: #9cc7d8; font-style: normal; font-size: 12px; line-height: 1.45; }
.compact-toolbox .tool-card em { display: none; }
.tool-card b { display: block; margin-top: 8px; color: #67e8f9; font-size: 12px; }
.visual-command {
  display: grid;
  grid-template-columns: 1.15fr .9fr .9fr;
  gap: 12px;
}
.visual-body-card,
.visual-chart-card {
  min-height: 240px;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(94,234,212,.16);
  background:
    radial-gradient(circle at 100% 0%, rgba(34,211,238,.12), transparent 32%),
    linear-gradient(180deg, rgba(7,20,34,.95), rgba(4,12,22,.98));
}
.visual-head {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}
.visual-head span {
  padding: 3px 8px;
  border-radius: 999px;
  color: #06131b;
  background: linear-gradient(135deg, #a7f3d0, #67e8f9);
  font-size: 11px;
  font-weight: 900;
}
.body-visual-wrap {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 168px;
  align-items: center;
  gap: 8px;
}
.body-visual-wrap :deep(.human-body) { max-height: 190px; overflow: hidden; }
.organ-mini-panel {
  display: grid;
  justify-items: center;
  gap: 8px;
}
.organ-risk-list {
  width: 100%;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}
.organ-risk-list button {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 10px;
  padding: 6px 7px;
  color: #c7f9ff;
  background: rgba(2,6,23,.22);
  cursor: pointer;
}
.organ-risk-list span { font-size: 12px; }
.organ-risk-list b { font-size: 12px; color: var(--icu-stable); }
.organ-risk-list .is-warning b { color: var(--icu-warning); }
.organ-risk-list .is-high b { color: var(--icu-high); }
.organ-risk-list .is-critical b { color: var(--icu-critical); }
.donut-wrap {
  display: grid;
  grid-template-columns: 132px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  min-height: 168px;
}
.donut-chart {
  width: 124px;
  height: 124px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  box-shadow: inset 0 0 0 1px rgba(125,211,252,.12), 0 10px 30px rgba(0,0,0,.22);
}
.donut-chart > div {
  width: 76px;
  height: 76px;
  display: grid;
  place-content: center;
  border-radius: 999px;
  text-align: center;
  background: #06131f;
}
.donut-chart strong { color: #ecfeff; font-size: 28px; line-height: 1; }
.donut-chart span { color: #8cb7c9; font-size: 12px; }
.donut-legend,
.role-bars { display: grid; gap: 9px; }
.donut-legend button,
.role-bars button {
  width: 100%;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 12px;
  padding: 8px 9px;
  color: #c7f9ff;
  background: rgba(2,6,23,.22);
  cursor: pointer;
}
.donut-legend i {
  width: 9px;
  height: 9px;
  border-radius: 999px;
}
.donut-legend span,
.role-bars span { font-size: 12px; }
.donut-legend b,
.role-bars b { color: #ecfeff; }
.role-bars button { grid-template-columns: 48px minmax(0, 1fr) 28px; }
.role-bars div {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(125,211,252,.12);
}
.role-bars i {
  display: block;
  height: 100%;
  border-radius: inherit;
}
.clinical-visual-grid {
  display: grid;
  grid-template-columns: 1.1fr .8fr .9fr;
  gap: 12px;
}
.visual-panel {
  min-height: 190px;
  padding: 14px;
  border-radius: 20px;
  border: 1px solid rgba(94,234,212,.16);
  background:
    radial-gradient(circle at 100% 0%, rgba(20,184,166,.12), transparent 30%),
    linear-gradient(180deg, rgba(7,20,34,.95), rgba(4,12,22,.98));
}
.bed-wall-panel,
.swimlane-panel { grid-row: span 2; }
.visual-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}
.visual-panel-head span {
  color: #ecfeff;
  font-size: 15px;
  font-weight: 900;
}
.visual-panel-head b {
  min-width: 34px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  color: #06131b;
  background: linear-gradient(135deg, #a7f3d0, #67e8f9);
  font-size: 12px;
}
.panel-subline {
  margin: -6px 0 10px;
  color: #8cb7c9;
  font-size: 12px;
}
.bed-heatmap {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 8px;
}
.bed-cell {
  min-height: 58px;
  display: grid;
  place-content: center;
  gap: 2px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 14px;
  color: #ecfeff;
  background: rgba(8,31,49,.7);
  cursor: pointer;
}
.bed-cell strong { font-size: 15px; }
.bed-cell span { color: #c7f9ff; font-size: 12px; }
.bed-cell.tone-critical { background: linear-gradient(145deg, rgba(127,29,29,.78), rgba(8,31,49,.72)); border-color: rgba(251,113,133,.42); }
.bed-cell.tone-high { background: linear-gradient(145deg, rgba(154,52,18,.72), rgba(8,31,49,.72)); border-color: rgba(251,146,60,.36); }
.bed-cell.tone-warning { background: linear-gradient(145deg, rgba(113,63,18,.62), rgba(8,31,49,.72)); border-color: rgba(251,191,36,.3); }
.bed-cell.tone-stable { border-color: rgba(52,211,153,.24); }
.omission-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.omission-cell {
  min-height: 54px;
  display: grid;
  place-items: center;
  gap: 3px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 14px;
  color: #c7f9ff;
  background: rgba(2,6,23,.24);
  cursor: pointer;
}
.omission-cell i {
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  font-style: normal;
  font-weight: 900;
}
.omission-cell span { font-size: 12px; }
.omission-cell.is-ok i { color: #052e24; background: var(--icu-stable); }
.omission-cell.is-todo { border-color: rgba(251,191,36,.34); background: rgba(113,63,18,.2); }
.omission-cell.is-todo i { color: #451a03; background: var(--icu-warning); }
.mini-progress {
  height: 8px;
  margin: -2px 0 10px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(2,6,23,.32);
}
.mini-progress i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #22c55e, #67e8f9);
}
.mini-task-row {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}
.mini-task-row button {
  padding: 6px 8px;
  border: 1px solid rgba(251,191,36,.24);
  border-radius: 10px;
  color: #fde68a;
  background: rgba(113,63,18,.2);
  text-align: left;
  cursor: pointer;
  font-size: 12px;
}
.antibiotic-chart {
  height: 112px;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  align-items: end;
}
.antibiotic-bar {
  height: 100%;
  display: grid;
  align-items: end;
  gap: 5px;
  border: 0;
  color: #9cc7d8;
  background: transparent;
  cursor: pointer;
}
.antibiotic-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  margin-bottom: 8px;
}
.antibiotic-stats span {
  padding: 5px 6px;
  border-radius: 10px;
  color: #c7f9ff;
  background: rgba(2,6,23,.24);
  text-align: center;
  font-size: 12px;
  font-weight: 900;
}
.antibiotic-bar i {
  width: 100%;
  min-height: 8px;
  align-self: end;
  border-radius: 999px 999px 5px 5px;
  background: linear-gradient(180deg, #67e8f9, #0e7490);
}
.antibiotic-bar span { font-size: 11px; }
.antibiotic-task-list {
  display: grid;
  gap: 6px;
  margin-top: 8px;
}
.antibiotic-task {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 8px;
  border: 1px solid rgba(125,211,252,.14);
  border-radius: 10px;
  color: inherit;
  background: rgba(2,6,23,.24);
  cursor: pointer;
}
.antibiotic-task.prio-high {
  border-color: rgba(251,113,133,.34);
}
.antibiotic-task strong,
.antibiotic-task span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.antibiotic-task strong { color: #ecfeff; }
.antibiotic-task span { color: #99f6e4; }
.source-chip {
  width: fit-content;
  margin-top: 10px;
  padding: 4px 8px;
  border-radius: 999px;
  color: #99f6e4;
  background: rgba(20,184,166,.14);
  font-size: 11px;
}
.swimlane-list,
.light-list,
.rescue-line { display: grid; gap: 8px; }
.swimlane-row {
  width: 100%;
  display: grid;
  grid-template-columns: 52px repeat(5, minmax(0, 1fr));
  gap: 6px;
  align-items: center;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 14px;
  padding: 8px;
  color: #ecfeff;
  background: rgba(2,6,23,.22);
  cursor: pointer;
}
.swimlane-row strong { font-size: 12px; }
.swimlane-row span {
  padding: 5px 4px;
  border-radius: 999px;
  text-align: center;
  color: #8cb7c9;
  background: rgba(125,211,252,.09);
  font-size: 11px;
}
.swimlane-row .is-done { color: #99f6e4; background: rgba(20,184,166,.22); }
.swimlane-row .is-todo { color: #fde68a; background: rgba(113,63,18,.28); }
.light-row {
  width: 100%;
  display: grid;
  grid-template-columns: 54px 42px repeat(5, 1fr);
  gap: 7px;
  align-items: center;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 14px;
  padding: 9px;
  color: #ecfeff;
  background: rgba(2,6,23,.22);
  cursor: pointer;
}
.light-row strong { font-size: 12px; }
.light-percent {
  color: #99f6e4;
  font-size: 12px;
  font-weight: 900;
}
.light-row i {
  height: 14px;
  border-radius: 999px;
  background: #64748b;
}
.light-row i.ok { background: var(--icu-stable); box-shadow: 0 0 12px rgba(52,211,153,.45); }
.light-row i.bad { background: var(--icu-critical); box-shadow: 0 0 12px rgba(251,113,133,.38); }
.rescue-line button {
  position: relative;
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  border: 0;
  padding: 4px 0;
  color: #c7f9ff;
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.rescue-line i {
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #67e8f9;
  box-shadow: 0 0 12px rgba(103,232,249,.6);
}
.rescue-line span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
}
.family-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.family-grid button {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 5px;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 14px;
  padding: 9px;
  color: #c7f9ff;
  background: rgba(2,6,23,.22);
  cursor: pointer;
}
.family-grid strong {
  grid-column: 1 / -1;
  color: #ecfeff;
  font-size: 12px;
}
.family-grid em {
  display: grid;
  place-items: center;
  border-radius: 999px;
  color: #052e24;
  background: linear-gradient(135deg, #67e8f9, #a7f3d0);
  font-style: normal;
  font-size: 12px;
  font-weight: 950;
}
.family-grid span {
  padding: 4px 5px;
  border-radius: 8px;
  text-align: center;
  background: rgba(14,116,144,.18);
  font-size: 11px;
}
.visual-empty {
  min-height: 110px;
  display: grid;
  place-content: center;
  border-radius: 14px;
  border: 1px dashed rgba(125,211,252,.18);
  color: #8cb7c9;
  font-size: 13px;
}
.sticky-section {
  padding: 16px;
  border-radius: 20px;
  border: 1px solid rgba(94,234,212,.16);
  background:
    radial-gradient(circle at 94% 8%, rgba(251,191,36,.11), transparent 28%),
    radial-gradient(circle at 0% 60%, rgba(45,212,191,.12), transparent 30%),
    linear-gradient(180deg, rgba(7,20,34,.96), rgba(4,12,22,.98));
}
.feature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  align-items: stretch;
}
.feature-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(125,211,252,.14);
  background: linear-gradient(180deg, rgba(8,31,49,.72), rgba(5,20,34,.88));
}
.feature-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.feature-meta span {
  display: inline-flex;
  padding: 3px 8px;
  border-radius: 999px;
  color: #06131b;
  background: linear-gradient(135deg, #a7f3d0, #67e8f9);
  font-size: 11px;
  font-weight: 900;
}
.feature-meta b {
  color: #8cb7c9;
  font-size: 12px;
}
.feature-head strong { display: block; color: #ecfeff; font-size: 18px; line-height: 1.25; }
.feature-list {
  display: grid;
  gap: 8px;
  align-content: start;
}
.feature-item {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  text-align: left;
  border: 1px solid rgba(125,211,252,.12);
  border-radius: 14px;
  min-height: 46px;
  padding: 10px 12px;
  background: rgba(2,6,23,.22);
  cursor: pointer;
}
.feature-item strong {
  display: block;
  color: #ecfeff;
  font-size: 13px;
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.feature-item span {
  align-self: center;
  white-space: nowrap;
  color: #67e8f9;
  font-size: 12px;
  font-weight: 900;
}
.feature-item:hover { border-color: rgba(103,232,249,.42); background: rgba(14,116,144,.18); }
.feature-more {
  width: 100%;
  border: 0;
  padding: 7px 10px;
  border-radius: 12px;
  color: #8cb7c9;
  background: rgba(14,116,144,.12);
  font-size: 12px;
  text-align: center;
  cursor: pointer;
}
.feature-more:hover { color: #67e8f9; background: rgba(14,116,144,.24); }
.content-grid { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(320px, .8fr); gap: 16px; }
.queue-board {
  min-height: 320px;
  padding: 16px;
  border: 1px solid rgba(80,199,255,.16);
  border-radius: 18px;
  background:
    radial-gradient(circle at 0% 0%, rgba(14, 165, 233, .14), transparent 28%),
    linear-gradient(180deg, rgba(7,20,34,.94), rgba(4,12,22,.97));
}
.queue-board-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(125,211,252,.12);
}
.panel-kicker { display: block; color: #67e8f9; font-size: 11px; letter-spacing: .12em; text-transform: uppercase; }
.queue-board-head strong { display: block; color: #ecfeff; font-size: 20px; margin-top: 2px; }
.queue-board-head small { display: block; color: #8cb7c9; font-size: 12px; margin-top: 2px; }
.queue-loading,.queue-empty {
  min-height: 238px;
  display: grid;
  place-content: center;
  text-align: center;
  color: #8cb7c9;
}
.queue-empty {
  max-width: 620px;
  margin: 0 auto;
}
.queue-empty strong { color: #ecfeff; font-size: 20px; }
.queue-empty p { margin: 10px 0 16px; line-height: 1.7; }
.empty-actions { display: flex; justify-content: center; align-items: center; gap: 14px; flex-wrap: wrap; }
.empty-actions a { color: #67e8f9; }
.patient-card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; padding-top: 14px; }
.patient-task-card {
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(125,211,252,.13);
  background: linear-gradient(180deg, rgba(8,31,49,.82), rgba(5,20,34,.92));
}
.patient-task-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.patient-task-card p { min-height: 38px; margin: 8px 0; color: #9cc7d8; line-height: 1.45; }
.risk-pill {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 12px;
  border: 1px solid rgba(125,211,252,.18);
}
.risk-high { color: #fecdd3; background: rgba(127,29,29,.36); border-color: rgba(248,113,113,.3); }
.risk-mid { color: #fde68a; background: rgba(113,63,18,.32); border-color: rgba(251,191,36,.28); }
.risk-low { color: #bfdbfe; background: rgba(30,64,175,.24); }
.patient-task-metrics { display: flex; gap: 8px; flex-wrap: wrap; }
.patient-task-metrics span {
  padding: 4px 8px;
  border-radius: 999px;
  color: #a5f3fc;
  background: rgba(14,116,144,.18);
  font-size: 12px;
}
.latest-alert {
  margin: 12px 0;
  padding: 10px;
  border-radius: 12px;
  background: rgba(2,6,23,.28);
}
.latest-alert span { display: block; color: #8cb7c9; font-size: 11px; }
.latest-alert strong { display: block; color: #ecfeff; margin-top: 3px; }
.card-actions { position: relative; z-index: 5; display: flex; align-items: center; gap: 8px; pointer-events: auto; }
.story-action {
  appearance: none;
  border: 1px solid rgba(125,211,252,.3);
  border-radius: 999px;
  padding: 7px 12px;
  color: #dffbff;
  background: rgba(8,31,49,.86);
  font: inherit;
  font-size: 14px;
  font-weight: 800;
  line-height: 1;
  cursor: pointer;
  pointer-events: auto;
  transition: transform .16s ease, border-color .16s ease, background .16s ease;
}
.story-action.primary {
  color: #06202d;
  border-color: rgba(103,232,249,.72);
  background: linear-gradient(135deg, #67e8f9, #5eead4);
  box-shadow: 0 8px 18px rgba(34,211,238,.16);
}
.story-action.compact { flex: 0 0 auto; white-space: nowrap; font-size: 12px; padding: 6px 10px; }
.story-action:hover { transform: translateY(-1px); border-color: rgba(103,232,249,.72); }
.story-action:active { transform: translateY(0); }
.panel { border: 1px solid rgba(80,199,255,.12); background: linear-gradient(180deg, rgba(7,20,34,.94), rgba(4,12,22,.97)); }
.panel-title span { display: block; color: #ecfeff; font-weight: 800; }
.patient-link { color: #67e8f9; font-weight: 800; }
.side-stack { display: grid; gap: 16px; align-content: start; }
.story-inline-panel {
  border-color: rgba(94, 234, 212, .22);
  box-shadow: 0 14px 30px rgba(20, 184, 166, .08);
}
.inline-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.playbook { display: grid; gap: 10px; }
.playbook-item,.scanner-row,.story-cluster {
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(125,211,252,.12);
  background: rgba(8,31,49,.62);
}
.playbook-item strong,.scanner-row strong,.story-cluster strong { color: #ecfeff; }
.playbook-item p,.story-cluster p { margin: 6px 0 0; color: #9cc7d8; }
.scanner-list { display: grid; gap: 8px; }
.scanner-row { display: flex; justify-content: space-between; gap: 12px; color: #9cc7d8; }
.action-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.action-panel {
  min-height: 260px;
  padding: 16px;
  border-radius: 20px;
  border: 1px solid rgba(125,211,252,.14);
  background:
    radial-gradient(circle at 100% 0%, rgba(34,211,238,.12), transparent 28%),
    linear-gradient(180deg, rgba(7,20,34,.95), rgba(4,12,22,.98));
}
.nurse-panel { border-color: rgba(52,211,153,.18); }
.doctor-panel { border-color: rgba(96,165,250,.2); }
.quality-panel { border-color: rgba(251,191,36,.2); }
.action-panel-head span {
  display: block;
  color: #67e8f9;
  font-size: 11px;
  letter-spacing: .12em;
  text-transform: uppercase;
}
.action-panel-head strong { display: block; color: #ecfeff; font-size: 19px; margin-top: 3px; }
.action-panel-head small { display: block; color: #8cb7c9; font-size: 12px; margin-top: 4px; line-height: 1.45; }
.action-list { display: grid; gap: 10px; margin-top: 14px; }
.action-list.compact { gap: 8px; }
.action-item {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  padding: 12px;
  border-radius: 15px;
  border: 1px solid rgba(125,211,252,.12);
  background: rgba(8,31,49,.66);
}
.action-item strong { color: #ecfeff; line-height: 1.35; }
.action-item p { margin: 6px 0 0; color: #9cc7d8; font-size: 12px; line-height: 1.55; }
.action-item b {
  min-width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  color: #ecfeff;
  background: rgba(2,6,23,.35);
}
.digest-strip { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.digest-strip span {
  padding: 5px 8px;
  border-radius: 999px;
  color: #fde68a;
  background: rgba(113,63,18,.24);
  font-size: 12px;
}
.mini-empty {
  min-height: 148px;
  display: grid;
  place-content: center;
  padding: 20px;
  margin-top: 14px;
  border-radius: 16px;
  border: 1px dashed rgba(125,211,252,.18);
  color: #8cb7c9;
  text-align: center;
  line-height: 1.7;
}
.handoff-text {
  white-space: pre-wrap;
  padding: 12px;
  border-radius: 12px;
  margin-bottom: 12px;
  color: #d9f99d;
  background: rgba(63, 98, 18, .22);
}
.handoff-text.inline,
.story-summary.inline,
.story-list.inline,
.story-empty.inline { margin-top: 10px; }
.feature-detail-panel {
  display: grid;
  gap: 12px;
  padding: 14px;
  margin-bottom: 12px;
  border-radius: 16px;
  border: 1px solid rgba(94,234,212,.22);
  background:
    radial-gradient(circle at 0% 0%, rgba(45,212,191,.14), transparent 32%),
    rgba(8,31,49,.68);
}
.feature-detail-panel.inline { margin-top: 10px; }
.treatment-card {
  display: grid;
  gap: 10px;
  margin: 10px 0 12px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(94,234,212,.2);
  background: rgba(8,31,49,.62);
}
.treatment-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.treatment-card__head span {
  color: #99f6e4;
  font-size: 12px;
  font-weight: 900;
}
.treatment-card__head button {
  border: 1px solid rgba(125,211,252,.22);
  border-radius: 999px;
  padding: 5px 9px;
  color: #c7f9ff;
  background: rgba(14,116,144,.18);
  cursor: pointer;
  font-size: 12px;
  font-weight: 800;
}
.treatment-card__body strong {
  display: block;
  color: #ecfeff;
  margin-bottom: 8px;
}
.treatment-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.treatment-metrics span,
.treatment-card__empty {
  padding: 5px 8px;
  border-radius: 999px;
  color: #a5f3fc;
  background: rgba(2,6,23,.28);
  font-size: 12px;
}
.treatment-card__empty {
  border-radius: 12px;
  line-height: 1.45;
}
.feature-detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.feature-detail-head span {
  padding: 3px 8px;
  border-radius: 999px;
  color: #06131b;
  background: linear-gradient(135deg, #a7f3d0, #67e8f9);
  font-size: 11px;
  font-weight: 900;
}
.feature-detail-head strong { color: #ecfeff; font-size: 17px; }
.feature-detail-panel p { margin: 0; color: #bff4ff; line-height: 1.65; }
.feature-detail-checklist {
  display: grid;
  gap: 8px;
}
.feature-detail-checklist div {
  position: relative;
  padding: 9px 10px 9px 28px;
  border-radius: 12px;
  color: #dffbff;
  background: rgba(2,6,23,.24);
  line-height: 1.45;
}
.feature-detail-checklist div::before {
  content: "";
  position: absolute;
  left: 11px;
  top: 16px;
  width: 7px;
  height: 7px;
  border-radius: 999px;
  background: #67e8f9;
  box-shadow: 0 0 10px rgba(103,232,249,.6);
}
.task-close-btn {
  width: fit-content;
  margin-top: 2px;
  padding: 8px 12px;
  border: 1px solid rgba(52,211,153,.28);
  border-radius: 999px;
  color: #a7f3d0;
  background: rgba(20,83,45,.28);
  cursor: pointer;
  font-weight: 900;
}
.story-summary { color: #ecfeff; margin-bottom: 12px; }
.story-empty {
  padding: 18px;
  border-radius: 16px;
  border: 1px dashed rgba(125,211,252,.2);
  background: rgba(8,31,49,.52);
  text-align: center;
}
.story-empty strong { color: #ecfeff; }
.story-empty p { margin: 8px 0 0; color: #8cb7c9; line-height: 1.6; }
.story-list { display: grid; gap: 10px; }
html[data-theme='light'] .hero,
html[data-theme='light'] .kpi-card,
html[data-theme='light'] .icu-day-section,
html[data-theme='light'] .ai-toolbox,
html[data-theme='light'] .day-card,
html[data-theme='light'] .tool-card,
html[data-theme='light'] .visual-body-card,
html[data-theme='light'] .visual-chart-card,
html[data-theme='light'] .visual-panel,
html[data-theme='light'] .sticky-section,
html[data-theme='light'] .feature-panel,
html[data-theme='light'] .feature-item,
html[data-theme='light'] .feature-detail-panel,
html[data-theme='light'] .panel,
html[data-theme='light'] .queue-board,
html[data-theme='light'] .patient-task-card,
html[data-theme='light'] .action-panel,
html[data-theme='light'] .action-item,
html[data-theme='light'] .story-empty,
html[data-theme='light'] .donut-chart > div { background: #fff; border-color: rgba(145,176,199,.36); box-shadow: none; }
html[data-theme='light'] h1,
html[data-theme='light'] .identity-card strong,
html[data-theme='light'] .kpi-card strong,
html[data-theme='light'] .panel-title span,
html[data-theme='light'] .queue-board-head strong,
html[data-theme='light'] .queue-empty strong,
html[data-theme='light'] .section-head strong,
html[data-theme='light'] .day-card strong,
html[data-theme='light'] .tool-card span,
html[data-theme='light'] .visual-panel-head span,
html[data-theme='light'] .feature-head strong,
html[data-theme='light'] .feature-item strong,
html[data-theme='light'] .feature-detail-head strong,
html[data-theme='light'] .latest-alert strong,
html[data-theme='light'] .playbook-item strong,
html[data-theme='light'] .scanner-row strong,
html[data-theme='light'] .story-cluster strong,
html[data-theme='light'] .action-panel-head strong,
html[data-theme='light'] .action-item strong,
html[data-theme='light'] .story-empty strong { color: #0f172a; }
html[data-theme='light'] .hero p,
html[data-theme='light'] .muted,
html[data-theme='light'] .panel-title small,
html[data-theme='light'] .queue-board-head small,
html[data-theme='light'] .section-head small,
html[data-theme='light'] .day-card p,
html[data-theme='light'] .tool-card em,
html[data-theme='light'] .panel-subline,
html[data-theme='light'] .visual-empty,
html[data-theme='light'] .feature-meta b,
html[data-theme='light'] .donut-chart span,
html[data-theme='light'] .feature-detail-panel p,
html[data-theme='light'] .patient-task-card p,
html[data-theme='light'] .playbook-item p,
html[data-theme='light'] .story-cluster p,
html[data-theme='light'] .action-panel-head small,
html[data-theme='light'] .action-item p,
html[data-theme='light'] .mini-empty,
html[data-theme='light'] .story-empty p { color: #64748b; }
@media (max-width: 1100px) {
  .hero,.content-grid,.action-grid { grid-template-columns: 1fr; display: grid; }
  .day-flow,.tool-row,.feature-grid,.visual-command,.clinical-visual-grid { grid-template-columns: 1fr; }
  .morning-tile-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .patient-card-grid { grid-template-columns: 1fr; }
  .bed-wall-panel,
  .swimlane-panel { grid-row: auto; }
}
</style>
