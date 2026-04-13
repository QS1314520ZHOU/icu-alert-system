<template>
  <div class="workbench">
    <section class="hero-card">
      <div>
        <h2>科研分析工作台</h2>
        <p>ICU 科研全流程：数据准备 → 分析 → 图表/表格导出 → AI撰写</p>
      </div>
      <div class="hero-actions">
        <span class="cohort-pill link" :class="{ empty: !currentCohortSummary }" @click="jumpToTab('prep')">
          当前队列：{{ currentCohortSummary || '未选择' }}
        </span>
        <a-space>
          <a-button size="small" @click="openSessionDrawer = true">分析会话</a-button>
          <a-button type="primary" size="small" :loading="sessionLoading" @click="saveSession">保存会话</a-button>
        </a-space>
      </div>
    </section>

    <section class="platform-strip">
      <article :class="['platform-card', `platform-card--${platformStatusLevel}`]">
        <div class="platform-card__head">
          <div>
            <div class="platform-card__title">平台状态</div>
            <div class="platform-card__sub">{{ platformStatus?.summary || '等待平台状态' }}</div>
          </div>
          <a-space>
            <a-button size="small" :loading="platformStatusLoading" @click="loadPlatformStatus">刷新</a-button>
            <a-button size="small" type="primary" ghost :loading="platformStatusLoading" @click="runPlatformCheck">自检</a-button>
          </a-space>
        </div>
        <div class="platform-kpi-row">
          <div v-for="item in platformKpis" :key="item.label" class="platform-kpi">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>
        <div v-if="platformMissingRows.length" class="platform-chip-row">
          <span v-for="item in platformMissingRows" :key="item.module" class="platform-chip platform-chip--warn">
            缺 {{ item.module }}
          </span>
        </div>
        <div v-if="platformStatusError" class="platform-error">{{ platformStatusError }}</div>
      </article>

      <article class="platform-card">
        <div class="platform-card__head">
          <div>
            <div class="platform-card__title">任务中心</div>
            <div class="platform-card__sub">统一查看分析与导出任务</div>
          </div>
          <a-button size="small" :loading="researchJobsLoading" @click="loadPlatformJobs">刷新</a-button>
        </div>
        <div class="platform-summary-row">
          <span>待执行 {{ researchJobsSummary?.pending || 0 }}</span>
          <span>执行中 {{ researchJobsSummary?.processing || 0 }}</span>
          <span>已完成 {{ researchJobsSummary?.completed || 0 }}</span>
          <span>失败 {{ researchJobsSummary?.failed || 0 }}</span>
        </div>
        <div v-if="recentPlatformJobs.length" class="platform-list">
          <div v-for="item in recentPlatformJobs" :key="item.job_id" class="platform-list__item">
            <div>
              <strong>{{ item.title || item.kind || '任务' }}</strong>
              <div class="platform-list__meta">{{ item.kind }} · {{ item.status }} · {{ item.progress }}%</div>
            </div>
            <span class="platform-list__time">{{ item.created_at ? String(item.created_at).slice(5, 16).replace('T', ' ') : '—' }}</span>
          </div>
        </div>
        <div v-else class="platform-empty">暂无科研任务</div>
        <div v-if="researchJobsError" class="platform-error">{{ researchJobsError }}</div>
      </article>

      <article class="platform-card">
        <div class="platform-card__head">
          <div>
            <div class="platform-card__title">产物中心</div>
            <div class="platform-card__sub">导出包、图表、表格统一归档</div>
          </div>
          <a-button size="small" :loading="researchArtifactsLoading" @click="loadPlatformArtifacts">刷新</a-button>
        </div>
        <div v-if="recentPlatformArtifacts.length" class="platform-list">
          <div v-for="item in recentPlatformArtifacts" :key="item.artifact_id" class="platform-list__item">
            <div>
              <strong>{{ item.title || item.file_name || '产物' }}</strong>
              <div class="platform-list__meta">{{ item.artifact_type || 'file' }} · {{ item.source || 'research' }}</div>
            </div>
            <a :href="item.download_url || '#'" class="artifact-link" target="_blank" rel="noopener noreferrer">下载</a>
          </div>
        </div>
        <div v-else class="platform-empty">暂无科研产物</div>
        <div v-if="researchArtifactsError" class="platform-error">{{ researchArtifactsError }}</div>
      </article>
    </section>

    <section v-if="!cohortReady && tab !== 'prep'" class="warn-banner" @click="jumpToTab('prep')">
      ⚠ 请先在「数据准备」中选择研究队列
    </section>

    <div class="workbench-body">
      <aside class="nav-panel">
        <div
          v-for="item in leftNav"
          :key="item.key"
          :class="[
            'nav-item',
            {
              active: tab === item.key,
              divider: item.type === 'divider',
              disabled: item.type !== 'divider' && !cohortReady && item.key !== 'prep',
            }
          ]"
          @click="onTabSelect(item)"
        >
          <template v-if="item.type !== 'divider'">
            <span class="nav-label">{{ item.label }}</span>
            <span
              v-if="item.key === 'prep'"
              class="nav-status"
            >
              <span class="status-dot" :class="{ ready: cohortReady }"></span>
            </span>
            <span
              v-else-if="navCompletion[item.key]"
              class="nav-status status-check"
            >
              ✓
            </span>
          </template>
        </div>
      </aside>

      <section class="content-panel">
        <div v-if="tab === 'prep'" key="prep" class="tab-content">
          <div class="card-grid">
            <div class="card">
              <div class="card-head">
                <span>选择研究队列</span>
              </div>
              <div class="prep-options">
                <ARadioGroup :value="prepMode" direction="vertical">
                  <ARadio value="saved" @click.stop.prevent="togglePrepMode('saved')">
                    使用已保存队列
                    <a-select
                      v-model:value="scope.cohort_id"
                      :disabled="prepMode !== 'saved'"
                      :options="cohortOptions"
                      allow-clear
                      show-search
                      option-filter-prop="label"
                      placeholder="选择队列"
                      style="width: 220px; margin-left: 12px"
                    >
                      <template #option="{ value, label }">
                        <div class="cohort-option">
                          <span class="cohort-label">{{ label }}</span>
                          <a-button type="link" size="small" @click.stop="removeCohort(String(value))">删除</a-button>
                        </div>
                      </template>
                    </a-select>
                  </ARadio>
                  <ARadio value="dept" @click.stop.prevent="togglePrepMode('dept')">
                    使用当前科室患者（{{ currentDeptDisplay }}）
                  </ARadio>
                  <ARadio value="builder" @click.stop.prevent="togglePrepMode('builder')">
                    <span>新建队列</span>
                    <a-button
                      type="link"
                      size="small"
                      style="margin-left: 12px"
                      @mousedown.stop.prevent
                      @click.stop.prevent="openCohortBuilder"
                    >
                      打开队列构建器
                    </a-button>
                  </ARadio>
                </ARadioGroup>
              <div class="form-grid two prep-scope-grid">
                <div>
                  <div class="label">患者范围</div>
                  <a-select v-model:value="scope.patient_scope" :options="patientScopeOptions" />
                </div>
              </div>
              <div class="prep-hint">
                <template v-if="currentDeptCode">
                  当前按 {{ currentDeptDisplay }} 科室和“{{ patientScopeLabel(scope.patient_scope) }}”范围构建科研队列
                </template>
                <template v-else>
                  当前访问地址未包含科室信息，可使用已保存队列或新建全量科研队列
                </template>
              </div>
            </div>
            <div class="prep-summary">
              <div>当前队列：{{ currentCohortSummary || '未选择' }}</div>
              <div>患者数：{{ cohortPreviewCount || 0 }} 例</div>
            </div>
            </div>

            <div class="card">
              <div class="card-head">
                <span>分组设置</span>
              </div>
              <div class="form-grid two">
                <div>
                  <div class="label">分组依据</div>
                  <a-select v-model:value="scope.group_by" :options="groupByOptions" />
                </div>
              </div>
              <div class="group-summary">
                <template v-for="(card, idx) in groupSummaryCards" :key="card.name">
                  <div class="group-card" :class="card.type">
                    <div class="label">{{ card.name }}</div>
                    <strong>{{ card.countText }}</strong>
                    <span>{{ card.percentText }}</span>
                  </div>
                  <div v-if="idx === 0 && groupSummaryCards.length > 1" class="group-vs">对比</div>
                </template>
              </div>
            </div>

            <div class="card collapsible full-width">
              <div class="card-head">
                <span>可用变量概览</span>
                <div class="var-head-actions">
                  <span>已选 {{ selectedVariables.length }}/{{ variableCatalog.length }} 个</span>
                  <span>已设筛选 {{ appliedFilterCount }} 个</span>
                  <span>当前 {{ selectedPatientIds.length }} 例（原 {{ originalCohortCount }} 例）</span>
                  <a-button size="small" type="link" @click="selectAllVariables">全选</a-button>
                  <a-button size="small" type="link" @click="clearAllVariables">清空</a-button>
                </div>
              </div>
              <div class="variable-tags">
                <div v-for="[category, vars] in variableGroups" :key="category" class="variable-row">
                  <span class="var-category" @click="toggleCategory(category)">
                    {{ category }}（点击可全选本类）：
                    <em v-if="categoryFlash[category]" class="category-flash">{{ categoryFlash[category] }}</em>
                  </span>
                  <div class="var-tags">
                    <a-tooltip v-for="item in vars" :key="item.field" :mouse-enter-delay="0.5">
                      <template #title>
                        <div class="var-tooltip">
                          <div class="tooltip-title">{{ item.label }}</div>
                          <div>类型：{{ typeLabelCN(item.type) }}</div>
                          <div>来源：{{ item.source || '临床记录' }}</div>
                          <div v-if="getVarSummary(item.field).non_null_rate != null">
                            非空率：{{ ((getVarSummary(item.field).non_null_rate || 0) * 100).toFixed(1) }}%
                            ({{ getVarSummary(item.field).non_null_count || 0 }}/{{ getVarSummary(item.field).total_count || 0 }})
                          </div>
                          <div v-if="item.type === 'continuous'">
                            范围：{{ getVarSummary(item.field).range ? `${getVarSummary(item.field).range.min} ~ ${getVarSummary(item.field).range.max}` : '--' }}
                          </div>
                          <div v-if="item.type === 'continuous'">
                            均值：{{ getVarSummary(item.field).mean != null ? `${getVarSummary(item.field).mean.toFixed(item.field === 'age' ? 0 : 1)} ± ${getVarSummary(item.field).std?.toFixed(item.field === 'age' ? 0 : 1) ?? '-'}` : '--' }}
                          </div>
                          <div v-else>
                            分布：
                            <div class="tooltip-distribution">
                              <div v-for="(info, key) in getVarSummary(item.field).distribution || {}" :key="key">
                                {{ key }} {{ info.count || 0 }}例 ({{ ((info.ratio || 0) * 100).toFixed(1) }}%)
                              </div>
                            </div>
                          </div>
                          <div class="tooltip-divider"></div>
                          <div>适用分析：{{ applicableLabel(item.applicable) || '—' }}</div>
                        </div>
                      </template>
                      <div class="var-item" :data-var-field="item.field">
                        <div
                          class="var-tag"
                          :class="[
                            { selected: isVariableSelected(item.field), filtered: hasVariableFilter(item.field) },
                            item.type
                          ]"
                        >
                          <button class="check-toggle" type="button" @click.stop="toggleVariable(item.field)">
                            {{ isVariableSelected(item.field) ? '☑' : '☐' }}
                          </button>
                          <span class="var-name" @click.stop="toggleVariable(item.field)">{{ item.label }}</span>
                          <span v-if="filterSummary(item.field)" class="filter-summary">{{ filterSummary(item.field) }}</span>
                          <span class="var-type">{{ variableTypeBadge(item.type) }}</span>
                          <button class="expand-toggle" type="button" @click.stop="toggleVariablePanel(item.field)">
                            {{ expandedVariableField === item.field ? '▴' : '▾' }}
                          </button>
                        </div>
                        <div v-if="expandedVariableField === item.field" class="filter-panel">
                          <template v-if="item.type === 'continuous'">
                            <label class="radio-option"><input v-model="draftFilter(item.field).mode" type="radio" value="none"> 不筛选</label>
                            <label class="radio-option"><input v-model="draftFilter(item.field).mode" type="radio" value="range"> 设定范围</label>
                            <div v-if="draftFilter(item.field).mode === 'range'" class="range-row">
                              <input
                                v-model.number="draftFilter(item.field).min"
                                type="number"
                                :placeholder="continuousPlaceholder(item.field, 'min')"
                                @keydown.enter.prevent="applyVariableFilter(item.field)"
                              >
                              <span>~</span>
                              <input
                                v-model.number="draftFilter(item.field).max"
                                type="number"
                                :placeholder="continuousPlaceholder(item.field, 'max')"
                                @keydown.enter.prevent="applyVariableFilter(item.field)"
                              >
                            </div>
                            <div class="overview-line">{{ continuousOverview(item.field) }}</div>
                            <div class="quick-buttons">
                              <button
                                v-for="quick in quickPresets(item.field)"
                                :key="quick.label"
                                type="button"
                                class="quick-btn"
                                @click="fillContinuousQuick(item.field, quick.min, quick.max)"
                              >
                                {{ quick.label }}
                              </button>
                            </div>
                          </template>
                          <template v-else-if="item.type === 'categorical'">
                            <label class="radio-option"><input v-model="draftFilter(item.field).mode" type="radio" value="none"> 不筛选</label>
                            <label class="radio-option"><input v-model="draftFilter(item.field).mode" type="radio" value="include"> 选择类别</label>
                            <div v-if="draftFilter(item.field).mode === 'include' && item.field === 'primary_diagnosis'" class="diag-search-block">
                              <a-select
                                mode="multiple"
                                :value="draftFilter(item.field).selected"
                                :options="icdSearch.options"
                                :loading="icdSearch.loading"
                                :filter-option="false"
                                show-search
                                allow-clear
                                placeholder="搜索 ICD（支持编码/汉字/拼音/首字母）"
                                style="width: 100%"
                                @search="onIcdSearch"
                                @update:value="(val) => onDiagnosisIcdSelect(item.field, val)"
                                @dropdownVisibleChange="(open) => onIcdDropdownOpen(open)"
                              />
                              <div class="diag-search-tip">来源：DataCenter / VI_ICU_ICD，已选 {{ (draftFilter(item.field).selected || []).length }} 项</div>
                            </div>
                            <div v-else-if="draftFilter(item.field).mode === 'include'" class="cat-grid">
                              <label v-for="opt in categoryOptions(item.field)" :key="opt.value" class="cat-item">
                                <input
                                  :checked="isCategoryChecked(item.field, opt.value)"
                                  type="checkbox"
                                  @change="toggleCategoryValue(item.field, opt.value)"
                                >
                                {{ opt.label }} ({{ opt.count }}例)
                              </label>
                            </div>
                          </template>
                          <template v-else>
                            <label class="radio-option"><input v-model="draftFilter(item.field).mode" type="radio" value="none"> 不筛选</label>
                            <label class="radio-option"><input v-model="draftFilter(item.field).mode" type="radio" value="yes"> 仅包含：是 ({{ binaryCount(item.field, true) }}例)</label>
                            <label class="radio-option"><input v-model="draftFilter(item.field).mode" type="radio" value="no"> 仅包含：否 ({{ binaryCount(item.field, false) }}例)</label>
                          </template>
                          <div class="actions">
                            <button type="button" class="btn-apply" @click="applyVariableFilter(item.field)">应用</button>
                            <button type="button" class="btn-clear" @click="clearVariableFilter(item.field)">清除筛选</button>
                          </div>
                        </div>
                      </div>
                    </a-tooltip>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="showNextSteps" class="next-step-card">
            <div class="status-line">
              <span>✓ 队列已选择 ({{ cohortPreviewCount || '0' }} 例)</span>
              <span>✓ 分组已设置</span>
            </div>
            <div class="recommend">推荐下一步：</div>
            <a-space>
              <a-button
                v-for="item in nextSteps"
                :key="item.key"
                size="small"
                @click="jumpToTab(item.key)"
              >
                {{ item.label }} →
              </a-button>
            </a-space>
          </div>

          <div class="card full-width">
            <div class="card-head">
              <span>AI 对话式配置与执行</span>
              <span class="collapse-summary">一句话描述需求，自动拆解并执行</span>
            </div>
            <ATextarea
              v-model:value="aiPlanner.prompt"
              :rows="3"
              placeholder="例如：纳入脓毒症患者，按结局分组，先出基线特征表，再做回归分析和相关性分析。"
            />
            <a-space>
              <a-button type="primary" :loading="aiPlanner.loading" @click="runAiPlanner(true)">AI一键配置并执行</a-button>
              <a-button :disabled="aiPlanner.loading" @click="runAiPlanner(false)">仅配置不执行</a-button>
            </a-space>
            <div v-if="aiPlanner.steps.length" class="planner-block">
              <div class="planner-progress-head">
                <span>执行进度</span>
                <span>{{ Math.round(aiPlanner.progress) }}%</span>
              </div>
              <AProgress
                :percent="Math.round(aiPlanner.progress)"
                size="small"
                :status="aiPlanner.loading ? 'active' : (Math.round(aiPlanner.progress) >= 100 ? 'success' : 'normal')"
              />
              <div class="planner-step-list">
                <div v-for="step in aiPlanner.steps" :key="step.key" class="planner-step-row" :class="`is-${step.status}`">
                  <span class="planner-step-dot"></span>
                  <span class="planner-step-title">{{ step.title }}</span>
                  <span class="planner-step-state">{{ plannerStatusText(step.status) }}</span>
                </div>
              </div>
            </div>
            <div v-if="aiPlanner.logs.length" class="planner-log-box">
              <div v-for="(row, idx) in aiPlanner.logs" :key="`${row.time}_${idx}`" class="planner-log-row" :class="`is-${row.level}`">
                <span class="planner-log-time">{{ row.time }}</span>
                <span class="planner-log-text">{{ row.text }}</span>
              </div>
            </div>
            <div v-if="aiPlanner.lastMessage" class="prep-hint">AI说明：{{ aiPlanner.lastMessage }}</div>
          </div>
        </div>

        <div v-else-if="tab === 'table1'" key="table1" class="tab-content">
          <div class="config-card">
            <a-collapse ghost v-model:activeKey="openConfigKeys.table1">
              <ACollapsePanel key="config" :show-arrow="false">
                <template #header>
                  <div class="collapse-head">
                    <span>分析配置</span>
                    <span class="collapse-summary">变量：{{ scope.variables.length }}</span>
                  </div>
                </template>
                <div class="form-grid three">
                  <div class="full">
                    <div class="label">变量选择</div>
                    <a-select v-model:value="scope.variables" mode="multiple" :options="variableOptions" placeholder="选择变量" />
                  </div>
                </div>
              </ACollapsePanel>
            </a-collapse>
          </div>
          <div class="action-bar">
            <a-button type="primary" :loading="loading.table1" @click="runTable1">生成基线特征表（表1）</a-button>
            <a-button @click="resetTable1">重置配置</a-button>
          </div>
          <div class="result-card">
            <template v-if="table1Rows.length">
              <div v-if="table1QualityTips.length" class="quality-strip">
                <span v-for="tip in table1QualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
              </div>
              <div class="card-head between">
                <span>基线特征表</span>
                <a-space>
                  <a-button size="small" @click="exportTable">导出文档</a-button>
                  <a-button size="small" @click="exportTableCsv">导出表格</a-button>
                </a-space>
              </div>
              <div v-if="table1QualityRows.length" class="sub-card">
                <div class="sub-title">变量完整性摘要</div>
                <a-table :columns="table1QualityColumns" :data-source="table1QualityRows" :pagination="false" size="small" row-key="field" />
              </div>
              <div class="paper-table">
                <a-table
                  :columns="table1Columns"
                  :data-source="table1Rows"
                  :pagination="false"
                  class="three-line-table"
                  size="small"
                  row-key="row_key"
                />
                <p class="table-footnote">{{ table1Result?.footnote }}</p>
              </div>
            </template>
            <template v-else>
              <div class="empty-state">
                <div class="empty-title">配置参数后点击运行</div>
              </div>
            </template>
          </div>
          <AiAssistPanel
            analysis-type="table1"
            :result="table1Result"
            :state="ai.table1"
            @generate="onAiGenerate"
            @copy="onAiCopy"
            @update-lang="onAiLang"
            @update-part="onAiPart"
            @update-text="onAiText"
          />
        </div>

        <div v-else-if="tab === 'survival'" key="survival" class="tab-content">
          <div class="config-card">
            <a-collapse ghost v-model:activeKey="openConfigKeys.survival">
              <ACollapsePanel key="config" :show-arrow="false">
                <template #header>
                  <div class="collapse-head">
                    <span>分析配置</span>
                    <span class="collapse-summary">{{ survivalForm.time_field }} · {{ survivalForm.event_field }}</span>
                  </div>
                </template>
                <div class="form-grid three">
                  <div>
                    <div class="label">时间变量</div>
                    <a-select v-model:value="survivalForm.time_field" :options="timeFieldOptions" />
                  </div>
                  <div>
                    <div class="label">事件变量</div>
                    <a-select v-model:value="survivalForm.event_field" :options="eventFieldOptions" />
                  </div>
                  <div>
                    <div class="label">最大观察时间(天)</div>
                    <a-input-number v-model:value="survivalForm.max_time" :min="7" :max="365" />
                  </div>
                  <div class="full">
                    <div class="label">分组依据</div>
                    <a-select v-model:value="survivalForm.group_by" :options="groupByOptions" allow-clear />
                  </div>
                </div>
              </ACollapsePanel>
            </a-collapse>
          </div>
          <div class="action-bar">
            <a-button type="primary" :loading="loading.survival" @click="runSurvival">运行生存分析</a-button>
          </div>
          <div class="result-card">
            <template v-if="survivalResult">
              <div v-if="survivalQualityTips.length" class="quality-strip">
                <span v-for="tip in survivalQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
              </div>
              <div class="sub-card">
                <div class="sub-title">样本摘要</div>
                <a-table :columns="survivalSummaryColumns" :data-source="survivalSummaryRows" :pagination="false" size="small" row-key="group" />
              </div>
              <template v-if="survivalOption">
                <div class="chart-card white">
                  <div class="card-head between">
                    <span>生存曲线</span>
                    <a-dropdown>
                      <a-button size="small">导出</a-button>
                      <template #overlay>
                        <a-menu>
                          <AMenuItem @click="exportFigure('survival')">PNG</AMenuItem>
                        </a-menu>
                      </template>
                    </a-dropdown>
                  </div>
                  <ResearchChart :option="survivalOption" :init-options="chartInitOptions" style="height: 400px" />
                </div>
              </template>
            </template>
            <template v-else>
              <div class="empty-state">
                <div class="empty-title">运行分析后查看结果</div>
              </div>
            </template>
          </div>
          <AiAssistPanel analysis-type="survival" :result="survivalResult" :state="ai.survival" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
        </div>

        <div v-else-if="tab === 'regression'" key="regression" class="tab-content">
          <div class="config-card">
            <a-collapse ghost v-model:activeKey="openConfigKeys.regression">
              <ACollapsePanel key="config" :show-arrow="false">
                <template #header>
                  <div class="collapse-head">
                    <span>分析配置</span>
                    <span class="collapse-summary">{{ regressionForm.outcome }} · {{ regressionForm.predictors.length }}个变量</span>
                  </div>
                </template>
                <div class="form-grid three">
                  <div>
                    <div class="label">结局变量</div>
                    <a-select v-model:value="regressionForm.outcome" :options="binaryVariableOptions" />
                  </div>
                  <div>
                    <div class="label">模型类型</div>
                    <a-select v-model:value="regressionForm.outcome_type" :options="[{ label: '二分类（逻辑回归）', value: 'binary' }, { label: '连续（线性回归）', value: 'continuous' }]" />
                  </div>
                  <div class="full">
                    <div class="label">预测变量</div>
                    <a-select v-model:value="regressionForm.predictors" mode="multiple" :options="variableOptions" placeholder="选择预测变量" @change="disableAutoSync('regression')" />
                  </div>
                  <div class="full">
                    <div class="label">校正变量（可选）</div>
                    <a-select v-model:value="regressionForm.confounders" mode="multiple" :options="variableOptions" placeholder="选择校正变量" @change="disableAutoSync('regression')" />
                  </div>
                </div>
                <div v-if="regressionCoverageText" class="prep-hint">{{ regressionCoverageText }}</div>
              </ACollapsePanel>
            </a-collapse>
          </div>
          <div class="action-bar">
            <a-button type="primary" :loading="loading.regression" @click="runRegression">运行回归分析</a-button>
          </div>
          <div class="result-card">
            <template v-if="regressionResult">
              <div v-if="regressionQualityTips.length" class="quality-strip">
                <span v-for="tip in regressionQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
              </div>
              <div class="card-head between">
                <span>回归结果（{{ regressionResult.model_type || '--' }}）</span>
                <span class="result-meta">样本数={{ regressionResult.n_total ?? '--' }}</span>
              </div>
              <div class="sub-card">
                <div class="sub-title">建模摘要</div>
                <a-table :columns="regressionSummaryColumns" :data-source="regressionSummaryRows" :pagination="false" size="small" row-key="row_key" />
              </div>
              <div v-if="regressionCountRows.length" class="sub-card">
                <div class="sub-title">单因素样本损失</div>
                <a-table :columns="regressionCountColumns" :data-source="regressionCountRows" :pagination="false" size="small" row-key="variable" />
              </div>
              <div class="sub-card">
                <div class="sub-title">单因素分析</div>
                <a-table :columns="regressionColumns" :data-source="regressionUnivariateRows" :pagination="false" size="small" row-key="row_key" />
              </div>
              <div class="sub-card">
                <div class="sub-title">多因素分析</div>
                <a-table :columns="regressionColumns" :data-source="regressionMultivariateRows" :pagination="false" size="small" row-key="row_key" />
              </div>
            </template>
            <template v-else>
              <div class="empty-state"><div class="empty-title">运行回归分析后查看结果</div></div>
            </template>
          </div>
          <AiAssistPanel analysis-type="regression" :result="regressionResult" :state="ai.regression" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
        </div>

        <div v-else-if="tab === 'roc'" key="roc" class="tab-content">
          <div class="config-card">
            <a-collapse ghost v-model:activeKey="openConfigKeys.roc">
              <ACollapsePanel key="config" :show-arrow="false">
                <template #header>
                  <div class="collapse-head">
                    <span>分析配置</span>
                    <span class="collapse-summary">{{ rocForm.predictors.length }}个预测指标</span>
                  </div>
                </template>
                <div class="form-grid three">
                  <div>
                    <div class="label">结局变量</div>
                    <a-select v-model:value="rocForm.outcome" :options="binaryVariableOptions" />
                  </div>
                  <div class="full">
                    <div class="label">预测指标</div>
                    <a-select v-model:value="rocForm.predictors" mode="multiple" :options="continuousVariableOptions" placeholder="选择连续变量" @change="disableAutoSync('roc')" />
                  </div>
                </div>
                <div v-if="rocCoverageText" class="prep-hint">{{ rocCoverageText }}</div>
              </ACollapsePanel>
            </a-collapse>
          </div>
          <div class="action-bar">
            <a-button type="primary" :loading="loading.roc" @click="runRoc">运行受试者工作特征分析</a-button>
          </div>
          <div class="result-card">
            <template v-if="rocResult">
              <template v-if="rocOption">
                <div class="chart-card white">
                  <div class="card-head between"><span>受试者工作特征曲线</span></div>
                  <ResearchChart :option="rocOption" :init-options="chartInitOptions" style="height: 360px" />
                </div>
              </template>
              <div class="sub-card">
                <a-table :columns="rocColumns" :data-source="rocRows" :pagination="false" size="small" row-key="row_key" />
              </div>
              <pre class="json-fallback">{{ JSON.stringify(rocResult, null, 2) }}</pre>
            </template>
            <template v-else>
              <div class="empty-state"><div class="empty-title">运行受试者工作特征分析后查看结果</div></div>
            </template>
          </div>
          <AiAssistPanel analysis-type="roc" :result="rocResult" :state="ai.roc" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
        </div>

        <div v-else-if="tab === 'trend'" key="trend" class="tab-content">
          <div class="config-card">
            <a-collapse ghost v-model:activeKey="openConfigKeys.trend">
              <ACollapsePanel key="config" :show-arrow="false">
                <template #header>
                  <div class="collapse-head">
                    <span>分析配置</span>
                    <span class="collapse-summary">{{ trendForm.indicators.length }}个指标 · {{ trendForm.time_range_hours }}小时</span>
                  </div>
                </template>
                <div class="form-grid three">
                  <div class="full">
                    <div class="label">指标</div>
                    <a-select v-model:value="trendForm.indicators" mode="multiple" :options="trendIndicatorOptions" placeholder="选择趋势指标" @change="disableAutoSync('trend')" />
                  </div>
                  <div>
                    <div class="label">时间范围(小时)</div>
                    <a-input-number v-model:value="trendForm.time_range_hours" :min="12" :max="240" />
                  </div>
                  <div>
                    <div class="label">采样间隔(小时)</div>
                    <a-input-number v-model:value="trendForm.interval_hours" :min="1" :max="24" />
                  </div>
                </div>
              </ACollapsePanel>
            </a-collapse>
          </div>
          <div class="action-bar">
            <a-button type="primary" :loading="loading.trend" @click="runTrend">运行趋势分析</a-button>
            <a-select v-if="trendIndicatorList.length" v-model:value="trendActiveIndicator" :options="trendIndicatorList.map((k) => ({ label: k, value: k }))" style="width: 220px" />
          </div>
          <div class="result-card">
            <template v-if="trendResult">
              <div v-if="trendQualityTips.length" class="quality-strip">
                <span v-for="tip in trendQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
              </div>
              <div v-if="trendSampleRows.length" class="sub-card">
                <div class="sub-title">时间点样本量摘要</div>
                <a-table :columns="trendSampleColumns" :data-source="trendSampleRows" :pagination="false" size="small" row-key="group" />
              </div>
              <template v-if="trendOption">
                <div class="chart-card white">
                  <div class="card-head between"><span>趋势曲线（{{ trendActiveIndicator || '-' }}）</span></div>
                  <ResearchChart :option="trendOption" :init-options="chartInitOptions" style="height: 360px" />
                </div>
              </template>
              <pre class="json-fallback">{{ JSON.stringify(trendResult, null, 2) }}</pre>
            </template>
            <template v-else>
              <div class="empty-state"><div class="empty-title">运行趋势分析后查看结果</div></div>
            </template>
          </div>
          <AiAssistPanel analysis-type="trend" :result="trendResult" :state="ai.trend" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
        </div>

        <div v-else-if="tab === 'correlation'" key="correlation" class="tab-content">
          <div class="config-card">
            <a-collapse ghost v-model:activeKey="openConfigKeys.correlation">
              <ACollapsePanel key="config" :show-arrow="false">
                <template #header>
                  <div class="collapse-head">
                    <span>分析配置</span>
                    <span class="collapse-summary">{{ correlationForm.variables.length }}个变量 · {{ correlationMethodLabel(correlationForm.method) }}</span>
                  </div>
                </template>
                <div class="form-grid three">
                  <div class="full">
                    <div class="label">变量</div>
                    <a-select v-model:value="correlationForm.variables" mode="multiple" :options="correlationVariableOptions" placeholder="选择至少2个连续变量" @change="disableAutoSync('correlation')" />
                  </div>
                  <div>
                    <div class="label">方法</div>
                    <a-select v-model:value="correlationForm.method" :options="[{ label: '自动选择', value: 'auto' }, { label: '皮尔逊', value: 'pearson' }, { label: '斯皮尔曼', value: 'spearman' }]" />
                  </div>
                </div>
                <div v-if="correlationCoverageText" class="prep-hint">{{ correlationCoverageText }}</div>
              </ACollapsePanel>
            </a-collapse>
          </div>
          <div class="action-bar">
            <a-button type="primary" :loading="loading.correlation" @click="runCorrelation">运行相关性分析</a-button>
          </div>
          <div class="result-card">
            <template v-if="correlationResult">
              <div v-if="correlationQualityTips.length" class="quality-strip">
                <span v-for="tip in correlationQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
              </div>
              <div v-if="correlationDataIssueText" class="result-meta correlation-warning">{{ correlationDataIssueText }}</div>
              <div v-if="correlationExcludedText" class="result-meta correlation-warning">{{ correlationExcludedText }}</div>
              <template v-if="correlationOption">
                <div class="chart-card white">
                  <div class="card-head between"><span>相关性热图</span></div>
                  <ResearchChart :option="correlationOption" :init-options="chartInitOptions" style="height: 420px" />
                </div>
              </template>
              <div v-if="correlationPairRows.length" class="sub-card">
                <div class="sub-title">有效样本对矩阵</div>
                <a-table :columns="correlationPairColumns" :data-source="correlationPairRows" :pagination="false" size="small" row-key="row_key" :scroll="{ x: true }" />
              </div>
              <pre class="json-fallback">{{ JSON.stringify(correlationResult, null, 2) }}</pre>
            </template>
            <template v-else>
              <div class="empty-state"><div class="empty-title">运行相关性分析后查看结果</div></div>
            </template>
          </div>
          <AiAssistPanel analysis-type="correlation" :result="correlationResult" :state="ai.correlation" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
        </div>

        <div v-else-if="tab === 'export'" key="export" class="tab-content">
          <div class="result-card">
            <div class="card-head between">
              <span>导出中心</span>
              <span class="result-meta">已生成 {{ exports.length }} 项</span>
            </div>
            <template v-if="exports.length">
              <a-table
                :columns="[
                  { title: '名称', dataIndex: 'title', key: 'title' },
                  { title: '文件', dataIndex: 'file_name', key: 'file_name' },
                  { title: '类型', dataIndex: 'format', key: 'format' },
                  { title: '时间', dataIndex: 'created_at', key: 'created_at' },
                  { title: '操作', key: 'action' },
                ]"
                :data-source="exports.map((row, idx) => ({ ...row, row_key: `exp_${idx}` }))"
                :pagination="false"
                size="small"
                row-key="row_key"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'created_at'">
                    {{ formatExportTime(record.created_at) }}
                  </template>
                  <template v-else-if="column.key === 'action'">
                    <a-button size="small" @click="openExport(record)">下载</a-button>
                  </template>
                </template>
              </a-table>
            </template>
            <template v-else>
              <div class="empty-state"><div class="empty-title">暂无导出记录，先在分析页运行并导出一次</div></div>
            </template>
          </div>
        </div>

        <div v-else-if="tab === 'subgroup'" key="subgroup" class="tab-content">
          <div class="config-card">
            <a-collapse ghost v-model:activeKey="openConfigKeys.subgroup">
              <ACollapsePanel key="config" :show-arrow="false">
                <template #header>
                  <div class="collapse-head">
                    亚组分析配置
                    <span class="collapse-summary">{{ subgroupForm.exposure }} · {{ subgroupForm.subgroups.filter(s => s.enabled).length }}个亚组</span>
                  </div>
                </template>
                <div class="form-grid three">
                  <div>
                    <div class="label">暴露因素</div>
                    <a-select v-model:value="subgroupForm.exposure" :options="variableOptions" placeholder="选择暴露因素" />
                  </div>
                  <div>
                    <div class="label">结局变量</div>
                    <a-select v-model:value="subgroupForm.outcome" :options="binaryVariableOptions" placeholder="选择结局变量" />
                  </div>
                  <div>
                    <div class="label">结局类型</div>
                    <a-select v-model:value="subgroupForm.outcome_type" :options="[{ value: 'binary', label: '二分类 (binary)' }, { value: 'continuous', label: '连续型 (continuous)' }]" />
                  </div>
                </div>
                <div v-if="subgroupCoverageText" class="prep-hint">{{ subgroupCoverageText }}</div>
                <div class="label" style="margin-top: 12px">亚组定义</div>
                <div class="form-grid three">
                  <label v-for="sg in subgroupForm.subgroups" :key="sg.key" class="radio-option">
                    <input type="checkbox" v-model="sg.enabled" /> {{ sg.label }}
                  </label>
                </div>
              </ACollapsePanel>
            </a-collapse>
          </div>
          <div class="action-bar">
            <a-button type="primary" :loading="loading.subgroup" @click="runSubgroup">运行亚组分析</a-button>
          </div>
          <div class="result-card">
            <template v-if="subgroupResult">
              <div v-if="subgroupQualityTips.length" class="quality-strip">
                <span v-for="tip in subgroupQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
              </div>
              <div class="chart-card white">
                <div class="card-head between">森林图（Forest Plot）</div>
                <ResearchChart :option="subgroupForestOption" :init-options="chartInitOptions" style="height: 480px" />
              </div>
              <div class="sub-card">
                <a-table :columns="subgroupColumns" :data-source="subgroupRows" :pagination="false" size="small" row-key="subgroup" />
              </div>
            </template>
            <template v-else>
              <div class="empty-state"><div class="empty-title">运行亚组分析后查看结果</div></div>
            </template>
          </div>
          <AiAssistPanel analysis-type="subgroup" :result="subgroupResult" :state="ai.subgroup" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
        </div>

        <div v-else key="other" class="tab-content">
          <div class="empty-state">
            <div class="empty-title">该模块稍后开放，当前请先完成核心分析流程</div>
          </div>
        </div>
      </section>
    </div>

    <a-drawer v-model:open="openSessionDrawer" title="分析会话" width="420">
      <a-space direction="vertical" style="width: 100%">
        <a-button size="small" :loading="sessionListLoading" @click="loadSessions">刷新</a-button>
        <div class="prep-hint" v-if="sessionListError">{{ sessionListError }}</div>
        <a-list
          :data-source="sessions"
          :loading="sessionListLoading"
          :locale="{ emptyText: sessionEmptyText }"
          bordered
          size="small"
        >
          <template #renderItem="{ item }">
            <AListItem>
              <div class="session-row">
                <div>{{ item.name }}</div>
                <a-button size="small" @click="restoreSession(String(item.session_id || ''))">载入</a-button>
              </div>
            </AListItem>
          </template>
        </a-list>
      </a-space>
    </a-drawer>
    <CohortBuilder
      :open="cohortBuilderOpen"
      :department="scope.department || currentDeptName || null"
      :dept-code="currentDeptCode"
      :patient-scope="scope.patient_scope"
      :initial-filters="cohortBuilderInitialFilters"
      @update:open="(val) => (cohortBuilderOpen = val)"
      @saved="onCohortBuilderSaved"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useRoute } from 'vue-router'
import {
  Button as AButton, Collapse as ACollapse, Drawer as ADrawer, Dropdown as ADropdown,
  Input as AInput, InputNumber as AInputNumber, List as AList, Menu as AMenu, Radio as ARadio, Select as ASelect,
  Progress as AProgress, Space as ASpace, Table as ATable, Tooltip as ATooltip, message, Modal,
} from 'ant-design-vue'
import AiAssistPanel from '../components/research/AiAssistPanel.vue'
import CohortBuilder from '../components/CohortBuilder.vue'
import { useResearchSelectionStore } from '../stores/researchSelection'
import {
  getDepartments, getPatients, getResearchAnalyticsTaskStatus, getResearchSession, listResearchCohorts, listResearchSessions, postResearchAiInterpret,
  postResearchAiPlan,
  getResearchIcdSearch,
  getResearchPlatformArtifacts,
  getResearchPlatformJobs,
  getResearchPlatformStatus,
  deleteResearchCohort, postResearchExportFigure, postResearchExportTable,
  postResearchPlatformCheck,
  postResearchCohortBuild, postResearchCorrelation, postResearchRegression, postResearchRoc, postResearchSubgroup, postResearchSurvival,
  postResearchTable1, postResearchTrend, postResearchVariableSummary, saveResearchSession,
} from '../api'

type LangKey = 'zh' | 'en'
type PartKey = 'interpretation' | 'methods_text' | 'results_text'
type AnyRecord = Record<string, any>
type AnalysisKey = 'table1' | 'survival' | 'regression' | 'roc' | 'subgroup' | 'trend' | 'correlation'
type VariableFilterMode = 'none' | 'range' | 'include' | 'yes' | 'no'
type CohortFilter = { field: string; operator: string; value: any }

const ARadioGroup = ARadio.Group
const ACollapsePanel = ACollapse.Panel
const AMenuItem = AMenu.Item
const AListItem = AList.Item
const ATextarea = AInput.TextArea

const ResearchChart = defineAsyncComponent(async () => {
  await import('../charts/analytics')
  const mod = await import('vue-echarts')
  return mod.default
})

const chartInitOptions = {
  devicePixelRatio: typeof window !== 'undefined'
    ? Math.max(window.devicePixelRatio || 1, window.innerWidth <= 1920 ? 1.5 : 1)
    : 1,
}

const variableCatalog = [
  { field: 'age', label: '年龄(岁)', type: 'continuous', category: '人口学', source: '患者基本信息', applicable: ['table1', 'regression', 'trend', 'correlation', 'roc'] },
  { field: 'sex', label: '性别', type: 'categorical', category: '人口学', source: '患者基本信息', applicable: ['table1', 'regression', 'subgroup'] },
  { field: 'sofa_admission', label: 'SOFA', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'trend', 'correlation', 'roc'] },
  { field: 'apache2', label: 'APACHE II', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation', 'roc'] },
  { field: 'mechanical_ventilation', label: '机械通气', type: 'binary', category: '治疗', source: '治疗记录', applicable: ['table1', 'regression', 'subgroup'] },
  { field: 'crrt', label: 'CRRT', type: 'binary', category: '治疗', source: '治疗记录', applicable: ['table1', 'regression', 'subgroup'] },
  { field: 'vasopressor', label: '血管活性药', type: 'binary', category: '治疗', source: '治疗记录', applicable: ['table1', 'regression', 'subgroup'] },
  { field: 'los_icu_days', label: 'ICU住院天数', type: 'continuous', category: '住院信息', source: '住院记录', applicable: ['table1', 'regression', 'trend', 'correlation'] },
  { field: 'primary_diagnosis', label: '主要诊断', type: 'categorical', category: '住院信息', source: '诊断记录', applicable: ['table1', 'regression'] },
  { field: 'icu_mortality', label: 'ICU死亡', type: 'binary', category: '结局', source: '结局信息', applicable: ['table1', 'regression', 'subgroup'] },
  // 评分类
  { field: 'gcs_admission', label: '入科GCS', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation', 'roc'] },
  { field: 'rass_admission', label: '入科RASS', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation'] },
  { field: 'sofa_max', label: 'SOFA最大值', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation', 'roc'] },
  { field: 'apache2_max', label: 'APACHE II最大值', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation', 'roc'] },
  // 检验类
  { field: 'lactate_admission', label: '入科乳酸(mmol/L)', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'creatinine_admission', label: '入科肌酐(μmol/L)', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'albumin_admission', label: '入科白蛋白(g/L)', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'pct_admission', label: '入科PCT(ng/mL)', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'wbc_admission', label: '入科WBC(×10⁹/L)', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'hemoglobin_admission', label: '入科Hb(g/L)', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'platelet_admission', label: '入科PLT(×10⁹/L)', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'pf_ratio_admission', label: '入科P/F比', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'bnp_admission', label: '入科BNP(pg/mL)', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  // 治疗类
  { field: 'vasopressor_days', label: '血管活性药使用天数', type: 'continuous', category: '治疗', source: '治疗记录', applicable: ['table1', 'regression', 'correlation'] },
  { field: 'mv_days', label: '机械通气天数', type: 'continuous', category: '治疗', source: '治疗记录', applicable: ['table1', 'regression', 'correlation'] },
  // 结局类
  { field: 'hospital_mortality', label: '院内死亡', type: 'binary', category: '结局', source: '结局信息', applicable: ['table1', 'regression', 'subgroup'] },
  { field: 'mortality_28d', label: '28天死亡', type: 'binary', category: '结局', source: '结局信息', applicable: ['table1', 'regression', 'subgroup'] },
  { field: 'icu_readmission', label: 'ICU再入科', type: 'binary', category: '结局', source: '结局信息', applicable: ['table1', 'regression', 'subgroup'] },
]

const tab = ref('prep')
const route = useRoute()
const cohorts = ref<Array<AnyRecord>>([])
const cohortPreviewCount = ref(0)
const patientLoadLoading = ref(false)
const scope = reactive({ cohort_id: '', patient_text: '', department: '', patient_scope: 'all' as 'in_dept' | 'out_dept' | 'all', group_by: 'outcome', variables: variableCatalog.map((v) => v.field) as string[] })
const loading = reactive({ table1: false, survival: false, regression: false, roc: false, subgroup: false, trend: false, correlation: false })
const table1Result = ref<AnyRecord | null>(null)
const survivalResult = ref<AnyRecord | null>(null)
const regressionResult = ref<AnyRecord | null>(null)
const rocResult = ref<AnyRecord | null>(null)
const subgroupResult = ref<AnyRecord | null>(null)
const trendResult = ref<AnyRecord | null>(null)
const correlationResult = ref<AnyRecord | null>(null)
const exports = ref<Array<AnyRecord>>([])
const deptNameByCode = ref<Record<string, string>>({})
const prepMode = ref<'saved' | 'dept' | 'builder' | ''>('saved')
const cohortBuilderOpen = ref(false)
const categoryFlash = reactive<Record<string, string>>({})
const expandedVariableField = ref<string>('')
const basePatientIds = ref<string[]>([])
const originalCohortCount = ref(0)
const cohortSourceFilters = ref<AnyRecord[]>([])
const appliedVariableFilters = reactive<Record<string, AnyRecord>>({})
const variableFilterDrafts = reactive<Record<string, AnyRecord>>({})
const analysisAutoSync = reactive({ regression: true, roc: true, trend: true, correlation: true })
const aiPlanner = reactive({
  prompt: '',
  loading: false,
  lastPlan: null as AnyRecord | null,
  lastMessage: '',
  progress: 0,
  steps: [] as Array<{ key: string; title: string; status: 'pending' | 'running' | 'success' | 'failed' | 'skipped'; detail?: string }>,
  logs: [] as Array<{ time: string; level: 'info' | 'success' | 'error'; text: string }>,
})
const icdSearch = reactive({
  loading: false,
  keyword: '',
  options: [] as Array<{ value: string; label: string; code: string; name: string }>,
})
let icdSearchTimer: ReturnType<typeof setTimeout> | null = null
let summaryFetchSeq = 0
let cohortBuildSeq = 0

const survivalForm = reactive({ time_field: 'los_icu_days', event_field: 'icu_mortality', group_by: 'outcome', max_time: 28 })
const regressionForm = reactive({ outcome: 'icu_mortality', outcome_type: 'binary', predictors: ['age', 'sofa_admission'], confounders: ['sex'] as string[] })
const rocForm = reactive({ outcome: 'icu_mortality', predictors: ['sofa_admission', 'apache2'] as string[] })
const subgroupForm = reactive({
  exposure: 'vasopressor',
  outcome: 'icu_mortality',
  outcome_type: 'binary' as 'binary' | 'continuous',
  subgroups: [] as Array<{ key: string; label: string; enabled: boolean; filterText: string }>,
})
const trendForm = reactive({ indicators: ['hr', 'map', 'lactate'] as string[], time_reference: 'icu_admission', time_range_hours: 72, interval_hours: 4 })
const correlationForm = reactive({ variables: ['age', 'sofa_admission', 'apache2', 'los_icu_days'] as string[], method: 'auto' })
const openConfigKeys = reactive<{ [key: string]: string[] }>({
  table1: ['config'],
  survival: ['config'],
  regression: ['config'],
  roc: ['config'],
  trend: ['config'],
  correlation: ['config'],
})

function newAiState() {
  return {
    open: false, loading: false, lang: 'zh' as LangKey, part: 'interpretation' as PartKey,
    content: { zh: { interpretation: '', methods_text: '', results_text: '' }, en: { interpretation: '', methods_text: '', results_text: '' } },
  }
}
type AiState = ReturnType<typeof newAiState>
const ai = reactive<{ [K in AnalysisKey]: AiState }>({
  table1: newAiState(), survival: newAiState(), regression: newAiState(), roc: newAiState(), subgroup: newAiState(), trend: newAiState(), correlation: newAiState(),
})

const researchSelectionStore = useResearchSelectionStore()
researchSelectionStore.initializeVariables(variableCatalog.map((v) => v.field))
const { selectedVariables, variableSummaries, selectedPatientIds, patientIdsVersion, cohort: selectionCohort } = storeToRefs(researchSelectionStore)

const openSessionDrawer = ref(false)
const sessionLoading = ref(false)
const sessionListLoading = ref(false)
const sessionListError = ref('')
const sessions = ref<Array<AnyRecord>>([])
const platformStatus = ref<AnyRecord | null>(null)
const platformStatusLoading = ref(false)
const platformStatusError = ref('')
const researchJobs = ref<Array<AnyRecord>>([])
const researchJobsSummary = ref<AnyRecord>({})
const researchJobsLoading = ref(false)
const researchJobsError = ref('')
const researchArtifacts = ref<Array<AnyRecord>>([])
const researchArtifactsLoading = ref(false)
const researchArtifactsError = ref('')
const leftNav = [
  { key: 'prep', label: '数据准备' },
  { type: 'divider', key: 'divider-1' },
  { key: 'table1', label: '基线特征' },
  { key: 'survival', label: '生存分析' },
  { key: 'regression', label: '回归分析' },
  { key: 'roc', label: '受试者工作特征' },
  { key: 'subgroup', label: '亚组分析' },
  { key: 'trend', label: '趋势分析' },
  { key: 'correlation', label: '相关性' },
  { type: 'divider', key: 'divider-2' },
  { key: 'export', label: '导出中心' },
]

const platformStatusLevel = computed(() => String(platformStatus.value?.level || 'yellow').toLowerCase())
const platformDependencyRows = computed(() => Array.isArray(platformStatus.value?.dependencies) ? platformStatus.value.dependencies : [])
const platformMissingRows = computed(() => platformDependencyRows.value.filter((item: any) => !item?.available))
const platformKpis = computed(() => {
  const counts = platformStatus.value?.counts || {}
  return [
    { label: '依赖就绪', value: `${platformDependencyRows.value.length - platformMissingRows.value.length}/${platformDependencyRows.value.length || 0}` },
    { label: '分析任务', value: Number(researchJobsSummary.value?.pending || 0) + Number(researchJobsSummary.value?.processing || 0) },
    { label: '导出产物', value: counts?.artifacts ?? researchArtifacts.value.length ?? 0 },
    { label: '研究队列', value: counts?.cohorts ?? cohorts.value.length ?? 0 },
  ]
})
const recentPlatformJobs = computed(() => researchJobs.value.slice(0, 5))
const recentPlatformArtifacts = computed(() => researchArtifacts.value.slice(0, 5))

const groupByOptions = [
  { label: '结局（存活/死亡）', value: 'outcome' },
  { label: 'ICU死亡', value: 'icu_mortality' },
  { label: '院内死亡', value: 'hospital_mortality' },
  { label: '28天死亡', value: 'mortality_28d' },
  { label: '出科去向', value: 'discharge_dest' },
  { label: 'ICU住院天数分层(<3/3-7/>=7天)', value: 'los_icu_group' },
  { label: '性别', value: 'sex' },
]
const patientScopeOptions = [
  { label: '全部', value: 'all' },
  { label: '在科', value: 'in_dept' },
  { label: '出科', value: 'out_dept' },
]
const variableOptions = variableCatalog.map((v) => ({ label: `${v.label} [${typeLabelCN(v.type).replace('变量', '')}]`, value: v.field }))
const continuousVariableOptions = computed(() => variableCatalog.filter((v) => v.type === 'continuous').map((v) => ({ label: v.label, value: v.field })))
const correlationVariableOptions = computed(() => variableCatalog
  .filter((v) => v.type === 'continuous')
  .map((v) => {
    const summary = getVarSummary(v.field)
    const nonNull = Number(summary.non_null_count || 0)
    const total = Number(summary.total_count || selectedPatientIds.value.length || 0)
    const suffix = total > 0 ? ` (${nonNull}/${total})` : ` (${nonNull})`
    return { label: `${v.label}${suffix}`, value: v.field }
  }))
const binaryVariableOptions = computed(() => variableCatalog.filter((v) => v.type === 'binary').map((v) => ({ label: v.label, value: v.field })))
const trendIndicatorOptions = computed(() => {
  const fromSelected = selectedVariables.value
    .filter((field) => variableCatalog.find((item) => item.field === field)?.type === 'continuous')
    .map((field) => ({ label: variableCatalog.find((item) => item.field === field)?.label || field, value: field }))
  const vitals = [
    { label: '心率', value: 'hr' },
    { label: '平均动脉压', value: 'map' },
    { label: '乳酸', value: 'lactate' },
    { label: '收缩压', value: 'sbp' },
    { label: '舒张压', value: 'dbp' },
    { label: '呼吸频率', value: 'rr' },
    { label: '血氧饱和度', value: 'spo2' },
    { label: '体温', value: 'temperature' },
  ]
  const map = new Map<string, { label: string; value: string }>()
  ;[...fromSelected, ...vitals].forEach((item) => {
    if (!item?.value) return
    if (!map.has(item.value)) map.set(item.value, item)
  })
  return Array.from(map.values())
})
const timeFieldOptions = [{ label: 'ICU住院天数', value: 'los_icu_days' }]
const eventFieldOptions = [{ label: 'ICU死亡', value: 'icu_mortality' }, { label: '院内死亡', value: 'hospital_mortality' }, { label: '28天死亡', value: 'mortality_28d' }]
const cohortOptions = computed(() => cohorts.value.map((c) => {
  const count = c.n_patients ?? c.patient_count ?? c.patient_ids?.length ?? 0
  const name = c.name || c.cohort_id || '未命名队列'
  const created = c.created_at ? formatCohortTime(c.created_at) : ''
  return { label: created ? `${name} (${count}) · ${created}` : `${name} (${count})`, value: c.cohort_id }
}))
const routeDeptCode = computed(() => String(route.query.dept_code || route.query.deptCode || '').trim())
const routeDeptName = computed(() => String(route.query.dept || route.query.department || '').trim())
const currentDeptCode = computed(() => routeDeptCode.value)
const currentDeptName = computed(() => deptNameByCode.value[currentDeptCode.value] || routeDeptName.value || '')
const currentDeptDisplay = computed(() => currentDeptName.value || currentDeptCode.value || '未知')
function patientScopeLabel(scopeValue?: string | null): string {
  const map: Record<string, string> = {
    in_dept: '在科',
    out_dept: '出科',
    all: '全部',
  }
  return map[String(scopeValue || 'all')] || '全部'
}
if (currentDeptCode.value && prepMode.value !== 'dept') {
  prepMode.value = 'dept'
}
const currentCohortSummary = computed(() => {
  if (prepMode.value === 'dept') {
    const dept = currentDeptDisplay.value || '当前科室'
    const countText = selectedPatientIds.value.length ? ` | ${selectedPatientIds.value.length}例` : ''
    return `${dept} ${patientScopeLabel(scope.patient_scope)}患者${countText}`
  }
  const snapshot = selectionCohort.value
  if (snapshot) {
    const countText = snapshot.patientCount ? ` | ${snapshot.patientCount}例` : ''
    return `${snapshot.name} | ${patientScopeLabel(snapshot.patientScope)}${countText}`
  }
  if (!scope.cohort_id) return ''
  const match = cohorts.value.find((c) => c.cohort_id === scope.cohort_id)
  if (!match) return ''
  const count = match.n_patients || (match.patient_ids?.length ?? 0)
  const timeText = match.filters?.time_range ? `${match.filters.time_range.start || ''} ~ ${match.filters.time_range.end || ''}` : ''
  return `${match.name || match.cohort_id} | ${count}例${timeText ? ` | ${timeText}` : ''}`
})
const variableGroups = computed(() => {
  const map = new Map<string, typeof variableCatalog>()
  variableCatalog.forEach((item) => {
    const key = item.category || '其他'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(item)
  })
  return Array.from(map.entries())
})
const appliedFilterCount = computed(() => Object.keys(appliedVariableFilters).length)
const cohortBuilderInitialFilters = computed<Array<{ field: string; operator: string; value: any }>>(() => {
  const base = (cohortSourceFilters.value || []).filter((item) => item && item.field && item.operator).map((item) => ({
    field: String(item.field),
    operator: String(item.operator),
    value: item.value,
  }))
  const dynamic = appliedConditions()
  if (!dynamic.length) return base
  const merged = [...base]
  dynamic.forEach((row) => {
    const idx = merged.findIndex((item) => String(item.field) === String(row.field))
    if (idx >= 0) merged[idx] = row
    else merged.push(row)
  })
  return merged
})
const cohortReady = computed(() => selectedPatientIds.value.length > 0)
const navCompletion = computed<Record<string, boolean>>(() => ({
  table1: Boolean(table1Result.value),
  survival: Boolean(survivalResult.value),
  regression: Boolean(regressionResult.value),
  roc: Boolean(rocResult.value),
  subgroup: Boolean(subgroupResult.value),
  trend: Boolean(trendResult.value),
  correlation: Boolean(correlationResult.value),
}))
const nextSteps = computed(() => [
  { key: 'table1', label: '生成基线特征表（表1）' },
  { key: 'survival', label: '运行生存分析' },
  { key: 'trend', label: '查看趋势' },
])
const showNextSteps = computed(() => cohortReady.value && scope.group_by)
const groupSummaryCards = computed(() => {
  const defaults = [
    { name: '组A', countText: '--', percentText: '--', type: 'survive' },
    { name: '组B', countText: '--', percentText: '--', type: 'death' },
  ]

  const total = Number(cohortPreviewCount.value || selectedPatientIds.value.length || 0)
  const field = String(scope.group_by || '').trim()
  const summary = getVarSummary(field)
  const dist = (summary.distribution || {}) as Record<string, AnyRecord>
  const norm = (value: string) => String(value || '').trim().toLowerCase()
  const findCount = (keys: string[]) => {
    for (const [rawKey, info] of Object.entries(dist)) {
      if (keys.includes(norm(rawKey))) return Number(info?.count || 0)
    }
    return 0
  }

  const configMap: Record<string, Array<{ name: string; keys: string[]; type: string }>> = {
    outcome: [
      { name: '存活组', keys: ['alive', '存活', 'survive'], type: 'survive' },
      { name: '死亡组', keys: ['dead', 'death', '死亡', 'deceased'], type: 'death' },
    ],
    icu_mortality: [
      { name: '存活组', keys: ['0', 'false', 'no', 'alive', '存活'], type: 'survive' },
      { name: '死亡组', keys: ['1', 'true', 'yes', 'dead', '死亡'], type: 'death' },
    ],
    hospital_mortality: [
      { name: '存活组', keys: ['0', 'false', 'no', 'alive', '存活'], type: 'survive' },
      { name: '死亡组', keys: ['1', 'true', 'yes', 'dead', '死亡'], type: 'death' },
    ],
    mortality_28d: [
      { name: '28天存活组', keys: ['0', 'false', 'no', 'alive', '存活'], type: 'survive' },
      { name: '28天死亡组', keys: ['1', 'true', 'yes', 'dead', '死亡'], type: 'death' },
    ],
  }

  const configured = configMap[field]
  if (configured && Object.keys(dist).length) {
    return configured.map((item) => {
      const count = findCount(item.keys)
      return {
        name: item.name,
        countText: `${count} 例`,
        percentText: total > 0 ? `${((count / total) * 100).toFixed(1)}%` : '--',
        type: item.type,
      }
    })
  }

  const groups = table1Result.value?.groups
  if (!groups || !groups.length) return defaults
  const parsed = groups.slice(0, 2).map((text: string, idx: number) => {
    const match = /(.+?)\s*\(n\s*=\s*(\d+)/i.exec(String(text))
    const name = match ? match[1] : `组${idx + 1}`
    const count = match ? Number(match[2]) : undefined
    const percent = total && count != null ? `${((count / total) * 100).toFixed(1)}%` : '--'
    return {
      name,
      countText: count != null ? `${count} 例` : '--',
      percentText: percent,
      type: idx === 0 ? 'survive' : 'death',
    }
  })
  return parsed.length ? parsed : defaults
})
function patientIdsFromRow(row: AnyRecord | undefined): string[] {
  if (!row) return []
  const pools = [row.patient_ids, row.patients, row.members]
  for (const pool of pools) {
    if (Array.isArray(pool) && pool.length) {
      return pool.map((id: any) => String(id || '').trim()).filter(Boolean)
    }
  }
  return []
}

function variableMeta(field: string): AnyRecord | undefined {
  return variableCatalog.find((item) => item.field === field)
}

function filterFieldAlias(field: string): string {
  const map: Record<string, string> = {
    sofa_admission: 'sofa_max',
    apache2: 'apache2_max',
    primary_diagnosis: 'diagnosis',
    icu_mortality: 'outcome',
  }
  return map[field] || field
}

function inverseFilterField(field: string): string {
  const map: Record<string, string> = {
    sofa_max: 'sofa_admission',
    apache2_max: 'apache2',
    diagnosis: 'primary_diagnosis',
    outcome: 'icu_mortality',
  }
  return map[field] || field
}

function clearAllVariableFilters(resetDraft = false): void {
  Object.keys(appliedVariableFilters).forEach((key) => delete appliedVariableFilters[key])
  if (resetDraft) Object.keys(variableFilterDrafts).forEach((key) => delete variableFilterDrafts[key])
  expandedVariableField.value = ''
}

function seedDraft(field: string): AnyRecord {
  const meta = variableMeta(field)
  if (!meta) return { mode: 'none', min: null, max: null, selected: [] as string[] }
  if (meta.type === 'continuous') return { mode: 'none', min: null, max: null, selected: [] as string[] }
  if (meta.type === 'categorical') return { mode: 'none', min: null, max: null, selected: [] as string[] }
  return { mode: 'none', min: null, max: null, selected: [] as string[] }
}

function draftFilter(field: string): AnyRecord {
  if (!variableFilterDrafts[field]) variableFilterDrafts[field] = seedDraft(field)
  return variableFilterDrafts[field]
}

function normalizeBinaryLabel(value: string): string {
  const token = String(value || '').trim().toLowerCase()
  if (['1', 'yes', 'y', 'true', '男', '死亡', 'dead'].includes(token)) return '是'
  if (['0', 'no', 'n', 'false', '女', '存活', 'alive'].includes(token)) return '否'
  return value
}

function categoryOptions(field: string): Array<{ label: string; value: string; count: number }> {
  const dist = getVarSummary(field).distribution || {}
  return Object.entries(dist).map(([key, info]: [string, any]) => ({
    label: key === 'M' ? '男' : key === 'F' ? '女' : key,
    value: key,
    count: Number(info?.count || 0),
  }))
}

function decodeIcdChoice(raw: string): { code: string; name: string } | null {
  const text = String(raw || '').trim()
  if (!text) return null
  try {
    const row = JSON.parse(text)
    if (row && typeof row === 'object') {
      const code = String((row as any).code || '').trim()
      const name = String((row as any).name || '').trim()
      if (code || name) return { code, name }
    }
  } catch {
    // ignore
  }
  return { code: '', name: text }
}

function diagnosisSelectedKeywords(field: string): string[] {
  const selected = (draftFilter(field).selected || []) as string[]
  const keywords: string[] = []
  selected.forEach((item) => {
    const parsed = decodeIcdChoice(item)
    if (!parsed) return
    if (parsed.code) keywords.push(parsed.code)
    if (parsed.name) keywords.push(parsed.name)
  })
  return Array.from(new Set(keywords.filter(Boolean)))
}

async function fetchIcdOptions(keyword = ''): Promise<void> {
  const q = String(keyword || '').trim()
  icdSearch.loading = true
  try {
    const res = await getResearchIcdSearch({ q, limit: 30 })
    const rows: AnyRecord[] = Array.isArray(res.data?.items) ? res.data.items : []
    icdSearch.options = rows.map((item) => {
      const code = String(item?.code || '').trim()
      const name = String(item?.name || '').trim()
      const py = String(item?.py || '').trim()
      const value = JSON.stringify({ code, name })
      const label = py ? `${code || '--'} ${name || '--'} (${py})` : `${code || '--'} ${name || '--'}`
      return { value, label, code, name }
    })
  } catch {
    icdSearch.options = []
  } finally {
    icdSearch.loading = false
  }
}

function onIcdSearch(value: string): void {
  icdSearch.keyword = String(value || '').trim()
  if (icdSearchTimer) clearTimeout(icdSearchTimer)
  icdSearchTimer = setTimeout(() => {
    fetchIcdOptions(icdSearch.keyword)
  }, 250)
}

function onIcdDropdownOpen(open: boolean): void {
  if (!open) return
  if (!icdSearch.options.length) {
    fetchIcdOptions(icdSearch.keyword)
  }
}

function onDiagnosisIcdSelect(field: string, values: any): void {
  const draft = draftFilter(field)
  draft.selected = Array.isArray(values) ? values.map((item) => String(item || '').trim()).filter(Boolean) : []
}

function binaryCount(field: string, yes: boolean): number {
  const dist = getVarSummary(field).distribution || {}
  let total = 0
  Object.entries(dist).forEach(([key, info]: [string, any]) => {
    const normalized = normalizeBinaryLabel(key)
    if ((yes && normalized === '是') || (!yes && normalized === '否')) total += Number(info?.count || 0)
  })
  return total
}

function quickPresets(field: string): Array<{ label: string; min: number | null; max: number | null }> {
  if (field === 'age') return [{ label: '<60岁', min: null, max: 59 }, { label: '≥60岁', min: 60, max: null }, { label: '≥65岁', min: 65, max: null }, { label: '≥75岁', min: 75, max: null }, { label: '≥80岁', min: 80, max: null }]
  if (field === 'sofa_admission') return [{ label: '<6', min: null, max: 5 }, { label: '≥6', min: 6, max: null }, { label: '≥8', min: 8, max: null }, { label: '≥10', min: 10, max: null }, { label: '≥12', min: 12, max: null }]
  if (field === 'los_icu_days') return [{ label: '<3天', min: null, max: 2 }, { label: '≥3天', min: 3, max: null }, { label: '≥7天', min: 7, max: null }, { label: '≥14天', min: 14, max: null }, { label: '≥28天', min: 28, max: null }]
  if (field === 'apache2') return [{ label: '<15', min: null, max: 14 }, { label: '≥15', min: 15, max: null }, { label: '≥20', min: 20, max: null }, { label: '≥25', min: 25, max: null }]
  return []
}

function fillContinuousQuick(field: string, min: number | null, max: number | null): void {
  const draft = draftFilter(field)
  draft.mode = 'range'
  draft.min = min
  draft.max = max
}

function continuousPlaceholder(field: string, side: 'min' | 'max'): string {
  const range = getVarSummary(field).range || {}
  const value = side === 'min' ? range.min : range.max
  if (value == null) return side === 'min' ? '最小值' : '最大值'
  return side === 'min' ? `最小 ${Number(value).toFixed(0)}` : `最大 ${Number(value).toFixed(0)}`
}

function continuousOverview(field: string): string {
  const s = getVarSummary(field)
  const isAge = field === 'age'
  const rangeText = s?.range ? `${Number(s.range.min).toFixed(0)}~${Number(s.range.max).toFixed(0)}` : '--'
  const meanText = s?.mean != null ? `${Number(s.mean).toFixed(isAge ? 0 : 1)}±${Number(s.std || 0).toFixed(isAge ? 0 : 1)}` : '--'
  const medianText = s?.median != null ? Number(s.median).toFixed(isAge ? 0 : 1) : '--'
  return `当前队列：${rangeText}，均值 ${meanText}，中位数 ${medianText}`
}

function toggleCategoryValue(field: string, value: string): void {
  const draft = draftFilter(field)
  const all = categoryOptions(field).map((item) => item.value)
  if (!Array.isArray(draft.selected)) draft.selected = []
  if (!draft.selected.length) draft.selected = [...all]
  if (draft.selected.includes(value)) {
    draft.selected = draft.selected.filter((item: string) => item !== value)
  } else {
    draft.selected = [...draft.selected, value]
  }
}

function isCategoryChecked(field: string, value: string): boolean {
  const selected = draftFilter(field).selected || []
  if (!selected.length) return true
  return selected.includes(value)
}

function hasVariableFilter(field: string): boolean {
  return Boolean(appliedVariableFilters[field])
}

function filterSummary(field: string): string {
  return String(appliedVariableFilters[field]?.summary || '')
}

function toggleVariablePanel(field: string): void {
  if (expandedVariableField.value === field) {
    expandedVariableField.value = ''
    return
  }
  const applied = appliedVariableFilters[field]
  variableFilterDrafts[field] = applied ? { ...applied, selected: [...(applied.selected || [])] } : seedDraft(field)
  if (field === 'primary_diagnosis' && variableFilterDrafts[field].mode === 'include' && !icdSearch.options.length) {
    fetchIcdOptions(icdSearch.keyword)
  }
  if (field !== 'primary_diagnosis' && variableMeta(field)?.type === 'categorical' && variableFilterDrafts[field].mode === 'include' && !variableFilterDrafts[field].selected?.length) {
    variableFilterDrafts[field].selected = categoryOptions(field).map((item) => item.value)
  }
  expandedVariableField.value = field
}

function normalizeFilterSummary(field: string, payload: AnyRecord): string {
  const meta = variableMeta(field)
  if (!meta) return ''
  if (meta.type === 'continuous') {
    if (payload.min != null && payload.max != null) return `${payload.min}-${payload.max}${field === 'age' ? '岁' : field === 'los_icu_days' ? '天' : ''}`
    if (payload.min != null) return `≥${payload.min}${field === 'age' ? '岁' : field === 'los_icu_days' ? '天' : ''}`
    if (payload.max != null) return `≤${payload.max}${field === 'los_icu_days' ? '天' : ''}`
    return ''
  }
  if (meta.type === 'binary') return payload.mode === 'yes' ? '=是' : payload.mode === 'no' ? '=否' : ''
  if (field === 'primary_diagnosis') {
    const selected = (payload.selected || []) as string[]
    const labels = selected
      .map((raw) => decodeIcdChoice(raw))
      .filter((row): row is { code: string; name: string } => Boolean(row))
      .map((row) => row.name || row.code)
      .filter(Boolean)
    if (!labels.length) return ''
    if (labels.length === 1) return `=${labels[0]}`
    return `已选${labels.length}项`
  }
  const allValues = categoryOptions(field).map((item) => item.value)
  const selected = (payload.selected || []) as string[]
  if (selected.length === 1) {
    const token = selected[0]
    return `=${token === 'M' ? '男' : token === 'F' ? '女' : token}`
  }
  if (allValues.length && selected.length && selected.length < allValues.length) {
    const excluded = allValues.filter((item) => !selected.includes(item))
    if (excluded.length > 0 && excluded.length <= 2) {
      const label = excluded.map((token) => (token === 'M' ? '男' : token === 'F' ? '女' : token)).join('/')
      return `排除:${label}`
    }
  }
  return selected.length ? `已选${selected.length}类` : ''
}

function apiErrorMessage(error: any, fallback: string): string {
  const detail = error?.response?.data?.detail || error?.message || ''
  const lower = String(detail).toLowerCase()
  if (lower.includes('timeout')) {
    return '请求超时：科研分析任务仍可能在后台执行中，请稍后重试或缩小分析变量范围'
  }
  return detail || fallback
}

function buildAppliedCondition(field: string): AnyRecord | null {
  const draft = draftFilter(field)
  const meta = variableMeta(field)
  if (!meta || draft.mode === 'none') return null
  if (meta.type === 'continuous') {
    const min = draft.min == null || draft.min === '' ? null : Number(draft.min)
    const max = draft.max == null || draft.max === '' ? null : Number(draft.max)
    if (min == null && max == null) return null
    return {
      mode: 'range' as VariableFilterMode,
      min,
      max,
      summary: normalizeFilterSummary(field, { min, max }),
      condition: { field: filterFieldAlias(field), operator: 'range', value: [min, max] },
    }
  }
  if (meta.type === 'binary') {
    if (draft.mode !== 'yes' && draft.mode !== 'no') return null
    const alias = filterFieldAlias(field)
    const value = alias === 'outcome' ? (draft.mode === 'yes' ? 'dead' : 'alive') : (draft.mode === 'yes' ? 'yes' : 'no')
    return {
      mode: draft.mode as VariableFilterMode,
      summary: normalizeFilterSummary(field, { mode: draft.mode }),
      condition: { field: alias, operator: 'eq', value },
    }
  }
  if (draft.mode !== 'include') return null
  if (field === 'primary_diagnosis') {
    const selected = ((draft.selected || []) as string[]).filter(Boolean)
    if (!selected.length) return null
    const keywords = diagnosisSelectedKeywords(field)
    if (!keywords.length) return null
    return {
      mode: 'include' as VariableFilterMode,
      selected,
      summary: normalizeFilterSummary(field, { selected }),
      condition: { field: filterFieldAlias(field), operator: 'contains', value: keywords },
    }
  }
  const allValues = categoryOptions(field).map((item) => item.value)
  const selected = ((draft.selected || []).length ? draft.selected : allValues).filter(Boolean)
  if (!selected.length) return null
  if (allValues.length && selected.length === allValues.length) return null
  const condition = field === 'primary_diagnosis'
    ? { field: filterFieldAlias(field), operator: 'contains', value: selected.join('|') }
    : selected.length === 1
      ? { field: filterFieldAlias(field), operator: 'eq', value: selected[0] }
      : { field: filterFieldAlias(field), operator: 'contains', value: selected.join('|') }
  return {
    mode: 'include' as VariableFilterMode,
    selected,
    summary: normalizeFilterSummary(field, { selected }),
    condition,
  }
}

function appliedConditions(): CohortFilter[] {
  return Object.values(appliedVariableFilters)
    .map((item: AnyRecord) => item.condition)
    .filter((item): item is CohortFilter => Boolean(item?.field && item?.operator))
}

async function refreshCohortByVariableFilters(): Promise<void> {
  if (!basePatientIds.value.length) return
  const seq = ++cohortBuildSeq
  const filters = appliedConditions()
  if (!filters.length) {
    scope.patient_text = basePatientIds.value.join('\n')
    cohortPreviewCount.value = basePatientIds.value.length
    if (selectionCohort.value) {
      researchSelectionStore.setCohort({ ...selectionCohort.value, patientCount: basePatientIds.value.length })
    }
    await fetchVariableSummary(true)
    return
  }
  try {
    const res = await postResearchCohortBuild({
      patient_ids: basePatientIds.value,
      filters,
      department: scope.department || null,
      dept_code: currentDeptCode.value || null,
      patient_scope: scope.patient_scope,
    })
    const ids = Array.isArray(res.data?.patient_ids) ? res.data.patient_ids.map((id: any) => String(id || '')).filter(Boolean) : []
    if (seq !== cohortBuildSeq) return
    scope.patient_text = ids.join('\n')
    cohortPreviewCount.value = ids.length
    if (selectionCohort.value) {
      researchSelectionStore.setCohort({ ...selectionCohort.value, patientCount: ids.length })
    }
    await fetchVariableSummary(true)
  } catch (e: any) {
    message.error(apiErrorMessage(e, '筛选应用失败'))
  }
}

async function applyVariableFilter(field: string): Promise<void> {
  const next = buildAppliedCondition(field)
  if (next) {
    appliedVariableFilters[field] = next
    if (!selectedVariables.value.includes(field)) {
      researchSelectionStore.selectVariables([field])
    }
  } else {
    delete appliedVariableFilters[field]
  }
  expandedVariableField.value = ''
  await refreshCohortByVariableFilters()
}

async function clearVariableFilter(field: string): Promise<void> {
  delete appliedVariableFilters[field]
  variableFilterDrafts[field] = seedDraft(field)
  expandedVariableField.value = ''
  await refreshCohortByVariableFilters()
}

function hydrateVariableFilters(filters: AnyRecord[] | undefined | null): void {
  clearAllVariableFilters(true)
  ;(filters || []).forEach((row) => {
    const field = inverseFilterField(String(row?.field || ''))
    if (!variableMeta(field)) return
    const operator = String(row?.operator || '').toLowerCase()
    const value = row?.value
    if (variableMeta(field)?.type === 'continuous') {
      let min: number | null = null
      let max: number | null = null
      if (operator === 'range' && Array.isArray(value)) {
        min = value[0] == null ? null : Number(value[0])
        max = value[1] == null ? null : Number(value[1])
      } else if (operator === 'gte' || operator === '>=' || operator === 'gt' || operator === '>') {
        min = value == null ? null : Number(value)
      } else if (operator === 'lte' || operator === '<=' || operator === 'lt' || operator === '<') {
        max = value == null ? null : Number(value)
      }
      if (min != null || max != null) {
        appliedVariableFilters[field] = { mode: 'range', min, max, summary: normalizeFilterSummary(field, { min, max }), condition: { field: filterFieldAlias(field), operator: 'range', value: [min, max] } }
      }
      return
    }
    if (variableMeta(field)?.type === 'binary') {
      const text = String(value || '').toLowerCase()
      const alias = filterFieldAlias(field)
      const yesValue = alias === 'outcome' ? 'dead' : 'yes'
      const noValue = alias === 'outcome' ? 'alive' : 'no'
      if (['yes', '1', 'true', 'dead', '死亡'].includes(text)) {
        appliedVariableFilters[field] = { mode: 'yes', summary: '=是', condition: { field: alias, operator: 'eq', value: yesValue } }
      } else if (['no', '0', 'false', 'alive', '存活'].includes(text)) {
        appliedVariableFilters[field] = { mode: 'no', summary: '=否', condition: { field: alias, operator: 'eq', value: noValue } }
      }
      return
    }
    if (operator === 'eq' && value != null) {
      const selected = [String(value)]
      appliedVariableFilters[field] = { mode: 'include', selected, summary: normalizeFilterSummary(field, { selected }), condition: { field: filterFieldAlias(field), operator: 'eq', value: selected[0] } }
      return
    }
    if (operator === 'contains' && value != null) {
      const selected = Array.isArray(value)
        ? value.map((item) => String(item || '').trim()).filter(Boolean).map((item) => JSON.stringify({ code: '', name: item }))
        : String(value).split('|').map((item) => item.trim()).filter(Boolean).map((item) => JSON.stringify({ code: '', name: item }))
      if (selected.length) {
        const rawValue = Array.isArray(value) ? value : String(value)
        appliedVariableFilters[field] = { mode: 'include', selected, summary: normalizeFilterSummary(field, { selected }), condition: { field: filterFieldAlias(field), operator: 'contains', value: rawValue } }
      }
    }
  })
}

function applyCohortSelection(cohortId: string | null | undefined) {
  const token = String(cohortId || '').trim()
  if (!token) return
  const matched = cohorts.value.find((item) => String(item.cohort_id) === token || String(item._id) === token)
  if (!matched) return
  cohortSourceFilters.value = Array.isArray(matched.filters) ? matched.filters : []
  const ids = patientIdsFromRow(matched)
  basePatientIds.value = [...ids]
  originalCohortCount.value = ids.length
  hydrateVariableFilters(matched.filters)
  if (ids.length) {
    scope.patient_text = ids.join('\n')
  }
  scope.patient_scope = ['in_dept', 'out_dept', 'all'].includes(String(matched.patient_scope || '')) ? matched.patient_scope : 'all'
  researchSelectionStore.setCohort({ id: token, name: matched.name || matched.cohort_id || '自定义队列', type: 'saved', patientCount: ids.length, department: matched.department || null, deptCode: matched.dept_code || null, patientScope: scope.patient_scope })
  if (!scope.department && matched.department) {
    scope.department = matched.department
  }
  fetchVariableSummary(true)
}

watch(() => scope.cohort_id, (val) => applyCohortSelection(val))
watch(patientIdsVersion, () => {
  fetchVariableSummary(true)
}, { immediate: true })

watch(cohorts, () => {
  if (scope.cohort_id) applyCohortSelection(scope.cohort_id)
})
watch(selectedPatientIds, (ids) => {
  cohortPreviewCount.value = ids.length
})

watch(prepMode, (mode) => {
  if (mode === 'dept') {
    scope.cohort_id = ''
    cohortSourceFilters.value = []
    clearAllVariableFilters(true)
    loadPatientsByDepartment()
    return
  }
  if (!mode) {
    scope.cohort_id = ''
    scope.patient_text = ''
    basePatientIds.value = []
    originalCohortCount.value = 0
    cohortPreviewCount.value = 0
    cohortSourceFilters.value = []
    clearAllVariableFilters(true)
    researchSelectionStore.setCohort(null)
    return
  }
}, { immediate: true })
watch(() => scope.patient_scope, async (val, oldVal) => {
  if (val === oldVal) return
  if (prepMode.value === 'dept') {
    await loadPatientsByDepartment()
  }
})
watch(selectedVariables, (val) => {
  scope.variables = [...val]
  const continuous = val.filter((field) => variableCatalog.find((v) => v.field === field)?.type === 'continuous')
  if (analysisAutoSync.regression) regressionForm.predictors = [...val]
  if (analysisAutoSync.roc) rocForm.predictors = [...continuous]
  if (analysisAutoSync.correlation) correlationForm.variables = [...continuous]
}, { immediate: true })

function disableAutoSync(key: 'regression' | 'roc' | 'trend' | 'correlation'): void {
  analysisAutoSync[key] = false
}

const table1Rows = computed(() => ((table1Result.value?.rows || []) as AnyRecord[]).map((r, i) => ({ ...r, row_key: `${i}_${r.variable || r.field || ''}` })))
const table1Columns = computed(() => {
  const groups = (table1Result.value?.groups || []) as string[]
  return [{ title: '变量', dataIndex: 'variable', key: 'var' }, ...groups.map((g, i) => ({ title: g, dataIndex: ['values', i], key: `g${i}` })), { title: '统计量', dataIndex: 'statistic', key: 's' }, { title: 'P值', dataIndex: 'p_display', key: 'p' }]
})
const table1QualityColumns = [
  { title: '变量', dataIndex: 'label', key: 'label' },
  { title: '非空数', dataIndex: 'non_null_count', key: 'non_null_count' },
  { title: '总样本', dataIndex: 'total_count', key: 'total_count' },
  { title: '非空率', dataIndex: 'non_null_rate_display', key: 'non_null_rate_display' },
]
const table1QualityRows = computed(() => scope.variables
  .map((field) => {
    const summary = getVarSummary(field)
    const nonNull = Number(summary.non_null_count || 0)
    const total = Number(summary.total_count || selectedPatientIds.value.length || 0)
    return {
      field,
      label: variableCatalog.find((item) => item.field === field)?.label || field,
      non_null_count: nonNull,
      total_count: total,
      non_null_rate_display: total > 0 ? `${((nonNull / total) * 100).toFixed(1)}%` : '—',
    }
  })
  .filter((row) => row.total_count > 0)
  .sort((a, b) => a.non_null_count - b.non_null_count)
  .slice(0, 8))
const table1QualityTips = computed(() => {
  const tips: string[] = []
  const low = table1QualityRows.value.filter((row) => row.total_count > 0 && row.non_null_count / row.total_count < 0.5)
  if (low.length) tips.push(`部分变量缺失较多：${low.map((row) => row.label).join('、')}`)
  if (Number(table1Result.value?.n_total || 0) > 0 && Number(table1Result.value?.n_total || 0) < 30) {
    tips.push(`总样本量较小（n=${Number(table1Result.value?.n_total || 0)}）`)
  }
  return tips
})

const survivalOption = computed(() => {
  const curves = (survivalResult.value?.kaplan_meier?.curves || {}) as Record<string, AnyRecord>
  const names = Object.keys(curves)
  if (!names.length) return null
  return {
    backgroundColor: '#fff',
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    xAxis: { type: 'value', name: '时间（天）' },
    yAxis: { type: 'value', name: '生存概率', min: 0, max: 1 },
    series: names.map((n) => {
      const curve = curves[n] || {}
      const timeline = curve.timeline || []
      const survival = curve.survival || []
      return {
        name: n,
        type: 'line',
        step: 'end',
        showSymbol: false,
        data: timeline.map((x: number, i: number) => [x, survival[i]]),
      }
    }),
  }
})

function patientIds(): string[] { return Array.from(new Set(String(scope.patient_text || '').split(/[\n,;\s]+/g).map((x) => x.trim()).filter(Boolean))) }
watch(() => scope.patient_text, () => {
  researchSelectionStore.setPatientIds(patientIds())
}, { immediate: true })
function scopedPatientIds(): string[] {
  const ids = (selectedPatientIds.value || []).map((x) => String(x || '').trim()).filter(Boolean)
  if (ids.length) return Array.from(new Set(ids))
  return patientIds()
}
function scopePayload() {
  return {
    patient_ids: scopedPatientIds(),
    cohort_id: scope.cohort_id || null,
    department: scope.department || null,
    dept_code: currentDeptCode.value || null,
    patient_scope: scope.patient_scope,
  }
}
function variablePayload() {
  return scope.variables
    .map((f) => variableCatalog.find((v) => v.field === f))
    .filter((v): v is (typeof variableCatalog)[number] => Boolean(v))
    .map((v) => ({ field: v.field, label: v.label, type: v.type }))
}

async function fetchVariableSummary(silent = false) {
  const ids = selectedPatientIds.value
  const seq = ++summaryFetchSeq
  if (!ids.length) {
    researchSelectionStore.setVariableSummaries({})
    return
  }
  try {
    const res = await postResearchVariableSummary({
      patient_ids: ids,
      fields: variableCatalog.map((v) => v.field),
    })
    const summaries = res.data?.summaries || res.data || {}
    const mapped: Record<string, AnyRecord> = {}
    variableCatalog.forEach((item) => {
      mapped[item.field] = summaries[item.field] || {}
    })
    if (seq !== summaryFetchSeq) return
    researchSelectionStore.setVariableSummaries(mapped)
  } catch (e: any) {
    if (!silent) {
      message.warning(apiErrorMessage(e, '变量摘要加载失败'))
    }
  }
}

function getVarSummary(field: string): AnyRecord {
  return (variableSummaries.value || {})[field] || {}
}

function typeLabelCN(type: string): string {
  const map: Record<string, string> = {
    continuous: '连续变量',
    categorical: '分类变量',
    binary: '二分类变量',
  }
  return map[type] || '变量'
}

function variableTypeBadge(type: string): string {
  const map: Record<string, string> = {
    continuous: '连续',
    categorical: '分类',
    binary: '二分',
  }
  return map[type] || '变量'
}

function applicableLabel(list?: string[]): string {
  if (!Array.isArray(list) || !list.length) return ''
  const map: Record<string, string> = {
    table1: '基线特征',
    survival: '生存',
    regression: '回归',
    roc: '受试者工作特征',
    subgroup: '亚组',
    trend: '趋势',
    correlation: '相关性',
  }
  return list.map((item) => map[item] || item).join(' ')
}

async function loadPatientsByDepartment() {
  const deptCode = String(currentDeptCode.value || '').trim()
  const deptName = String(currentDeptName.value || routeDeptName.value || '').trim()
  if (!deptCode && !deptName) {
    message.warning('未检测到科室信息')
    return
  }
  patientLoadLoading.value = true
  try {
    const params: AnyRecord = { patient_scope: scope.patient_scope }
    if (deptCode) params.dept_code = deptCode
    else params.dept = deptName
    const res = await getPatients(params)
    const list: AnyRecord[] = Array.isArray(res.data?.patients) ? res.data.patients : []
    if (list.length && deptCode && !deptNameByCode.value[deptCode]) {
      const deptName = String(list[0]?.hisDept || list[0]?.dept || '').trim()
      if (deptName) deptNameByCode.value[deptCode] = deptName
    }
    const ids = list
      .map((row) => row?._id || row?.patient_id || row?.patientId || row?.hisPid || row?.pid)
      .map((id) => String(id || '').trim())
      .filter(Boolean)
    basePatientIds.value = [...ids]
    originalCohortCount.value = ids.length
    cohortSourceFilters.value = []
    clearAllVariableFilters(true)
    scope.patient_text = ids.join('\n')
    cohortPreviewCount.value = ids.length
    researchSelectionStore.setCohort({ id: null, name: `${currentDeptDisplay.value || deptName || deptCode || '当前科室'} ${patientScopeLabel(scope.patient_scope)}患者`, type: 'dept', patientCount: ids.length, department: currentDeptName.value || deptName || null, deptCode: currentDeptCode.value || null, patientScope: scope.patient_scope })
    await fetchVariableSummary()
    if (ids.length) {
      message.success(`已载入 ${ids.length} 名${patientScopeLabel(scope.patient_scope)}患者`)
    } else {
      message.info(`当前科室暂无${patientScopeLabel(scope.patient_scope)}患者`)
    }
  } catch (e: any) {
    message.error(apiErrorMessage(e, '患者加载失败'))
  } finally {
    patientLoadLoading.value = false
  }
}





async function loadCohorts() {
  try {
    const res = await listResearchCohorts({ limit: 200 })
    cohorts.value = Array.isArray(res.data?.cohorts) ? res.data.cohorts : []
  } catch {
    cohorts.value = []
  }
}

async function resolveResult(req: Promise<any>) { const res = await req; const data = res?.data || {}; if (data.async && data.task_id) { message.info('后台计算中...'); for (let i = 0; i < 120; i += 1) { const s = await getResearchAnalyticsTaskStatus(String(data.task_id)); const row = s.data || {}; if (row.status === 'completed') return row.result || {}; if (row.status === 'failed') throw new Error(row.error || '任务失败'); await new Promise((r) => setTimeout(r, 1500)) } throw new Error('任务超时') } return data.result || data }
function ensureCohortReady(target: string): boolean {
  if (target !== 'prep' && !cohortReady.value) {
    message.warning('请先在「数据准备」中选择研究队列')
    return false
  }
  return true
}

function onTabSelect(item: AnyRecord): void {
  if (item.type === 'divider') return
  if (!ensureCohortReady(item.key)) {
    tab.value = item.key
    return
  }
  tab.value = item.key
}

function resetTable1(): void {
  scope.variables = variableCatalog.map((v) => v.field)
}

function jumpToTab(key: string): void {
  tab.value = key
}

function isVariableSelected(field: string): boolean {
  return selectedVariables.value.includes(field)
}

function toggleVariable(field: string): void {
  researchSelectionStore.toggleVariable(field)
}

function selectAllVariables(): void {
  researchSelectionStore.setSelectedVariables(variableCatalog.map((v) => v.field))
}

function clearAllVariables(): void {
  researchSelectionStore.clearSelectedVariables()
}

function togglePrepMode(mode: 'saved' | 'dept' | 'builder'): void {
  prepMode.value = prepMode.value === mode ? '' : mode
}

function openCohortBuilder(): void {
  prepMode.value = 'builder'
  cohortBuilderOpen.value = true
}

function onCohortBuilderSaved(payload: { cohort: AnyRecord; filters: AnyRecord[] }): void {
  const data = payload.cohort || {}
  const ids = Array.isArray(data.patient_ids) ? data.patient_ids.map((id: any) => String(id || '')).filter(Boolean) : []
  cohortSourceFilters.value = Array.isArray(payload.filters) ? payload.filters : []
  basePatientIds.value = [...ids]
  originalCohortCount.value = ids.length
  hydrateVariableFilters(payload.filters)
  scope.patient_text = ids.join('\n')
  scope.cohort_id = data.cohort_id || scope.cohort_id
  scope.patient_scope = ['in_dept', 'out_dept', 'all'].includes(String(data.patient_scope || '')) ? data.patient_scope : scope.patient_scope
  prepMode.value = 'builder'
  researchSelectionStore.setCohort({ id: data.cohort_id || null, name: data.name || '自定义队列', type: 'builder', patientCount: ids.length, department: scope.department || currentDeptName.value || null, deptCode: currentDeptCode.value || null, patientScope: scope.patient_scope })
  cohorts.value = [{ cohort_id: data.cohort_id, name: data.name, n_patients: data.patient_count, patient_ids: ids, filters: payload.filters, department: scope.department || currentDeptName.value || null, dept_code: currentDeptCode.value || null, patient_scope: scope.patient_scope }, ...cohorts.value.filter((c) => c.cohort_id !== data.cohort_id)]
}

async function removeCohort(cohortId: string): Promise<void> {
  if (!cohortId) return
  Modal.confirm({
    title: '删除队列',
    content: '确认删除该队列吗？',
    onOk: async () => {
      try {
        await deleteResearchCohort(cohortId)
        cohorts.value = cohorts.value.filter((item) => item.cohort_id !== cohortId)
        message.success('队列已删除')
      } catch (e: any) {
        message.error(apiErrorMessage(e, '删除队列失败'))
      }
    },
  })
}

function toggleCategory(category: string): void {
  const fields = variableCatalog.filter((v) => v.category === category).map((v) => v.field)
  const allSelected = fields.every((field) => selectedVariables.value.includes(field))
  if (allSelected) {
    const remaining = selectedVariables.value.filter((field) => !fields.includes(field))
    researchSelectionStore.setSelectedVariables(remaining)
    categoryFlash[category] = '已清空'
  } else {
    researchSelectionStore.selectVariables(fields)
    categoryFlash[category] = '已全选'
  }
  setTimeout(() => {
    categoryFlash[category] = ''
  }, 1000)
}

async function exportTableCsv(): Promise<void> {
  if (!table1Result.value) return
  try {
    const res = await postResearchExportTable({ title: table1Result.value.title || '基线特征表', table_data: table1Result.value, format: 'csv', filename: `table1_${Date.now()}` })
    addExport(res.data || {}, '基线特征表（电子表格）', 'tables')
    message.success('电子表格导出成功')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '导出失败'))
  }
}

async function loadDeptNameMap(): Promise<void> {
  try {
    const res = await getDepartments()
    const rows = Array.isArray(res.data?.departments) ? res.data.departments : []
    const next: Record<string, string> = { ...deptNameByCode.value }
    rows.forEach((row: AnyRecord) => {
      const code = String(row?.deptCode || row?.code || row?.dept_code || '').trim()
      const name = String(row?.dept || row?.name || '').trim()
      if (code && name) next[code] = name
      if (name && !next[name]) next[name] = name
    })
    if (routeDeptCode.value && routeDeptName.value && !next[routeDeptCode.value]) {
      next[routeDeptCode.value] = routeDeptName.value
    }
    deptNameByCode.value = next
  } catch {
    if (routeDeptCode.value && routeDeptName.value) {
      deptNameByCode.value = { ...deptNameByCode.value, [routeDeptCode.value]: routeDeptName.value }
    }
  }
}

function correlationMethodLabel(method: string): string {
  const map: Record<string, string> = {
    auto: '自动选择',
    pearson: '皮尔逊',
    spearman: '斯皮尔曼',
  }
  return map[String(method || '').toLowerCase()] || method
}

function analysisTitle(key: string): string {
  const map: Record<string, string> = {
    table1: '基线特征表',
    survival: '生存分析',
    regression: '回归分析',
    roc: '受试者工作特征分析',
    subgroup: '亚组分析',
    trend: '趋势分析',
    correlation: '相关性分析',
  }
  return map[key] || key
}

function analysisLabel(field: string): string {
  return variableCatalog.find((item) => item.field === field)?.label || field
}

function groupDefinitionsByField(field: string): Record<string, AnyRecord> {
  const map: Record<string, Record<string, AnyRecord>> = {
    outcome: { 存活组: { outcome: 'alive' }, 死亡组: { outcome: 'dead' } },
    icu_mortality: { 存活组: { icu_mortality: 0 }, 死亡组: { icu_mortality: 1 } },
    hospital_mortality: { 存活组: { hospital_mortality: 0 }, 死亡组: { hospital_mortality: 1 } },
    mortality_28d: { '28天存活组': { mortality_28d: 0 }, '28天死亡组': { mortality_28d: 1 } },
  }
  return map[String(field || '')] || {}
}

function formatCohortTime(value: any): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}
function formatExportTime(value: any): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return date.toLocaleString('zh-CN')
}
function openExport(row: AnyRecord): void {
  const url = row?.download_url || row?.url || row?.file_path
  if (!url) {
    message.warning('该导出项缺少下载地址')
    return
  }
  window.open(String(url), '_blank')
}

async function runTable1() {
  loading.table1 = true
  try {
    table1Result.value = await resolveResult(postResearchTable1({
      ...scopePayload(),
      group_by: scope.group_by,
      group_definitions: groupDefinitionsByField(scope.group_by),
      variables: variablePayload(),
    }))
    openConfigKeys.table1 = []
    message.success('基线特征表完成')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '基线特征表生成失败'))
  } finally {
    loading.table1 = false
  }
}
async function runSurvival() {
  loading.survival = true
  try {
    survivalResult.value = await resolveResult(postResearchSurvival({ ...scopePayload(), ...survivalForm }))
    const curveCount = Object.keys((survivalResult.value?.kaplan_meier?.curves || {})).length
    if (!curveCount) {
      const n = Number(survivalResult.value?.n_total || 0)
      const evt = Number(survivalResult.value?.n_events || 0)
      const reason = String(survivalResult.value?.reason || '')
      if (reason === 'no_valid_time_event_data' && scope.patient_scope === 'in_dept') {
        message.warning('当前在科患者通常尚未形成可用于生存分析的结局时间，建议切换为“全部”或“出科”队列后再试')
      } else {
        message.warning(`生存分析暂无可展示曲线（样本 ${n}，事件 ${evt}）`)
      }
      return
    }
    message.success('生存分析完成')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '生存分析失败'))
  } finally {
    loading.survival = false
  }
}
async function runRegression() {
  loading.regression = true
  try {
    const predictors = Array.from(new Set((regressionForm.predictors || []).filter(Boolean)))
    if (!predictors.length) {
      message.warning('请先选择至少1个预测变量')
      return
    }
    const usablePredictors = predictors.filter((field) => Number(getVarSummary(field).non_null_count || 0) >= 3)
    if (!usablePredictors.length) {
      message.warning('当前所选预测变量可用样本不足，无法进行回归分析')
      return
    }
    regressionResult.value = await resolveResult(postResearchRegression({
      ...scopePayload(),
      outcome: regressionForm.outcome,
      outcome_type: regressionForm.outcome_type,
      predictors,
      confounders: regressionForm.confounders || [],
    }))
    const uni = Array.isArray(regressionResult.value?.univariate) ? regressionResult.value.univariate.length : 0
    const multi = Array.isArray(regressionResult.value?.multivariate) ? regressionResult.value.multivariate.length : 0
    if (!uni && !multi) {
      const n = Number(regressionResult.value?.n_total || 0)
      const pos = regressionResult.value?.outcome_positive
      const reason = String(regressionResult.value?.reason || '')
      if (reason === 'outcome_single_class') {
        message.warning(scope.patient_scope === 'in_dept' ? '当前在科患者通常尚未形成死亡/出院结局，回归分析难以建模；建议切换为“全部”或“出科”队列' : `回归分析无法建模：结局变量只有单一类别（样本 ${n}，阳性 ${pos ?? 0}）`)
      } else {
        message.warning(`回归分析暂无可用结果（样本 ${n}）`)
      }
      return
    }
    message.success('回归分析完成')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '回归分析失败'))
  } finally {
    loading.regression = false
  }
}
async function runRoc() {
  loading.roc = true
  try {
    const predictors = Array.from(new Set((rocForm.predictors || []).filter(Boolean)))
    if (!predictors.length) {
      message.warning('请先选择至少1个预测指标')
      return
    }
    const usablePredictors = predictors.filter((field) => Number(getVarSummary(field).non_null_count || 0) >= 10)
    if (!usablePredictors.length) {
      message.warning('当前所选 ROC 指标可用样本不足，无法形成稳定曲线')
      return
    }
    rocResult.value = await resolveResult(postResearchRoc({
      ...scopePayload(),
      outcome: rocForm.outcome,
      predictors,
    }))
    const curveCount = Object.keys((rocResult.value?.curves || {})).length
    if (!curveCount) {
      const n = Number(rocResult.value?.n_total || 0)
      const pos = rocResult.value?.outcome_positive
      const reason = String(rocResult.value?.reason || '')
      if (reason === 'outcome_single_class') {
        message.warning(scope.patient_scope === 'in_dept' ? '当前在科患者通常尚未形成死亡/出院结局，ROC 难以计算；建议切换为“全部”或“出科”队列' : `ROC 暂无法计算：结局变量只有单一类别（样本 ${n}，阳性 ${pos ?? 0}）`)
      } else {
        message.warning(`ROC 暂无可用结果（样本 ${n}）`)
      }
      return
    }
    message.success('受试者工作特征分析完成')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '受试者工作特征分析失败'))
  } finally {
    loading.roc = false
  }
}
async function runTrend() {
  loading.trend = true
  try {
    const indicators = Array.from(new Set((trendForm.indicators || []).filter(Boolean)))
    if (!indicators.length) {
      message.warning('请先选择至少1个指标')
      return
    }
    trendResult.value = await resolveResult(postResearchTrend({
      ...scopePayload(),
      indicators,
      group_by: scope.group_by || null,
      time_reference: trendForm.time_reference,
      time_range_hours: trendForm.time_range_hours,
      interval_hours: trendForm.interval_hours,
    }))
    message.success('趋势分析完成')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '趋势分析失败'))
  } finally {
    loading.trend = false
  }
}
async function runSubgroup() {
  const enabledSubgroups = subgroupForm.subgroups.filter((s) => s.enabled)
  if (!enabledSubgroups.length) {
    message.warning('请至少开启一个亚组')
    return
  }
  const exposureNonNull = Number(getVarSummary(subgroupForm.exposure).non_null_count || 0)
  if (exposureNonNull < 3) {
    message.warning(`亚组分析当前无法建模：暴露因素 ${analysisLabel(subgroupForm.exposure)} 可用样本不足（${exposureNonNull}）`)
    return
  }
  loading.subgroup = true
  try {
    subgroupResult.value = await resolveResult(postResearchSubgroup({
      ...scopePayload(),
      exposure: subgroupForm.exposure,
      outcome: subgroupForm.outcome,
      outcome_type: subgroupForm.outcome_type,
      subgroups: enabledSubgroups.map((s) => ({
        name: s.label,
        filter: JSON.parse(s.filterText),
      })),
    }))
    openConfigKeys.subgroup = []
    message.success('亚组分析完成')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '亚组分析失败'))
  } finally {
    loading.subgroup = false
  }
}

async function runCorrelation() {
  loading.correlation = true
  try {
    const variables = Array.from(new Set((correlationForm.variables || []).filter(Boolean)))
    if (variables.length < 2) {
      message.warning('相关性分析至少需要2个变量')
      return
    }
    const usable = variables.filter((field) => Number(getVarSummary(field).non_null_count || 0) >= 3)
    const removed = variables.filter((field) => !usable.includes(field))
    if (usable.length < 2) {
      const labels = removed.map((field) => variableCatalog.find((item) => item.field === field)?.label || field).join('、')
      message.warning(labels ? `所选变量有效数值不足：${labels}` : '所选变量有效数值不足，无法计算相关性')
      return
    }
    if (removed.length) {
      const labels = removed.map((field) => variableCatalog.find((item) => item.field === field)?.label || field).join('、')
      message.info(`已自动排除数据不足的变量：${labels}`)
    }
    correlationResult.value = await resolveResult(postResearchCorrelation({
      ...scopePayload(),
      variables: usable,
      method: correlationForm.method,
    }))
    message.success('相关性分析完成')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '相关性分析失败'))
  } finally {
    loading.correlation = false
  }
}

function addExport(row: AnyRecord, title: string, folder: string) {
  exports.value.unshift({ ...row, title, arcname: `${folder}/${row.file_name || ''}` })
}

async function exportFigure(chartType: string) {
  const dataMap: Record<string, AnyRecord | null> = {
    survival: survivalResult.value,
    regression: regressionResult.value,
    roc: rocResult.value,
    subgroup: subgroupResult.value,
    trend: trendResult.value,
    correlation: correlationResult.value,
  }
  const result = dataMap[chartType]
  if (!result) return
  try {
    const res = await postResearchExportFigure({
      chart_type: chartType,
      result,
      format: 'png',
      width_mode: 'double',
      filename: `${chartType}_${Date.now()}.png`,
    })
    addExport(res.data || {}, `${analysisTitle(chartType)}图`, 'figures')
    message.success('导出成功')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '导出失败'))
  }
}

async function exportTable() {
  if (!table1Result.value) return
  try {
    const res = await postResearchExportTable({
      title: table1Result.value.title || '基线特征表',
      table_data: table1Result.value,
      format: 'docx',
      filename: `table1_${Date.now()}`,
    })
    addExport(res.data || {}, '基线特征表', 'tables')
    message.success('导出成功')
  } catch (e: any) {
    message.error(apiErrorMessage(e, '导出失败'))
  }
}

function useDefaultSubgroups() {
  subgroupForm.subgroups = [
    { key: 'age_lt_65', label: '年龄 < 65', enabled: true, filterText: '{"age":{"$lt":65}}' },
    { key: 'age_gte_65', label: '年龄 >= 65', enabled: true, filterText: '{"age":{"$gte":65}}' },
    { key: 'sex_m', label: '男性', enabled: true, filterText: '{"sex":"M"}' },
    { key: 'sex_f', label: '女性', enabled: true, filterText: '{"sex":"F"}' },
  ]
}

function normalizeAnalysisKey(value: string): AnalysisKey | null {
  const key = String(value || '').trim() as AnalysisKey
  if (['table1', 'survival', 'regression', 'roc', 'subgroup', 'trend', 'correlation'].includes(key)) return key
  return null
}

function normalizePlanVariable(field: any): string {
  const token = String(field || '').trim()
  const map: Record<string, string> = {
    sofa: 'sofa_admission',
    sofa_max: 'sofa_admission',
    apache_ii: 'apache2',
    apache2_max: 'apache2',
    diagnosis: 'primary_diagnosis',
    icu_death: 'icu_mortality',
    mortality: 'icu_mortality',
  }
  return map[token] || token
}

function normalizePlanGroupBy(field: any): string {
  const token = String(field || '').trim()
  const allowed = new Set(['outcome', 'icu_mortality', 'hospital_mortality', 'mortality_28d', 'discharge_dest', 'los_icu_group', 'sex'])
  if (allowed.has(token)) return token
  return 'outcome'
}

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function plannerStatusText(status: 'pending' | 'running' | 'success' | 'failed' | 'skipped'): string {
  const map: Record<string, string> = {
    pending: '待执行',
    running: '执行中',
    success: '成功',
    failed: '失败',
    skipped: '跳过',
  }
  return map[status] || status
}

function plannerLog(text: string, level: 'info' | 'success' | 'error' = 'info'): void {
  aiPlanner.logs.unshift({
    time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    level,
    text,
  })
  if (aiPlanner.logs.length > 120) aiPlanner.logs = aiPlanner.logs.slice(0, 120)
}

function plannerProgressRecalc(): void {
  const total = aiPlanner.steps.length
  if (!total) {
    aiPlanner.progress = 0
    return
  }
  const done = aiPlanner.steps.filter((s) => ['success', 'failed', 'skipped'].includes(s.status)).length
  aiPlanner.progress = (done / total) * 100
}

function plannerSetStepStatus(key: string, status: 'pending' | 'running' | 'success' | 'failed' | 'skipped', detail = ''): void {
  const idx = aiPlanner.steps.findIndex((s) => s.key === key)
  if (idx < 0) return
  const step = aiPlanner.steps[idx]
  if (!step) return
  step.status = status
  step.detail = detail
  plannerProgressRecalc()
}

function buildPlannerSteps(plan: AnyRecord, autoRun: boolean): Array<{ key: string; title: string; status: 'pending' | 'running' | 'success' | 'failed' | 'skipped' }> {
  const steps: Array<{ key: string; title: string; status: 'pending' | 'running' | 'success' | 'failed' | 'skipped' }> = [
    { key: 'parse', title: '解析自然语言需求', status: 'pending' },
    { key: 'cohort', title: '应用队列配置', status: 'pending' },
    { key: 'group', title: '应用分组设置', status: 'pending' },
    { key: 'variables', title: '应用变量选择', status: 'pending' },
    { key: 'filters', title: '应用筛选条件', status: 'pending' },
  ]
  if (autoRun) {
    const analyses = Array.isArray(plan?.analyses) ? plan.analyses : []
    analyses.forEach((row: AnyRecord, index: number) => {
      const key = normalizeAnalysisKey(String(row?.type || ''))
      if (!key) return
      steps.push({ key: `analysis_${index}_${key}`, title: `执行${analysisTitle(key)}`, status: 'pending' })
    })
  }
  return steps
}

type PlannerRunStep = (key: string, title: string, action: () => Promise<void>) => Promise<void>

async function applyAiPlan(plan: AnyRecord, autoRun = true, runStep?: PlannerRunStep): Promise<{ failed: number }> {
  const exec: PlannerRunStep = runStep || (async (_key, _title, action) => action())
  let failed = 0
  const cohort = (plan?.cohort || {}) as AnyRecord
  const prepModeFromPlan = String(plan?.prep_mode || '').trim()

  await exec('cohort', '应用队列配置', async () => {
    if (cohort?.use_current_dept || prepModeFromPlan === 'dept') {
      prepMode.value = 'dept'
      await loadPatientsByDepartment()
      return
    }
    if (prepModeFromPlan === 'saved' && cohort?.cohort_id) {
      prepMode.value = 'saved'
      scope.cohort_id = String(cohort.cohort_id)
      applyCohortSelection(scope.cohort_id)
      await wait(120)
      return
    }
    if (prepModeFromPlan === 'builder') {
      prepMode.value = 'builder'
      if (!selectedPatientIds.value.length && currentDeptCode.value) {
        await loadPatientsByDepartment()
      }
    }
  })

  await exec('group', '应用分组设置', async () => {
    scope.group_by = normalizePlanGroupBy(plan?.group_by)
  })

  await exec('variables', '应用变量选择', async () => {
    const selected = Array.from(new Set((plan?.selected_variables || []).map((item: any) => normalizePlanVariable(item))))
      .filter((field): field is string => variableCatalog.some((item) => item.field === field))
    if (selected.length) {
      researchSelectionStore.setSelectedVariables(selected)
    }
  })

  await exec('filters', '应用筛选条件', async () => {
    const filterRows = Array.isArray(cohort?.filters) ? cohort.filters : []
    if (filterRows.length) {
      cohortSourceFilters.value = filterRows
      hydrateVariableFilters(filterRows)
      await refreshCohortByVariableFilters()
    }
  })

  const analyses = Array.isArray(plan?.analyses) ? plan.analyses : []
  if (!analyses.length || !autoRun) return { failed }
  const runnerMap: Record<string, () => Promise<void>> = {
    table1: runTable1,
    survival: runSurvival,
    regression: runRegression,
    roc: runRoc,
    subgroup: async () => message.info('亚组分析暂未接入 AI 自动运行，请手动点运行'),
    trend: runTrend,
    correlation: runCorrelation,
  }
  for (const item of analyses) {
    const key = normalizeAnalysisKey(String(item?.type || ''))
    if (!key) continue
    if (key === 'regression' && Array.isArray(item?.params?.predictors)) {
      regressionForm.predictors = item.params.predictors.map(normalizePlanVariable).filter((f: string) => variableCatalog.some((x) => x.field === f))
      if (item?.params?.outcome) regressionForm.outcome = normalizePlanVariable(item.params.outcome)
    }
    if (key === 'roc' && Array.isArray(item?.params?.predictors)) {
      rocForm.predictors = item.params.predictors.map(normalizePlanVariable).filter((f: string) => variableCatalog.some((x) => x.field === f))
      if (item?.params?.outcome) rocForm.outcome = normalizePlanVariable(item.params.outcome)
    }
    if (key === 'trend' && Array.isArray(item?.params?.indicators)) {
      trendForm.indicators = item.params.indicators.map(normalizePlanVariable).filter((f: string) => variableCatalog.some((x) => x.field === f))
    }
    if (key === 'correlation' && Array.isArray(item?.params?.variables)) {
      correlationForm.variables = item.params.variables.map(normalizePlanVariable).filter((f: string) => variableCatalog.some((x) => x.field === f))
    }
    tab.value = key
    const runner = runnerMap[key]
    if (!runner) continue
    const stepKey = `analysis_${analyses.indexOf(item)}_${key}`
    try {
      await exec(stepKey, `执行${analysisTitle(key)}`, async () => {
        await runner()
      })
    } catch {
      failed += 1
    }
  }
  return { failed }
}

async function runAiPlanner(autoRun = true): Promise<void> {
  const text = String(aiPlanner.prompt || '').trim()
  if (!text) {
    message.warning('请先输入分析需求')
    return
  }
  aiPlanner.loading = true
  aiPlanner.progress = 0
  aiPlanner.logs = []
  aiPlanner.steps = [{ key: 'parse', title: '解析自然语言需求', status: 'running' }]
  plannerLog(`收到需求：${text}`)
  try {
    const res = await postResearchAiPlan({
      query: text,
      scope: {
        current_dept_code: currentDeptCode.value || null,
        current_cohort_id: scope.cohort_id || null,
        selected_variables: selectedVariables.value,
      },
    })
    const plan = res.data?.plan?.plan || res.data?.plan || {}
    aiPlanner.lastPlan = plan
    aiPlanner.lastMessage = String(plan?.explanation || res.data?.message || '')
    aiPlanner.steps = buildPlannerSteps(plan, autoRun)
    plannerSetStepStatus('parse', 'success')
    plannerLog('需求解析完成', 'success')

    const runStep: PlannerRunStep = async (key, title, action) => {
      plannerSetStepStatus(key, 'running')
      plannerLog(`${title}：开始`)
      try {
        await action()
        plannerSetStepStatus(key, 'success')
        plannerLog(`${title}：成功`, 'success')
      } catch (error: any) {
        const msg = apiErrorMessage(error, `${title}失败`)
        plannerSetStepStatus(key, 'failed', msg)
        plannerLog(`${title}：失败 - ${msg}`, 'error')
        throw error
      }
    }

    const result = await applyAiPlan(plan, autoRun, runStep)
    if (autoRun) {
      if (result.failed > 0) {
        message.warning(`AI 执行完成，但有 ${result.failed} 个步骤失败，请查看日志`)
      } else {
        message.success('AI 已完成配置并执行分析')
      }
    } else {
      message.success('AI 已完成配置，请确认后执行')
    }
  } catch (e: any) {
    plannerSetStepStatus('parse', 'failed', apiErrorMessage(e, 'AI 解析失败'))
    plannerLog(apiErrorMessage(e, 'AI 解析失败'), 'error')
    message.error(apiErrorMessage(e, 'AI 解析失败'))
  } finally {
    aiPlanner.loading = false
    plannerProgressRecalc()
  }
}
async function onAiGenerate(payload: { analysisType: string; force?: boolean; lang?: LangKey }) {
  const key = normalizeAnalysisKey(payload.analysisType)
  if (!key) return
  const resultMap: Record<AnalysisKey, AnyRecord | null> = {
    table1: table1Result.value, survival: survivalResult.value, regression: regressionResult.value, roc: rocResult.value, subgroup: subgroupResult.value, trend: trendResult.value, correlation: correlationResult.value,
  }
  const result = resultMap[key]
  if (!result) { message.warning('请先生成分析结果'); return }
  const state = ai[key]
  if (!state) return
  const lang = payload.lang || state.lang
  if (!payload.force && state.content[lang].interpretation) return
  state.loading = true
  try {
    const res = await postResearchAiInterpret({ analysis_type: key, results: result, language: lang })
    state.content[lang] = {
      interpretation: String(res.data?.interpretation || ''),
      methods_text: String(res.data?.methods_text || ''),
      results_text: String(res.data?.results_text || ''),
    }
    state.open = true
  } catch (e: any) {
    message.error(apiErrorMessage(e, 'AI生成失败'))
  } finally {
    state.loading = false
  }
}
async function onAiCopy(payload: { analysisType: string; part: PartKey; lang: LangKey }) {
  const key = normalizeAnalysisKey(payload.analysisType)
  if (!key) return
  const state = ai[key]
  if (!state) return
  const text = state.content[payload.lang][payload.part] || ''
  if (!text) return
  try { await navigator.clipboard.writeText(text); message.success('已复制') } catch { message.warning('复制失败') }
}
function onAiLang(payload: { analysisType: string; lang: LangKey }) { const key = normalizeAnalysisKey(payload.analysisType); if (!key) return; const state = ai[key]; if (!state) return; state.lang = payload.lang }
function onAiPart(payload: { analysisType: string; part: PartKey }) { const key = normalizeAnalysisKey(payload.analysisType); if (!key) return; const state = ai[key]; if (!state) return; state.part = payload.part }
function onAiText(payload: { analysisType: string; part: PartKey; lang: LangKey; value: string }) { const key = normalizeAnalysisKey(payload.analysisType); if (!key) return; const state = ai[key]; if (!state) return; state.content[payload.lang][payload.part] = payload.value }

async function saveSession() { sessionLoading.value = true; try { await saveResearchSession({ name: `科研分析_${new Date().toLocaleString('zh-CN')}`, payload: { tab: tab.value, scope: { ...scope }, forms: { survivalForm: { ...survivalForm }, regressionForm: { ...regressionForm }, rocForm: { ...rocForm }, subgroupForm: { ...subgroupForm }, trendForm: { ...trendForm }, correlationForm: { ...correlationForm } }, results: { table1: table1Result.value, survival: survivalResult.value, regression: regressionResult.value, roc: rocResult.value, subgroup: subgroupResult.value, trend: trendResult.value, correlation: correlationResult.value }, exports: exports.value } }); message.success('会话已保存'); await loadSessions() } catch (e: any) { message.error(apiErrorMessage(e, '会话保存失败')) } finally { sessionLoading.value = false } }
async function loadPlatformStatus() {
  platformStatusLoading.value = true
  platformStatusError.value = ''
  try {
    const res = await getResearchPlatformStatus()
    platformStatus.value = res.data?.status || null
  } catch (e: any) {
    platformStatus.value = null
    platformStatusError.value = apiErrorMessage(e, '平台状态加载失败')
  } finally {
    platformStatusLoading.value = false
  }
}

async function runPlatformCheck() {
  platformStatusLoading.value = true
  platformStatusError.value = ''
  try {
    const res = await postResearchPlatformCheck()
    platformStatus.value = res.data?.status || null
    message.success('科研平台自检完成')
    await Promise.allSettled([loadPlatformJobs(), loadPlatformArtifacts()])
  } catch (e: any) {
    platformStatusError.value = apiErrorMessage(e, '平台自检失败')
    message.error(platformStatusError.value)
  } finally {
    platformStatusLoading.value = false
  }
}

async function loadPlatformJobs() {
  researchJobsLoading.value = true
  researchJobsError.value = ''
  try {
    const res = await getResearchPlatformJobs({ limit: 50 })
    researchJobs.value = Array.isArray(res.data?.rows) ? res.data.rows : []
    researchJobsSummary.value = res.data?.summary || {}
  } catch (e: any) {
    researchJobs.value = []
    researchJobsSummary.value = {}
    researchJobsError.value = apiErrorMessage(e, '任务中心加载失败')
  } finally {
    researchJobsLoading.value = false
  }
}

async function loadPlatformArtifacts() {
  researchArtifactsLoading.value = true
  researchArtifactsError.value = ''
  try {
    const res = await getResearchPlatformArtifacts({ limit: 50 })
    researchArtifacts.value = Array.isArray(res.data?.rows) ? res.data.rows : []
  } catch (e: any) {
    researchArtifacts.value = []
    researchArtifactsError.value = apiErrorMessage(e, '产物中心加载失败')
  } finally {
    researchArtifactsLoading.value = false
  }
}

async function loadSessions() {
  sessionListLoading.value = true
  sessionListError.value = ''
  try {
    const res = await listResearchSessions({ limit: 50 })
    sessions.value = Array.isArray(res.data?.sessions) ? res.data.sessions : []
  } catch (e: any) {
    sessions.value = []
    sessionListError.value = apiErrorMessage(e, '会话列表加载失败')
    message.error(sessionListError.value)
  } finally {
    sessionListLoading.value = false
  }
}
async function restoreSession(sessionId: string) { if (!sessionId) return; try { const res = await getResearchSession(sessionId); const p = (res.data?.payload || {}) as AnyRecord; if (p.tab) tab.value = String(p.tab); if (p.scope) Object.assign(scope, p.scope); if (p.forms?.survivalForm) Object.assign(survivalForm, p.forms.survivalForm); if (p.forms?.regressionForm) Object.assign(regressionForm, p.forms.regressionForm); if (p.forms?.rocForm) Object.assign(rocForm, p.forms.rocForm); if (p.forms?.subgroupForm) Object.assign(subgroupForm, p.forms.subgroupForm); if (p.forms?.trendForm) Object.assign(trendForm, p.forms.trendForm); if (p.forms?.correlationForm) Object.assign(correlationForm, p.forms.correlationForm); if (p.results) { table1Result.value = p.results.table1 || null; survivalResult.value = p.results.survival || null; regressionResult.value = p.results.regression || null; rocResult.value = p.results.roc || null; subgroupResult.value = p.results.subgroup || null; trendResult.value = p.results.trend || null; correlationResult.value = p.results.correlation || null } exports.value = Array.isArray(p.exports) ? p.exports : []; message.success('会话已恢复') } catch (e: any) { message.error(apiErrorMessage(e, '会话恢复失败')) } }
onMounted(async () => {
  await loadDeptNameMap()
  await loadCohorts()
  await loadSessions()
  await Promise.allSettled([loadPlatformStatus(), loadPlatformJobs(), loadPlatformArtifacts()])
  useDefaultSubgroups()
})

const sessionEmptyText = computed(() => {
  if (sessionListLoading.value) return '正在加载会话...'
  if (sessionListError.value) return '会话加载失败，请重试'
  return '暂无会话，请先点击顶部“保存会话”'
})

watch(openSessionDrawer, (val) => {
  if (val) void loadSessions()
})

function onDocumentPointerDown(event: Event): void {
  const target = event.target as HTMLElement | null
  if (!target) return
  if (target.closest('.var-item')) return
  expandedVariableField.value = ''
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocumentPointerDown)
})
const regressionUnivariateRows = computed(() => ((regressionResult.value?.univariate || []) as AnyRecord[]).map((row, idx) => ({ ...row, row_key: `uni_${idx}_${row.variable || ''}` })))
const regressionMultivariateRows = computed(() => ((regressionResult.value?.multivariate || []) as AnyRecord[]).map((row, idx) => ({ ...row, row_key: `multi_${idx}_${row.variable || ''}` })))
const regressionSummaryColumns = [
  { title: '项目', dataIndex: 'item', key: 'item' },
  { title: '值', dataIndex: 'value', key: 'value' },
]
const regressionSummaryRows = computed(() => {
  const rows: AnyRecord[] = []
  const total = Number(regressionResult.value?.n_total || 0)
  const outcomeNonNull = Number(regressionResult.value?.outcome_non_null || 0)
  rows.push({ row_key: 'total', item: '总样本数', value: total || '—' })
  rows.push({ row_key: 'outcome_non_null', item: '结局可用样本', value: outcomeNonNull || '—' })
  if (regressionResult.value?.outcome_positive != null) {
    rows.push({ row_key: 'positive', item: '阳性结局数', value: Number(regressionResult.value.outcome_positive || 0) })
  }
  const multi = regressionResult.value?.multivariate_count || {}
  if (Array.isArray(multi.variables) && multi.variables.length) {
    rows.push({ row_key: 'multi_n', item: '多因素建模样本', value: Number(multi.n_model || 0) })
    rows.push({ row_key: 'multi_excluded', item: '多因素排除样本', value: Number(multi.n_excluded || 0) })
    rows.push({ row_key: 'multi_vars', item: '多因素变量', value: String((multi.variables || []).join('、') || '—') })
  }
  return rows
})
const regressionCountColumns = [
  { title: '变量', dataIndex: 'label', key: 'label' },
  { title: '建模样本', dataIndex: 'n_model', key: 'n_model' },
  { title: '排除样本', dataIndex: 'n_excluded', key: 'n_excluded' },
]
const regressionCountRows = computed(() => {
  const rows = Array.isArray(regressionResult.value?.univariate_counts) ? regressionResult.value.univariate_counts : []
  return rows.map((row: AnyRecord) => {
    const field = String(row.variable || '')
    return {
      variable: field,
      label: variableCatalog.find((item) => item.field === field)?.label || field,
      n_model: Number(row.n_model || 0),
      n_excluded: Number(row.n_excluded || 0),
    }
  }).sort((a, b) => b.n_excluded - a.n_excluded)
})
const regressionQualityTips = computed(() => {
  const tips: string[] = []
  const total = Number(regressionResult.value?.n_total || 0)
  const outcomeNonNull = Number(regressionResult.value?.outcome_non_null || 0)
  const multi = regressionResult.value?.multivariate_count || {}
  if (total > 0 && total < 50) tips.push(`总样本量偏少（n=${total}）`)
  if (outcomeNonNull > 0 && outcomeNonNull < 30) tips.push(`结局可用样本较少（n=${outcomeNonNull}）`)
  if (Number(multi.n_excluded || 0) > 0 && total > 0 && Number(multi.n_excluded || 0) / total > 0.3) {
    tips.push(`多因素建模样本损失较高（排除 ${Number(multi.n_excluded || 0)} 例）`)
  }
  return tips
})
const regressionCoverageText = computed(() => {
  const rows = Array.from(new Set([...(regressionForm.predictors || []), ...(regressionForm.confounders || [])]))
    .map((field) => {
      const summary = getVarSummary(field)
      return {
        field,
        label: analysisLabel(field),
        count: Number(summary.non_null_count || 0),
        total: Number(summary.total_count || selectedPatientIds.value.length || 0),
      }
    })
    .filter((item) => item.count < 3)
  if (!rows.length) return ''
  return `以下回归变量当前可用样本不足，运行时会被自动排除：${rows.map((item) => `${item.label}(${item.count}/${item.total})`).join('、')}`
})

const rocCoverageText = computed(() => {
  const rows = Array.from(new Set(rocForm.predictors || []))
    .map((field) => {
      const summary = getVarSummary(field)
      return {
        field,
        label: analysisLabel(field),
        count: Number(summary.non_null_count || 0),
        total: Number(summary.total_count || selectedPatientIds.value.length || 0),
      }
    })
    .filter((item) => item.count < 10)
  if (!rows.length) return ''
  return `以下 ROC 指标可用样本偏少，可能无法形成稳定曲线：${rows.map((item) => `${item.label}(${item.count}/${item.total})`).join('、')}`
})

const subgroupCoverageText = computed(() => {
  const exposureSummary = getVarSummary(subgroupForm.exposure)
  const outcomeSummary = getVarSummary(subgroupForm.outcome)
  const exposureCount = Number(exposureSummary.non_null_count || 0)
  const outcomeCount = Number(outcomeSummary.non_null_count || 0)
  const total = Number(exposureSummary.total_count || outcomeSummary.total_count || selectedPatientIds.value.length || 0)
  const msgs: string[] = []
  if (exposureCount < 3) msgs.push(`暴露因素 ${analysisLabel(subgroupForm.exposure)} 几乎无可用样本（${exposureCount}/${total}）`)
  if (outcomeCount < 3) msgs.push(`结局变量 ${analysisLabel(subgroupForm.outcome)} 可用样本不足（${outcomeCount}/${total}）`)
  return msgs.join('；')
})
const regressionColumns = computed(() => ([
  { title: '变量', dataIndex: 'variable', key: 'variable' },
  { title: '估计值', dataIndex: 'estimate_display', key: 'estimate_display' },
  { title: '95%CI', dataIndex: 'ci_display', key: 'ci_display' },
  { title: 'P值', dataIndex: 'p_display', key: 'p_display' },
]))
const rocRows = computed(() => Object.entries(rocResult.value?.curves || {}).map(([name, row]: [string, any], idx) => ({
  row_key: `roc_${idx}_${name}`,
  predictor: variableCatalog.find((item) => item.field === name)?.label || name,
  auc: row?.auc != null ? Number(row.auc).toFixed(3) : '--',
  ci: row?.ci_lower != null && row?.ci_upper != null ? `${Number(row.ci_lower).toFixed(3)} - ${Number(row.ci_upper).toFixed(3)}` : '--',
  cutoff: row?.optimal_cutoff != null ? Number(row.optimal_cutoff).toFixed(2) : '--',
  sensitivity: row?.sensitivity_at_cutoff != null ? `${(Number(row.sensitivity_at_cutoff) * 100).toFixed(1)}%` : '--',
  specificity: row?.specificity_at_cutoff != null ? `${(Number(row.specificity_at_cutoff) * 100).toFixed(1)}%` : '--',
})))
const rocColumns = computed(() => ([
  { title: '预测指标', dataIndex: 'predictor', key: 'predictor' },
  { title: '曲线下面积', dataIndex: 'auc', key: 'auc' },
  { title: '95%置信区间', dataIndex: 'ci', key: 'ci' },
  { title: '最佳阈值', dataIndex: 'cutoff', key: 'cutoff' },
  { title: '灵敏度', dataIndex: 'sensitivity', key: 'sensitivity' },
  { title: '特异度', dataIndex: 'specificity', key: 'specificity' },
]))
const rocOption = computed(() => {
  const curves = (rocResult.value?.curves || {}) as Record<string, AnyRecord>
  const names = Object.keys(curves)
  if (!names.length) return null
  return {
    backgroundColor: '#fff',
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    xAxis: { type: 'value', name: '1 - 特异度', min: 0, max: 1 },
    yAxis: { type: 'value', name: '灵敏度', min: 0, max: 1 },
    series: [
      ...names.map((name) => ({
        name: `${variableCatalog.find((item) => item.field === name)?.label || name}（曲线下面积 ${Number(curves[name]?.auc || 0).toFixed(3)}）`,
        type: 'line',
        showSymbol: false,
        data: (curves[name]?.fpr || []).map((x: number, idx: number) => [x, curves[name]?.tpr?.[idx]]),
      })),
      { name: '参考线', type: 'line', showSymbol: false, lineStyle: { type: 'dashed', opacity: 0.7 }, data: [[0, 0], [1, 1]] },
    ],
  }
})
const trendActiveIndicator = ref('')
const trendIndicatorList = computed(() => Object.keys(trendResult.value?.indicators || {}))
watch(trendIndicatorList, (list) => {
  if (!list.length) {
    trendActiveIndicator.value = ''
    return
  }
  if (!trendActiveIndicator.value || !list.includes(trendActiveIndicator.value)) {
    trendActiveIndicator.value = list[0] || ''
  }
}, { immediate: true })
const trendOption = computed(() => {
  const key = trendActiveIndicator.value
  if (!key) return null
  const payload = trendResult.value?.indicators?.[key] || {}
  const timeline = payload.timeline_hours || []
  const groups = payload.groups || {}
  const names = Object.keys(groups)
  if (!timeline.length || !names.length) return null
  return {
    backgroundColor: '#fff',
    tooltip: { trigger: 'axis' },
    legend: { top: 0 },
    xAxis: { type: 'value', name: '时间 (小时)' },
    yAxis: { type: 'value', name: variableCatalog.find((item) => item.field === key)?.label || key },
    series: names.map((name) => ({
      name,
      type: 'line',
      showSymbol: false,
      connectNulls: false,
      data: timeline.map((hour: number, idx: number) => [hour, groups[name]?.mean?.[idx]]),
    })),
  }
})
const trendSampleColumns = [
  { title: '分组', dataIndex: 'group', key: 'group' },
  { title: '总观测点', dataIndex: 'total_points', key: 'total_points' },
  { title: '峰值样本量', dataIndex: 'peak_n', key: 'peak_n' },
  { title: '非空时间点', dataIndex: 'non_empty_bins', key: 'non_empty_bins' },
]
const trendSampleRows = computed(() => {
  const key = trendActiveIndicator.value
  if (!key) return []
  const payload = trendResult.value?.indicators?.[key] || {}
  const groups = payload.groups || {}
  return Object.keys(groups).map((group) => {
    const counts = Array.isArray(groups[group]?.n) ? groups[group].n.map((x: any) => Number(x || 0)) : []
    return {
      group,
      total_points: counts.reduce((sum: number, item: number) => sum + item, 0),
      peak_n: counts.length ? Math.max(...counts) : 0,
      non_empty_bins: counts.filter((item: number) => item > 0).length,
    }
  })
})
const trendQualityTips = computed(() => {
  const tips: string[] = []
  const sparse = trendSampleRows.value.filter((row) => Number(row.non_empty_bins || 0) < 3)
  if (sparse.length) tips.push(`部分分组有效时间点较少：${sparse.map((row) => row.group).join('、')}`)
  const lowPeak = trendSampleRows.value.filter((row) => Number(row.peak_n || 0) < 5)
  if (lowPeak.length) tips.push(`部分分组单时间点样本量偏低：${lowPeak.map((row) => row.group).join('、')}`)
  return tips
})
const correlationOption = computed(() => {
  const matrix = correlationResult.value?.matrix || {}
  const labels = (matrix.labels || []) as string[]
  const displayLabels = labels.map((field) => variableCatalog.find((item) => item.field === field)?.label || field)
  const values = matrix.correlations || []
  const pValues = matrix.p_values || []
  const nPairs = matrix.n_pairs || []
  if (!labels.length || !values.length) return null
  const heat = labels.flatMap((_: string, rowIdx: number) =>
    labels.map((__: string, colIdx: number) => ({
      value: [colIdx, rowIdx, Number(values?.[rowIdx]?.[colIdx] ?? 0)],
      raw: values?.[rowIdx]?.[colIdx],
      n: Number(nPairs?.[rowIdx]?.[colIdx] ?? 0),
      p: pValues?.[rowIdx]?.[colIdx],
      xLabel: displayLabels[colIdx],
      yLabel: displayLabels[rowIdx],
      insufficient: rowIdx === colIdx ? Number(nPairs?.[rowIdx]?.[colIdx] ?? 0) < 1 : Number(nPairs?.[rowIdx]?.[colIdx] ?? 0) < 3,
    })),
  )

  const fmtCorr = (val: number) => {
    const num = Number(val || 0)
    if (Math.abs(num) < 0.0005) return '≈0'
    return num.toFixed(2)
  }
  const fmtP = (val: any) => {
    const num = Number(val)
    if (!Number.isFinite(num)) return '—'
    if (num < 0.001) return '<0.001'
    return num.toFixed(3)
  }
  return {
    backgroundColor: '#fff',
    tooltip: {
      formatter: (params: any) => {
        const row = params?.data || {}
        if (row.insufficient) {
          return `${row.yLabel} 与 ${row.xLabel}<br/>有效配对样本不足<br/>n = ${Number(row.n || 0)}`
        }
        return `${row.yLabel} 与 ${row.xLabel}<br/>r = ${fmtCorr(Number(row.raw))}<br/>p = ${fmtP(row.p)}<br/>n = ${Number(row.n || 0)}`
      },
    },
    xAxis: { type: 'category', data: displayLabels, axisLabel: { rotate: 30 } },
    yAxis: { type: 'category', data: displayLabels },
    visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0 },
    series: [{
      type: 'heatmap',
      data: heat,
      label: {
        show: true,
        formatter: (p: any) => (p?.data?.insufficient ? '—' : fmtCorr(Number(p?.data?.raw))),
        color: '#111',
      },
    }],
  }
})

const survivalSummaryColumns = [
  { title: '分组', dataIndex: 'group', key: 'group' },
  { title: '样本量', dataIndex: 'n', key: 'n' },
  { title: '事件数', dataIndex: 'events', key: 'events' },
  { title: '删失数', dataIndex: 'censored', key: 'censored' },
  { title: '中位生存时间', dataIndex: 'median_survival_display', key: 'median_survival_display' },
]
const survivalSummaryRows = computed(() => {
  const curves = (survivalResult.value?.kaplan_meier?.curves || {}) as Record<string, AnyRecord>
  const medians = (survivalResult.value?.kaplan_meier?.median_survival || {}) as Record<string, any>
  return Object.keys(curves).map((group) => {
    const row = curves[group] || {}
    const n = Number(row.n || 0)
    const events = Number(row.events || 0)
    const median = Number(medians[group])
    return {
      group,
      n,
      events,
      censored: Math.max(0, n - events),
      median_survival_display: Number.isFinite(median) ? median.toFixed(1) : '—',
    }
  })
})
const survivalQualityTips = computed(() => {
  const tips: string[] = []
  const total = Number(survivalResult.value?.n_total || 0)
  const events = Number(survivalResult.value?.n_events || 0)
  const reason = String(survivalResult.value?.reason || '')
  if (reason === 'no_valid_time_event_data' && scope.patient_scope === 'in_dept') {
    tips.push('当前在科患者通常缺少可用于生存分析的结局时间，更适合做趋势或相关性分析')
  }
  if (total > 0 && total < 30) tips.push(`生存分析总样本偏少（n=${total}）`)
  if (events > 0 && events < 10) tips.push(`事件数偏少（events=${events}），曲线稳定性有限`)
  const smallGroups = survivalSummaryRows.value.filter((row) => Number(row.n || 0) < 10)
  if (smallGroups.length) tips.push(`部分分组样本较少：${smallGroups.map((row) => row.group).join('、')}`)
  return tips
})

const correlationDataIssueText = computed(() => {
  const matrix = correlationResult.value?.matrix || {}
  const labels = Array.isArray(matrix.labels) ? matrix.labels : []
  const nPairs = Array.isArray(matrix.n_pairs) ? matrix.n_pairs : []
  if (!labels.length || !nPairs.length) return ''
  const emptyFields = labels.filter((_: string, idx: number) => Number(nPairs?.[idx]?.[idx] ?? 0) < 1)
  if (!emptyFields.length) return ''
  const display = emptyFields
    .map((field: string) => variableCatalog.find((item) => item.field === field)?.label || field)
    .join('、')
  return `以下变量当前缺少可用数值，热图中会显示为“—”：${display}`
})

const correlationCoverageText = computed(() => {
  const variables = Array.from(new Set((correlationForm.variables || []).filter(Boolean)))
  if (!variables.length) return ''
  const lowCoverage = variables
    .map((field) => {
      const summary = getVarSummary(field)
      return {
        field,
        label: variableCatalog.find((item) => item.field === field)?.label || field,
        count: Number(summary.non_null_count || 0),
        total: Number(summary.total_count || selectedPatientIds.value.length || 0),
      }
    })
    .filter((item) => item.count < 3)
  if (!lowCoverage.length) return ''
  return `以下变量当前可用样本不足，运行时会被自动排除：${lowCoverage.map((item) => `${item.label}(${item.count}/${item.total})`).join('、')}`
})

const correlationExcludedText = computed(() => {
  const rows = Array.isArray(correlationResult.value?.excluded_variables) ? correlationResult.value.excluded_variables : []
  if (!rows.length) return ''
  const text = rows.map((item: AnyRecord) => {
    const field = String(item.field || '')
    const label = variableCatalog.find((row) => row.field === field)?.label || field
    return `${label}(${Number(item.non_null_count || 0)}/${Number(item.total_count || 0)})`
  }).join('、')
  return `本次已自动排除样本不足的变量：${text}`
})
const correlationQualityTips = computed(() => {
  const tips: string[] = []
  const excluded = Array.isArray(correlationResult.value?.excluded_variables) ? correlationResult.value.excluded_variables : []
  if (excluded.length) tips.push(`已自动排除 ${excluded.length} 个低覆盖变量`)
  const rows = correlationPairRows.value
  if (rows.length) {
    let insufficient = 0
    rows.forEach((row: AnyRecord) => {
      Object.keys(row).forEach((key) => {
        if (key.startsWith('col_') && row[key] === '—') insufficient += 1
      })
    })
    if (insufficient > 0) tips.push('部分变量对有效配对样本不足，相关系数解释需谨慎')
  }
  return tips
})

const correlationPairColumns = computed(() => {
  const labels = (correlationResult.value?.matrix?.labels || []) as string[]
  const displayLabels = labels.map((field) => variableCatalog.find((item) => item.field === field)?.label || field)
  return [
    { title: '变量', dataIndex: 'label', key: 'label', fixed: 'left' as const, width: 160 },
    ...displayLabels.map((label, idx) => ({ title: label, dataIndex: `col_${idx}`, key: `col_${idx}`, width: 110 })),
  ]
})

const correlationPairRows = computed(() => {
  const matrix = correlationResult.value?.matrix || {}
  const labels = Array.isArray(matrix.labels) ? matrix.labels : []
  const nPairs = Array.isArray(matrix.n_pairs) ? matrix.n_pairs : []
  if (!labels.length || !nPairs.length) return []
  return labels.map((field: string, rowIdx: number) => {
    const row: AnyRecord = {
      row_key: `${field}_${rowIdx}`,
      label: variableCatalog.find((item) => item.field === field)?.label || field,
    }
    labels.forEach((_: string, colIdx: number) => {
      const count = Number(nPairs?.[rowIdx]?.[colIdx] ?? 0)
      row[`col_${colIdx}`] = count >= (rowIdx === colIdx ? 1 : 3) ? count : '—'
    })
    return row
  })
})

const subgroupColumns = [
  { title: '亚组', dataIndex: 'subgroup', key: 'subgroup' },
  { title: '样本量', dataIndex: 'n', key: 'n' },
  { title: '效应值', dataIndex: 'estimate_display', key: 'estimate' },
  { title: '95% CI', dataIndex: 'ci_display', key: 'ci' },
  { title: 'P值 (交互)', dataIndex: 'p_interaction_display', key: 'p_int' },
]

const subgroupRows = computed(() => {
  const data = subgroupResult.value?.subgroups || []
  return data.map((item: any) => ({
    ...item,
    subgroup: item.name,
    estimate_display: item.estimate != null ? Number(item.estimate).toFixed(2) : '--',
    ci_display: item.ci_lower != null ? `${Number(item.ci_lower).toFixed(2)} - ${Number(item.ci_upper).toFixed(2)}` : '--',
    p_interaction_display: item.p_interaction != null ? (item.p_interaction < 0.001 ? '<0.001' : Number(item.p_interaction).toFixed(3)) : '--',
  }))
})
const subgroupQualityTips = computed(() => {
  const tips: string[] = []
  const rows = subgroupRows.value
  const emptyEstimate = rows.filter((row: AnyRecord) => row.estimate_display === '--')
  if (emptyEstimate.length) tips.push(`部分亚组无法估计效应值：${emptyEstimate.map((row: AnyRecord) => row.subgroup).join('、')}`)
  const lowEvent = rows.filter((row: AnyRecord) => Number(row.n_event || 0) < 5)
  if (lowEvent.length) tips.push(`部分亚组事件数偏少：${lowEvent.map((row: AnyRecord) => row.subgroup).join('、')}`)
  return tips
})

const subgroupForestOption = computed(() => {
  const data = subgroupResult.value?.subgroups || []
  if (!data.length) return undefined
  const yAxisData = data.map((d: any) => d.name).reverse()
  const estimates = data.map((d: any) => d.estimate).reverse()
  const ciLowers = data.map((d: any) => d.ci_lower).reverse()
  const ciUppers = data.map((d: any) => d.ci_upper).reverse()

  return {
    backgroundColor: '#fff',
    tooltip: { trigger: 'axis' },
    grid: { left: '20%', right: '10%', bottom: '15%' },
    xAxis: {
      type: 'value',
      name: subgroupForm.outcome_type === 'binary' ? 'OR (95% CI)' : 'Beta (95% CI)',
      scale: true,
    },
    yAxis: { type: 'category', data: yAxisData },
    series: [
      {
        type: 'scatter',
        data: estimates.map((val: any, i: number) => [val, i]),
        symbol: 'rect',
        symbolSize: 8,
        itemStyle: { color: '#1890ff' },
      },
      {
        type: 'custom',
        renderItem: (_params: any, api: any) => {
          const y = api.value(1)
          const high = api.coord([api.value(2), y])
          const low = api.coord([api.value(0), y])
          return {
            type: 'group',
            children: [
              {
                type: 'line',
                shape: { x1: low[0], y1: low[1], x2: high[0], y2: high[1] },
                style: api.style({ stroke: '#1890ff', lineWidth: 2 }),
              },
            ],
          }
        },
        data: ciLowers.map((low: any, i: number) => [low, i, ciUppers[i]]),
        clip: true,
      },
      {
        name: '参考线',
        type: 'line',
        markLine: {
          symbol: 'none',
          data: [{ xAxis: subgroupForm.outcome_type === 'binary' ? 1 : 0 }],
          lineStyle: { type: 'dashed', color: '#999' },
        },
      },
    ],
  }
})

onUnmounted(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
})
</script>

<style scoped>
.workbench { padding: 18px 24px 32px; display: flex; flex-direction: column; gap: 16px; min-height: calc(100vh - 40px); font-family: var(--app-display-font); }
.hero-card { background: rgba(255,255,255,0.04); border: 1px solid rgba(0,210,210,0.16); border-radius: 10px; padding: 18px 24px; display: flex; justify-content: space-between; align-items: center; }
.hero-card h2 { margin: 0; color: #e8fbff; font-size: 22px; }
.hero-card p { margin: 6px 0 0; color: rgba(255,255,255,0.6); font-size: 13px; }
.hero-actions { display: flex; align-items: center; gap: 16px; }
.cohort-pill { padding: 6px 12px; border-radius: 999px; background: rgba(0,210,210,0.15); color: #cffafd; font-size: 13px; transition: all .2s; }
.cohort-pill.link { cursor: pointer; }
.cohort-pill.link:hover { background: rgba(0,210,210,0.3); }
.cohort-pill.empty { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.6); }
.warn-banner { background: rgba(255,166,0,0.15); border: 1px solid rgba(255,166,0,0.35); border-radius: 10px; padding: 8px 16px; color: #ffdba0; font-size: 13px; cursor: pointer; }
.workbench-body { display: flex; gap: 18px; flex: 1; }
.nav-panel { width: 180px; background: rgba(7, 15, 26, 0.78); border: 1px solid rgba(0,210,210,0.15); border-radius: 12px; padding: 12px 0; position: sticky; top: 18px; height: fit-content; }
.nav-item { padding: 10px 18px; color: rgba(255,255,255,0.7); cursor: pointer; display: flex; align-items: center; justify-content: space-between; }
.nav-item.divider { border-top: 1px solid rgba(255,255,255,0.08); margin: 6px 0; height: 0; padding: 0; cursor: default; }
.nav-item.active { color: #00f2ff; background: rgba(0,210,210,0.16); box-shadow: inset 3px 0 0 #00f2ff; }
.nav-item.disabled { opacity: 0.45; cursor: not-allowed; }
.nav-label { font-size: 14px; }
.nav-status { font-size: 12px; color: #66ffd8; margin-left: 8px; }
.status-dot { width: 8px; height: 8px; border-radius: 999px; background: rgba(255,255,255,0.25); display: inline-block; transition: background .2s, box-shadow .2s; box-shadow: 0 0 0 rgba(0,0,0,0); }
.status-dot.ready { background: #36fcca; box-shadow: 0 0 6px rgba(54,252,202,0.8); }
.status-check { color: #66ffd8; font-weight: 600; }
.content-panel { flex: 1; background: rgba(7,17,30,0.78); border: 1px solid rgba(0,210,210,0.12); border-radius: 16px; padding: 24px 28px 40px; overflow: hidden; }
.tab-content { display: flex; flex-direction: column; gap: 18px; }
.analysis-section { display: flex; flex-direction: column; gap: 18px; }
.card-grid { display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.card { background: rgba(255,255,255,0.03); border: 1px solid rgba(0,210,210,0.15); border-radius: 10px; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.card.full-width { grid-column: 1 / -1; }
.card-head { display: flex; justify-content: space-between; font-weight: 600; color: #e2f7ff; }
.prep-options { display: flex; flex-direction: column; gap: 8px; }
.cohort-option { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.cohort-option :deep(.ant-btn-link) { opacity: 0; transition: opacity .2s ease; }
.cohort-option:hover :deep(.ant-btn-link) { opacity: 1; }
.cohort-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: rgba(255,255,255,0.85); }
.prep-options :deep(.ant-radio-wrapper) { display: flex; align-items: center; margin: 0; color: rgba(255,255,255,0.85); }
.prep-hint { font-size: 12px; color: rgba(255,255,255,0.55); margin-top: 6px; }
.prep-summary { font-size: 13px; color: rgba(255,255,255,0.75); display: flex; flex-direction: column; gap: 4px; }
.group-summary { display: flex; gap: 14px; align-items: stretch; }
.group-card { flex: 1; background: rgba(255,255,255,0.05); border-radius: 10px; padding: 12px 16px; display: flex; flex-direction: column; gap: 6px; text-align: left; }
.group-card.survive { background: linear-gradient(135deg, rgba(0,210,170,0.35), rgba(0,210,210,0.08)); }
.group-card.death { background: linear-gradient(135deg, rgba(255,99,71,0.4), rgba(255,140,0,0.08)); }
.group-card strong { font-size: 18px; color: #fff; }
.group-card span { font-size: 13px; color: rgba(255,255,255,0.85); }
.group-vs { align-self: center; padding: 0 4px; font-size: 15px; font-weight: 600; color: rgba(255,255,255,0.65); }
.variable-tags { display: flex; flex-direction: column; gap: 12px; }
.variable-row { display: flex; gap: 12px; align-items: flex-start; }
.var-category { width: 70px; text-align: right; color: rgba(255,255,255,0.45); font-size: 12px; line-height: 24px; cursor: pointer; transition: color .2s; }
.var-category:hover { color: rgba(255,255,255,0.75); }
.var-tags { display: flex; flex-wrap: wrap; gap: 8px; flex: 1; }
.var-head-actions { display: flex; align-items: center; gap: 10px; font-size: 12px; color: rgba(255,255,255,0.65); }
.var-head-actions :deep(.ant-btn-link) { padding: 0; height: auto; }
.var-item { position: relative; display: inline-flex; flex-direction: column; align-items: flex-start; }
.var-tag { padding: 4px 8px; border-radius: 5px; border: 1px solid rgba(0,210,210,0.2); background: rgba(0,210,210,0.05); color: rgba(255,255,255,0.6); font-size: 12px; display: inline-flex; align-items: center; gap: 6px; transition: all .2s; }
.var-tag:not(.selected):hover { background: rgba(0,210,210,0.1); border-color: rgba(0,210,210,0.35); }
.var-tag.selected { background: rgba(0,210,210,0.2); border-color: rgba(0,210,210,0.65); color: #fff; box-shadow: 0 0 8px rgba(0,210,210,0.15); }
.var-tag.filtered { box-shadow: inset 3px 0 0 #00d2d2; }
.check-toggle, .expand-toggle { border: none; background: transparent; color: inherit; cursor: pointer; padding: 0; line-height: 1; }
.var-name { cursor: pointer; }
.filter-summary { color: #57f5ff; font-size: 11px; }
.var-type { font-size: 11px; color: rgba(255,255,255,0.65); }
.var-tag.continuous .var-type::before { content: '● '; color: #4FC3F7; font-size: 12px; }
.var-tag.categorical .var-type::before { content: '■ '; color: #FFB74D; font-size: 12px; }
.var-tag.binary .var-type::before { content: '◆ '; color: #81C784; font-size: 12px; }
.category-flash { margin-left: 6px; color: #62ffd6; font-size: 11px; }
.filter-panel {
  margin-top: 8px;
  margin-bottom: 8px;
  margin-left: 8px;
  background: rgba(0, 20, 30, 0.6);
  border: 1px solid rgba(0, 210, 210, 0.15);
  border-radius: 6px;
  padding: 12px 16px;
  max-width: 400px;
  animation: slideDown 0.2s ease;
}
@keyframes slideDown {
  from { opacity: 0; max-height: 0; }
  to { opacity: 1; max-height: 260px; }
}
.radio-option { display: block; font-size: 13px; color: rgba(255,255,255,0.8); line-height: 28px; }
.range-row { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.range-row input[type="number"] {
  width: 88px;
  height: 32px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(0, 210, 210, 0.2);
  border-radius: 4px;
  color: #fff;
  padding: 0 8px;
  font-size: 13px;
}
.overview-line { margin-top: 6px; color: rgba(255,255,255,0.45); font-size: 11px; }
.quick-buttons { margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap; }
.quick-btn {
  padding: 2px 10px;
  font-size: 11px;
  border: 1px solid rgba(0, 210, 210, 0.3);
  border-radius: 3px;
  background: transparent;
  color: rgba(0, 210, 210, 0.9);
  cursor: pointer;
}
.quick-btn:hover { background: rgba(0, 210, 210, 0.1); }
.cat-grid { display: flex; flex-wrap: wrap; gap: 8px 12px; margin-top: 6px; }
.cat-item { font-size: 12px; color: rgba(255,255,255,0.8); }
.diag-search-block { margin-top: 6px; display: grid; gap: 6px; min-width: 300px; }
.diag-search-tip { font-size: 11px; color: rgba(255,255,255,0.5); }
.actions { margin-top: 10px; display: flex; gap: 8px; }
.btn-apply {
  padding: 4px 16px;
  font-size: 12px;
  background: rgba(0, 210, 210, 0.2);
  border: 1px solid rgba(0, 210, 210, 0.4);
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
}
.btn-clear {
  padding: 4px 16px;
  font-size: 12px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.6);
  cursor: pointer;
}
.var-tooltip { max-width: 260px; color: #fff; font-size: 12px; }
.tooltip-title { font-weight: 600; margin-bottom: 4px; }
.tooltip-divider { border-top: 1px solid rgba(255,255,255,0.25); margin: 6px 0; }
.tooltip-distribution { margin-left: 12px; }
.planner-block {
  margin-top: 6px;
  padding: 10px 12px;
  border: 1px solid rgba(0, 210, 210, 0.2);
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.2);
}
.planner-progress-head {
  display: flex;
  justify-content: space-between;
  color: rgba(255,255,255,0.75);
  font-size: 12px;
  margin-bottom: 6px;
}
.planner-step-list { margin-top: 8px; display: grid; gap: 6px; }
.planner-step-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: rgba(255,255,255,0.72);
}
.planner-step-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: rgba(255,255,255,0.35);
  flex: 0 0 8px;
}
.planner-step-row.is-running .planner-step-dot { background: #38bdf8; box-shadow: 0 0 6px rgba(56,189,248,0.8); }
.planner-step-row.is-success .planner-step-dot { background: #34d399; }
.planner-step-row.is-failed .planner-step-dot { background: #f87171; }
.planner-step-row.is-skipped .planner-step-dot { background: rgba(255,255,255,0.4); }
.planner-step-title { flex: 1; }
.planner-step-state { color: rgba(255,255,255,0.55); }
.planner-log-box {
  margin-top: 8px;
  max-height: 170px;
  overflow: auto;
  background: rgba(0,0,0,0.24);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px;
  padding: 8px 10px;
}
.planner-log-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
  color: rgba(255,255,255,0.75);
}
.planner-log-row + .planner-log-row { margin-top: 4px; }
.planner-log-time { color: rgba(255,255,255,0.45); min-width: 64px; }
.planner-log-row.is-success .planner-log-text { color: #9af5d2; }
.planner-log-row.is-error .planner-log-text { color: #ffb4b4; }
.next-step-card { background: rgba(255,255,255,0.02); border: 1px dashed rgba(0,210,210,0.3); border-radius: 12px; padding: 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.status-line { display: flex; gap: 18px; color: rgba(0,255,213,0.8); font-size: 13px; }
.recommend { color: rgba(255,255,255,0.7); font-size: 13px; }
.config-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(0,210,210,0.15); border-radius: 10px; }
.collapse-head { display: flex; justify-content: space-between; width: 100%; color: #cfefff; font-weight: 600; }
.collapse-summary { color: rgba(255,255,255,0.6); font-size: 12px; }
.form-grid { display: grid; gap: 16px; }
.form-grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.form-grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.form-grid .full { grid-column: 1 / -1; }
.label { color: rgba(255,255,255,0.7); font-size: 12px; margin-bottom: 6px; }
.action-bar { display: flex; gap: 12px; }
.result-card { background: rgba(255,255,255,0.03); border: 1px solid rgba(0,210,210,0.1); border-radius: 10px; padding: 18px; }
.result-meta { color: rgba(13,34,58,0.65); font-size: 12px; }
.quality-strip { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.quality-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(255, 196, 61, 0.14);
  border: 1px solid rgba(255, 196, 61, 0.28);
  color: #ffe29a;
  font-size: 12px;
  line-height: 1.4;
}
.sub-card { margin-top: 12px; background: rgba(255,255,255,0.85); border: 1px solid rgba(12,33,54,0.08); border-radius: 8px; padding: 10px; }
.sub-title { font-size: 13px; color: #0d223a; font-weight: 600; margin-bottom: 8px; }
.chart-card.white { background: #fff; border-radius: 8px; padding: 16px; }
.card-head.between { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; color: #0d223a; }
.json-fallback {
  margin-top: 12px;
  background: rgba(0,0,0,0.22);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  padding: 12px;
  color: rgba(255,255,255,0.78);
  font-size: 12px;
  line-height: 1.5;
  max-height: 260px;
  overflow: auto;
}
.empty-state { padding: 80px 0; text-align: center; color: rgba(255,255,255,0.35); }
.empty-title { font-size: 14px; }
.paper-table { background: #fff; border-radius: 8px; padding: 10px; }
.three-line-table :deep(.ant-table-thead) > tr > th { background: #f0f0f0; font-weight: 600; border: none; }
.three-line-table :deep(.ant-table-container) { border-top: 2px solid #121212; border-bottom: 2px solid #121212; }
.three-line-table :deep(.ant-table-tbody > tr > td) { border: none; }
.table-footnote { margin-top: 8px; font-size: 11px; color: #8a8a8a; font-style: italic; }
.card-grid .card.collapsible { max-height: 220px; overflow-y: auto; }
.platform-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; margin-bottom: 16px; }
.platform-card { border: 1px solid rgba(0,210,210,0.15); border-radius: 14px; background: rgba(7, 15, 26, 0.78); padding: 14px; display: grid; gap: 10px; }
.platform-card--green { border-color: rgba(16,185,129,.28); }
.platform-card--yellow { border-color: rgba(245,158,11,.28); }
.platform-card--red { border-color: rgba(239,68,68,.28); }
.platform-card__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.platform-card__title { color: #e9fcff; font-size: 15px; font-weight: 700; }
.platform-card__sub { color: #8eb3bc; font-size: 12px; line-height: 1.5; }
.platform-kpi-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.platform-kpi { border: 1px solid rgba(0,210,210,0.12); border-radius: 10px; padding: 10px; background: rgba(3,10,18,0.48); display: grid; gap: 4px; }
.platform-kpi span { color: #7da8b2; font-size: 11px; }
.platform-kpi strong { color: #f3feff; font-size: 16px; }
.platform-chip-row { display: flex; flex-wrap: wrap; gap: 8px; }
.platform-chip { padding: 4px 10px; border-radius: 999px; border: 1px solid rgba(0,210,210,0.15); color: #d8f7fb; font-size: 11px; }
.platform-chip--warn { border-color: rgba(245,158,11,.28); color: #facc15; }
.platform-summary-row { display: flex; flex-wrap: wrap; gap: 10px; color: #8eb3bc; font-size: 12px; }
.platform-list { display: grid; gap: 8px; }
.platform-list__item { display: flex; justify-content: space-between; gap: 10px; padding: 10px 12px; border-radius: 10px; background: rgba(3,10,18,0.42); border: 1px solid rgba(0,210,210,0.1); }
.platform-list__item strong { color: #eefcff; font-size: 13px; }
.platform-list__meta { color: #7da8b2; font-size: 11px; margin-top: 2px; }
.platform-list__time { color: #7da8b2; font-size: 11px; white-space: nowrap; }
.platform-empty, .platform-error { font-size: 12px; color: #8eb3bc; }
.platform-error { color: #f87171; }
.artifact-link { color: #67e8f9; font-size: 12px; align-self: center; }
.tab-content :deep(.ant-collapse) { background: transparent; border: none; }
.tab-content :deep(.ant-collapse-item) { border: none; }
.tab-content :deep(.ant-collapse-content) { background: transparent !important; }
.tab-content :deep(.ant-select), .tab-content :deep(.ant-input-number), .tab-content :deep(.ant-input) { width: 100%; }
.session-row { display: flex; justify-content: space-between; align-items: center; }
@media (max-width: 1400px) {
  .form-grid.three { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .platform-strip { grid-template-columns: 1fr; }
  .platform-kpi-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
html[data-theme='light'] .workbench {
  background:
    radial-gradient(circle at top right, rgba(59, 130, 246, 0.08), rgba(59, 130, 246, 0) 36%),
    linear-gradient(180deg, #f4f8fc 0%, #edf3f9 100%);
  color: #1f3852;
}
html[data-theme='light'] .hero-card,
html[data-theme='light'] .platform-card,
html[data-theme='light'] .nav-panel,
html[data-theme='light'] .content-panel,
html[data-theme='light'] .card,
html[data-theme='light'] .config-card,
html[data-theme='light'] .next-step-card,
html[data-theme='light'] .planner-block,
html[data-theme='light'] .filter-panel,
html[data-theme='light'] .result-card,
html[data-theme='light'] .var-tag,
html[data-theme='light'] .group-card,
html[data-theme='light'] .sub-card {
  border-color: rgba(187, 204, 220, 0.72);
  background: rgba(241, 246, 251, 0.98);
}
html[data-theme='light'] .hero-card h2,
html[data-theme='light'] .platform-card__title,
html[data-theme='light'] .card-head,
html[data-theme='light'] .sub-title,
html[data-theme='light'] .card-head.between,
html[data-theme='light'] .group-card strong {
  color: #16324f;
}
html[data-theme='light'] .hero-card p,
html[data-theme='light'] .platform-card__sub,
html[data-theme='light'] .platform-summary-row,
html[data-theme='light'] .platform-list__meta,
html[data-theme='light'] .platform-list__time,
html[data-theme='light'] .platform-empty,
html[data-theme='light'] .cohort-pill.empty,
html[data-theme='light'] .nav-item,
html[data-theme='light'] .var-category,
html[data-theme='light'] .prep-hint,
html[data-theme='light'] .prep-summary,
html[data-theme='light'] .var-head-actions,
html[data-theme='light'] .overview-line,
html[data-theme='light'] .radio-option,
html[data-theme='light'] .diag-search-tip,
html[data-theme='light'] .status-line,
html[data-theme='light'] .recommend,
html[data-theme='light'] .label,
html[data-theme='light'] .result-meta,
html[data-theme='light'] .table-footnote,
html[data-theme='light'] .empty-state {
  color: #6f8399;
}
html[data-theme='light'] .cohort-pill {
  background: rgba(219, 234, 254, 0.98);
  color: #1d4ed8;
}
html[data-theme='light'] .platform-kpi {
  border-color: rgba(187, 204, 220, 0.72);
  background: #ffffff;
}
html[data-theme='light'] .platform-kpi span { color: #6f8399; }
html[data-theme='light'] .platform-kpi strong { color: #16324f; }
html[data-theme='light'] .platform-chip { border-color: rgba(187, 204, 220, 0.72); color: #47627e; background: #ffffff; }
html[data-theme='light'] .platform-list__item { border-color: rgba(187, 204, 220, 0.72); background: #ffffff; }
html[data-theme='light'] .artifact-link { color: #1d4ed8; }
html[data-theme='light'] .cohort-pill.link:hover { background: rgba(191, 219, 254, 0.98); }
html[data-theme='light'] .warn-banner {
  background: rgba(254, 243, 199, 0.98);
  border-color: rgba(245, 158, 11, 0.28);
  color: #b45309;
}
html[data-theme='light'] .nav-item.active {
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.98);
  box-shadow: inset 3px 0 0 #1d4ed8;
}
html[data-theme='light'] .nav-item.divider { border-top-color: rgba(187, 204, 220, 0.72); }
html[data-theme='light'] .status-dot { background: rgba(148, 180, 206, 0.5); }
html[data-theme='light'] .status-dot.ready { background: #10b981; box-shadow: 0 0 6px rgba(16,185,129,.4); }
html[data-theme='light'] .status-check { color: #059669; }
html[data-theme='light'] .group-card.survive { background: rgba(220, 252, 231, 0.98); }
html[data-theme='light'] .group-card.death { background: rgba(255, 241, 242, 0.98); }
html[data-theme='light'] .group-card span { color: #47627e; }
html[data-theme='light'] .var-tag.selected {
  background: rgba(219, 234, 254, 0.98);
  border-color: rgba(59, 130, 246, 0.35);
  color: #1d4ed8;
  box-shadow: none;
}
html[data-theme='light'] .var-tag.filtered { box-shadow: inset 3px 0 0 #1d4ed8; }
html[data-theme='light'] .range-row input[type=\"number\"] {
  background: rgba(241, 246, 251, 0.98);
  border-color: rgba(187, 204, 220, 0.72);
  color: #1f3852;
}
html[data-theme='light'] .quick-btn {
  border-color: rgba(59, 130, 246, 0.32);
  color: #1d4ed8;
}
html[data-theme='light'] .quick-btn:hover { background: rgba(219, 234, 254, 0.98); }
html[data-theme='light'] .btn-apply {
  background: rgba(219, 234, 254, 0.98);
  border-color: rgba(59, 130, 246, 0.36);
  color: #1d4ed8;
}
html[data-theme='light'] .btn-clear {
  border-color: rgba(187, 204, 220, 0.72);
  color: #6f8399;
}
html[data-theme='light'] .planner-step-row,
html[data-theme='light'] .planner-log-row,
html[data-theme='light'] .planner-step-state,
html[data-theme='light'] .planner-log-time,
html[data-theme='light'] .quality-pill {
  color: #6f8399;
}
html[data-theme='light'] .quality-pill {
  background: rgba(254, 243, 199, 0.98);
  border-color: rgba(245, 158, 11, 0.28);
}
</style>
