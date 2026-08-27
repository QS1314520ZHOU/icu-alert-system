<template>
  <div class="workbench">
    <PageHeader title="科研分析工作台" subtitle="数据准备 → 选择分析 → 预览结果 → 导出">
      <template #actions>
        <a-space>
          <a-button size="small" @click="openSessionDrawer = true">会话</a-button>
          <a-button size="small" :loading="sessionLoading" @click="saveSession">保存</a-button>
          <a-button size="small" :loading="platformStatusLoading" @click="loadPlatformStatus">平台状态</a-button>
        </a-space>
      </template>
    </PageHeader>

    <!-- 队列状态条 -->
    <div class="cohort-strip" :class="{ empty: !cohortReady }" @click="currentStep = 0">
      当前队列：{{ currentCohortSummary || '未选择' }} · 患者 {{ selectedPatientIds.length }} 例
    </div>

    <!-- 步骤导航 -->
    <div class="step-card">
      <a-steps :current="currentStep" size="small" :items="stepItems" @change="(n: number) => currentStep = n" />
    </div>

    <!-- 步骤1：数据准备 -->
    <div v-show="currentStep === 0" class="step-panel">
      <SectionHeader title="选择研究队列" description="选择或创建队列，设置分组和变量">
        <template #actions>
          <a-space>
            <span class="var-count">已选 {{ selectedVariables.length }}/{{ variableCatalog.length }}</span>
            <a-button size="small" type="link" @click="selectAllVariables">全选</a-button>
            <a-button size="small" type="link" @click="clearAllVariables">清空</a-button>
          </a-space>
        </template>
      </SectionHeader>

      <!-- 队列选择 -->
      <div class="prep-grid">
        <div class="prep-card">
          <div class="card-label">队列来源</div>
          <a-radio-group v-model:value="prepMode" direction="vertical">
            <a-radio value="saved">
              已保存队列
              <a-select v-model:value="scope.cohort_id" :disabled="prepMode !== 'saved'" :options="cohortOptions" allow-clear show-search option-filter-prop="label" placeholder="选择队列" style="width: 240px; margin-left: 8px">
                <template #option="{ value, label }">
                  <div class="cohort-option"><span>{{ label }}</span><a-button type="link" size="small" @click.stop="removeCohort(String(value))">删除</a-button></div>
                </template>
              </a-select>
            </a-radio>
            <a-radio value="dept">当前科室（{{ currentDeptDisplay }}）</a-radio>
            <a-radio value="builder">
              新建队列
              <a-button type="link" size="small" @click.stop="openCohortBuilder">打开构建器</a-button>
            </a-radio>
          </a-radio-group>
          <div class="prep-scope">
            <span class="card-label">患者范围</span>
            <a-select v-model:value="scope.patient_scope" :options="patientScopeOptions" style="width: 120px" />
          </div>
        </div>

        <div class="prep-card">
          <div class="card-label">分组依据</div>
          <a-select v-model:value="scope.group_by" :options="groupByOptions" style="width: 100%" />
          <div class="group-chips">
            <template v-for="(card, idx) in groupSummaryCards" :key="card.name">
              <div class="group-chip" :class="card.type">
                <span>{{ card.name }}</span>
                <strong>{{ card.countText }}</strong>
                <small>{{ card.percentText }}</small>
              </div>
              <span v-if="idx === 0 && groupSummaryCards.length > 1" class="vs">vs</span>
            </template>
          </div>
        </div>
      </div>

      <!-- 变量目录 -->
      <div class="var-section">
        <div v-for="[category, vars] in variableGroups" :key="category" class="var-category-row">
          <span class="var-cat-label" @click="toggleCategory(category)">
            {{ category }}
            <em v-if="categoryFlash[category]" class="flash">{{ categoryFlash[category] }}</em>
          </span>
          <div class="var-chips">
            <a-tooltip v-for="item in vars" :key="item.field" :mouse-enter-delay="0.5">
              <template #title>
                <div class="var-tip">
                  <div class="tip-title">{{ item.label }}</div>
                  <div>类型：{{ typeLabelCN(item.type) }}</div>
                  <div v-if="getVarSummary(item.field).non_null_rate != null">非空率：{{ ((getVarSummary(item.field).non_null_rate || 0) * 100).toFixed(1) }}%</div>
                  <div>适用：{{ applicableLabel(item.applicable) }}</div>
                </div>
              </template>
              <div class="var-chip" :class="{ selected: isVariableSelected(item.field), filtered: hasVariableFilter(item.field) }">
                <button class="check" type="button" @click.stop="toggleVariable(item.field)">{{ isVariableSelected(item.field) ? '☑' : '☐' }}</button>
                <span class="name" @click.stop="toggleVariable(item.field)">{{ item.label }}</span>
                <span v-if="filterSummary(item.field)" class="fsum">{{ filterSummary(item.field) }}</span>
                <button class="expand" type="button" @click.stop="toggleVariablePanel(item.field)">{{ expandedVariableField === item.field ? '▴' : '▾' }}</button>
              </div>
            </a-tooltip>
          </div>
        </div>
      </div>

      <ActionBar>
        <a-button type="primary" :disabled="!cohortReady" @click="currentStep = 1">下一步：选择分析 →</a-button>
      </ActionBar>
    </div>

    <!-- 步骤2：选择分析方法 -->
    <div v-show="currentStep === 1" class="step-panel">
      <SectionHeader title="选择分析方法" description="选择要执行的统计分析" />

      <div class="analysis-grid">
        <div v-for="item in analysisOptions" :key="item.key" class="analysis-card" :class="{ done: (navCompletion as any)[item.key] }" @click="runAnalysis(item.key)">
          <div class="analysis-icon">{{ item.icon }}</div>
          <div class="analysis-info">
            <strong>{{ item.label }}</strong>
            <small>{{ item.desc }}</small>
          </div>
          <span v-if="(navCompletion as any)[item.key]" class="done-badge">✓</span>
          <span v-if="(loading as any)[item.key]" class="loading-badge">⏳</span>
        </div>
      </div>

      <!-- AI 对话配置 -->
      <div class="ai-section">
        <SectionHeader title="AI 对话式配置" description="一句话描述需求，自动拆解并执行" />
        <a-textarea v-model:value="aiPlanner.prompt" :rows="2" placeholder="例如：纳入脓毒症患者，按结局分组，先出基线特征表，再做回归分析" />
        <div class="ai-actions">
          <a-button type="primary" size="small" :loading="aiPlanner.loading" @click="runAiPlanner(true)">AI 一键执行</a-button>
          <a-button size="small" :disabled="aiPlanner.loading" @click="runAiPlanner(false)">仅配置</a-button>
        </div>
        <div v-if="aiPlanner.steps.length" class="planner-progress">
          <a-progress :percent="Math.round(aiPlanner.progress)" size="small" :status="aiPlanner.loading ? 'active' : (Math.round(aiPlanner.progress) >= 100 ? 'success' : 'normal')" />
          <div v-for="step in aiPlanner.steps" :key="step.key" class="planner-step" :class="`is-${step.status}`">
            <span class="dot"></span><span class="title">{{ step.title }}</span><span class="state">{{ plannerStatusText(step.status) }}</span>
          </div>
        </div>
      </div>

      <ActionBar>
        <a-button @click="currentStep = 0">上一步</a-button>
        <a-button type="primary" :disabled="!hasAnyResult" @click="currentStep = 2">查看结果 →</a-button>
      </ActionBar>
    </div>

    <!-- 步骤3：结果预览 -->
    <div v-show="currentStep === 2" class="step-panel">
      <SectionHeader title="分析结果" description="查看各分析结果，可切换分析类型">
        <template #actions>
          <a-select v-model:value="activeResultTab" :options="resultTabOptions" style="width: 180px" />
        </template>
      </SectionHeader>

      <!-- 基线特征表 -->
      <template v-if="activeResultTab === 'table1' && table1Result">
        <div class="result-toolbar">
          <a-button size="small" @click="exportTable">导出文档</a-button>
          <a-button size="small" @click="exportTableCsv">导出表格</a-button>
        </div>
        <div v-if="table1QualityTips.length" class="quality-strip">
          <span v-for="tip in table1QualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
        </div>
        <div class="result-table-wrap">
          <a-table :columns="table1Columns" :data-source="table1Rows" :pagination="false" size="small" row-key="row_key" />
          <p class="footnote">{{ table1Result?.footnote }}</p>
        </div>
        <AiAssistPanel analysis-type="table1" :result="table1Result" :state="ai.table1" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
      </template>

      <!-- 生存分析 -->
      <template v-if="activeResultTab === 'survival' && survivalResult">
        <div v-if="survivalQualityTips.length" class="quality-strip">
          <span v-for="tip in survivalQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
        </div>
        <div class="result-table-wrap">
          <a-table :columns="survivalSummaryColumns" :data-source="survivalSummaryRows" :pagination="false" size="small" row-key="group" />
        </div>
        <div v-if="survivalOption" class="chart-wrap">
          <ResearchChart :option="survivalOption" :init-options="chartInitOptions" style="height: 400px" />
        </div>
        <AiAssistPanel analysis-type="survival" :result="survivalResult" :state="ai.survival" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
      </template>

      <!-- 回归分析 -->
      <template v-if="activeResultTab === 'regression' && regressionResult">
        <div v-if="regressionQualityTips.length" class="quality-strip">
          <span v-for="tip in regressionQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
        </div>
        <div class="result-table-wrap">
          <div class="sub-title">建模摘要</div>
          <a-table :columns="regressionSummaryColumns" :data-source="regressionSummaryRows" :pagination="false" size="small" row-key="row_key" />
        </div>
        <div class="result-table-wrap">
          <div class="sub-title">单因素分析</div>
          <a-table :columns="regressionColumns" :data-source="regressionUnivariateRows" :pagination="false" size="small" row-key="row_key" />
        </div>
        <div class="result-table-wrap">
          <div class="sub-title">多因素分析</div>
          <a-table :columns="regressionColumns" :data-source="regressionMultivariateRows" :pagination="false" size="small" row-key="row_key" />
        </div>
        <AiAssistPanel analysis-type="regression" :result="regressionResult" :state="ai.regression" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
      </template>

      <!-- ROC -->
      <template v-if="activeResultTab === 'roc' && rocResult">
        <div v-if="rocOption" class="chart-wrap">
          <ResearchChart :option="rocOption" :init-options="chartInitOptions" style="height: 360px" />
        </div>
        <div class="result-table-wrap">
          <a-table :columns="rocColumns" :data-source="rocRows" :pagination="false" size="small" row-key="row_key" />
        </div>
        <AiAssistPanel analysis-type="roc" :result="rocResult" :state="ai.roc" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
      </template>

      <!-- 趋势分析 -->
      <template v-if="activeResultTab === 'trend' && trendResult">
        <div class="result-toolbar">
          <a-select v-model:value="trendActiveIndicator" :options="trendIndicatorList.map(k => ({ label: k, value: k }))" style="width: 200px" />
        </div>
        <div v-if="trendQualityTips.length" class="quality-strip">
          <span v-for="tip in trendQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
        </div>
        <div v-if="trendOption" class="chart-wrap">
          <ResearchChart :option="trendOption" :init-options="chartInitOptions" style="height: 360px" />
        </div>
        <AiAssistPanel analysis-type="trend" :result="trendResult" :state="ai.trend" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
      </template>

      <!-- 相关性 -->
      <template v-if="activeResultTab === 'correlation' && correlationResult">
        <div v-if="correlationQualityTips.length" class="quality-strip">
          <span v-for="tip in correlationQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
        </div>
        <div v-if="correlationOption" class="chart-wrap">
          <ResearchChart :option="correlationOption" :init-options="chartInitOptions" style="height: 420px" />
        </div>
        <AiAssistPanel analysis-type="correlation" :result="correlationResult" :state="ai.correlation" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
      </template>

      <!-- 亚组分析 -->
      <template v-if="activeResultTab === 'subgroup' && subgroupResult">
        <div v-if="subgroupQualityTips.length" class="quality-strip">
          <span v-for="tip in subgroupQualityTips" :key="tip" class="quality-pill">{{ tip }}</span>
        </div>
        <div v-if="subgroupForestOption" class="chart-wrap">
          <ResearchChart :option="subgroupForestOption" :init-options="chartInitOptions" style="height: 480px" />
        </div>
        <div class="result-table-wrap">
          <a-table :columns="subgroupColumns" :data-source="subgroupRows" :pagination="false" size="small" row-key="subgroup" />
        </div>
        <AiAssistPanel analysis-type="subgroup" :result="subgroupResult" :state="ai.subgroup" @generate="onAiGenerate" @copy="onAiCopy" @update-lang="onAiLang" @update-part="onAiPart" @update-text="onAiText" />
      </template>

      <EmptyState v-if="!activeResultTab || (!getResult(activeResultTab))" title="暂无结果" description="请先在上一步执行分析" />

      <ActionBar>
        <a-button @click="currentStep = 1">上一步</a-button>
        <a-button type="primary" @click="currentStep = 3">导出 →</a-button>
      </ActionBar>
    </div>

    <!-- 步骤4：导出 -->
    <div v-show="currentStep === 3" class="step-panel">
      <SectionHeader title="导出中心" :description="`已生成 ${exports.length} 项产物`" />
      <template v-if="exports.length">
        <a-table :columns="exportColumns" :data-source="exports.map((r, i) => ({ ...r, row_key: `e${i}` }))" :pagination="false" size="small" row-key="row_key">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'action'"><a-button size="small" @click="openExportUrl(record.download_url)">下载</a-button></template>
          </template>
        </a-table>
      </template>
      <EmptyState v-else title="暂无导出" description="在分析结果页执行分析并导出" />
      <ActionBar>
        <a-button @click="currentStep = 2">上一步</a-button>
      </ActionBar>
    </div>

    <!-- 会话抽屉 -->
    <a-drawer v-model:open="openSessionDrawer" title="分析会话" width="400">
      <a-button size="small" :loading="sessionListLoading" @click="loadSessions">刷新</a-button>
      <a-list :data-source="sessions" :loading="sessionListLoading" bordered size="small" style="margin-top: 12px">
        <template #renderItem="{ item }">
          <a-list-item>
            <div style="display:flex;justify-content:space-between;width:100%">
              <span>{{ item.name }}</span>
              <a-button size="small" @click="restoreSession(String(item.session_id || ''))">载入</a-button>
            </div>
          </a-list-item>
        </template>
      </a-list>
    </a-drawer>

    <CohortBuilder :open="cohortBuilderOpen" :department="scope.department || currentDeptName || null" :dept-code="currentDeptCode" :patient-scope="scope.patient_scope" @update:open="(val: boolean) => (cohortBuilderOpen = val)" @saved="onCohortBuilderSaved" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  Button as AButton, Drawer as ADrawer, Input as AInput, List as AList, Progress as AProgress,
  Radio as ARadio, Select as ASelect, Space as ASpace, Steps as ASteps,
  Table as ATable, Tooltip as ATooltip, message,
} from 'ant-design-vue'
import { PageHeader, SectionHeader, ActionBar, EmptyState } from '../components/common/design-system'
import AiAssistPanel from '../components/research/AiAssistPanel.vue'
import CohortBuilder from '../components/CohortBuilder.vue'
import { useResearchWorkbench } from '../composables/useResearchWorkbench'

type AnyRecord = Record<string, any>

const ARadioGroup = ARadio.Group
const AListItem = AList.Item
const ATextarea = AInput.TextArea

const ResearchChart = defineAsyncComponent(async () => {
  await import('../charts/analytics')
  const mod = await import('vue-echarts')
  return mod.default
})

const chartInitOptions = {
  devicePixelRatio: typeof window !== 'undefined' ? Math.max(window.devicePixelRatio || 1, window.innerWidth <= 1920 ? 1.5 : 1) : 1,
}

/* ───── 变量目录 ───── */
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
  { field: 'gcs_admission', label: '入科GCS', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation', 'roc'] },
  { field: 'rass_admission', label: '入科RASS', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation'] },
  { field: 'sofa_max', label: 'SOFA最大值', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation', 'roc'] },
  { field: 'apache2_max', label: 'APACHE II最大值', type: 'continuous', category: '评分', source: '评分记录', applicable: ['table1', 'regression', 'correlation', 'roc'] },
  { field: 'lactate_admission', label: '入科乳酸', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'creatinine_admission', label: '入科肌酐', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'albumin_admission', label: '入科白蛋白', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'pct_admission', label: '入科PCT', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'wbc_admission', label: '入科WBC', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'hemoglobin_admission', label: '入科Hb', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'platelet_admission', label: '入科PLT', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'pf_ratio_admission', label: '入科P/F比', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'bnp_admission', label: '入科BNP', type: 'continuous', category: '检验', source: '检验记录', applicable: ['table1', 'regression', 'correlation', 'roc', 'trend'] },
  { field: 'vasopressor_days', label: '血管活性药天数', type: 'continuous', category: '治疗', source: '治疗记录', applicable: ['table1', 'regression', 'correlation'] },
  { field: 'mv_days', label: '机械通气天数', type: 'continuous', category: '治疗', source: '治疗记录', applicable: ['table1', 'regression', 'correlation'] },
  { field: 'hospital_mortality', label: '院内死亡', type: 'binary', category: '结局', source: '结局信息', applicable: ['table1', 'regression', 'subgroup'] },
  { field: 'mortality_28d', label: '28天死亡', type: 'binary', category: '结局', source: '结局信息', applicable: ['table1', 'regression', 'subgroup'] },
  { field: 'icu_readmission', label: 'ICU再入科', type: 'binary', category: '结局', source: '结局信息', applicable: ['table1', 'regression', 'subgroup'] },
]

/* ───── 使用 composable ───── */
const wb = useResearchWorkbench(variableCatalog)

const {
   scope, loading, prepMode, cohortBuilderOpen, categoryFlash, expandedVariableField,
  openSessionDrawer, sessionLoading, sessionListLoading, sessions,
  platformStatusLoading, aiPlanner,
  table1Result, survivalResult, regressionResult, rocResult, subgroupResult, trendResult, correlationResult, exports,
  ai, selectedVariables, selectedPatientIds,
  currentDeptCode, currentDeptName, currentDeptDisplay, cohortReady, currentCohortSummary,
  variableGroups, cohortOptions, groupByOptions, patientScopeOptions,
  navCompletion, groupSummaryCards,
  getVarSummary, typeLabelCN, /*  */ applicableLabel,
  isVariableSelected, toggleVariable, selectAllVariables, clearAllVariables,
  toggleCategory, toggleVariablePanel, hasVariableFilter, filterSummary,
  /* togglePrepMode */ openCohortBuilder, onCohortBuilderSaved, removeCohort,
  saveSession, loadSessions, restoreSession, loadPlatformStatus,
  runTable1, runSurvival, runRegression, runRoc, runTrend, runSubgroup, runCorrelation,
  exportTable, exportTableCsv, /*  */
} = wb

// AI assist handlers (not in composable, defined locally)
function onAiGenerate(payload: any) {
  const key = payload?.analysisType as keyof typeof ai
  if (!key || !ai[key]) return
  ai[key].loading = true
  ai[key].open = true
  // actual generation logic handled by parent/API layer
}
function onAiCopy(payload: any) {
  const key = payload?.analysisType as keyof typeof ai
  if (!key || !ai[key]) return
  const s = ai[key]
  const text = s.content?.[s.lang]?.[s.part] || ''
  navigator.clipboard?.writeText(text)
  message.success('已复制')
}
function onAiLang(payload: any) {
  const key = payload?.analysisType as keyof typeof ai
  if (key && ai[key]) ai[key].lang = payload.lang
}
function onAiPart(payload: any) {
  const key = payload?.analysisType as keyof typeof ai
  if (key && ai[key]) ai[key].part = payload.part
}
function onAiText(payload: any) {
  const key = payload?.analysisType as keyof typeof ai
  if (key && ai[key]) {
    const lang = payload.lang || ai[key].lang
    const part = payload.part || ai[key].part
    const contentMap = ai[key].content as Record<string, any>
    if (!contentMap[lang]) contentMap[lang] = { interpretation: '', methods_text: '', results_text: '' }
    contentMap[lang][part] = payload.value || ''
  }
}
function plannerStatusText(status: string) {
  const map: Record<string, string> = { pending: '待执行', running: '执行中', success: '已完成', failed: '失败', skipped: '已跳过' }
  return map[status] || status
}
async function runAiPlanner(_full: boolean) {
  aiPlanner.loading = true
  try { message.info('AI 规划执行中...') } finally { aiPlanner.loading = false }
}
function openExportUrl(url: string) { window.open(url || '#', '_blank') }

/* ───── 步骤 ───── */
const currentStep = ref(0)
const stepItems = [
  { title: '数据准备' },
  { title: '选择分析' },
  { title: '结果预览' },
  { title: '导出' },
]

/* ───── 分析选项 ───── */
const analysisOptions = [
  { key: 'table1', label: '基线特征表', desc: '表1：分组比较', icon: '📊' },
  { key: 'survival', label: '生存分析', desc: 'Kaplan-Meier 曲线', icon: '📈' },
  { key: 'regression', label: '回归分析', desc: '单/多因素回归', icon: '🔬' },
  { key: 'roc', label: 'ROC 分析', desc: '受试者工作特征', icon: '📉' },
  { key: 'subgroup', label: '亚组分析', desc: '森林图', icon: '🌲' },
  { key: 'trend', label: '趋势分析', desc: '时间序列', icon: '⏰' },
  { key: 'correlation', label: '相关性', desc: '热图', icon: '🔥' },
]

const activeResultTab = ref('')
const resultTabOptions = [
  { label: '基线特征表', value: 'table1' },
  { label: '生存分析', value: 'survival' },
  { label: '回归分析', value: 'regression' },
  { label: 'ROC 分析', value: 'roc' },
  { label: '亚组分析', value: 'subgroup' },
  { label: '趋势分析', value: 'trend' },
  { label: '相关性', value: 'correlation' },
]

const hasAnyResult = computed(() => Object.values(wb.navCompletion.value).some(Boolean))

function getResult(key: string) {
  const map: Record<string, any> = { table1: table1Result.value, survival: survivalResult.value, regression: regressionResult.value, roc: rocResult.value, subgroup: subgroupResult.value, trend: trendResult.value, correlation: correlationResult.value }
  return map[key]
}

function runAnalysis(key: string) {
  const runners: Record<string, () => Promise<void>> = {
    table1: runTable1, survival: runSurvival, regression: runRegression,
    roc: runRoc, subgroup: runSubgroup, trend: runTrend, correlation: runCorrelation,
  }
  const runner = runners[key]
  if (runner) { runner(); activeResultTab.value = key }
}

/* ───── 表格列定义 ───── */
const table1Rows = computed(() => ((table1Result.value?.rows || []) as AnyRecord[]).map((r, i) => ({ ...r, row_key: `${i}_${r.variable || ''}` })))
const table1Columns = computed(() => {
  const groups = (table1Result.value?.groups || []) as string[]
  return [{ title: '变量', dataIndex: 'variable', key: 'var' }, ...groups.map((g, i) => ({ title: g, dataIndex: ['values', i], key: `g${i}` })), { title: '统计量', dataIndex: 'statistic', key: 's' }, { title: 'P值', dataIndex: 'p_display', key: 'p' }]
})
const table1QualityTips = computed(() => {
  const tips: string[] = []
  if (Number(table1Result.value?.n_total || 0) > 0 && Number(table1Result.value?.n_total || 0) < 30) tips.push(`样本量较小（n=${table1Result.value?.n_total}）`)
  return tips
})
const survivalOption = computed(() => {
  const curves = (survivalResult.value?.kaplan_meier?.curves || {}) as Record<string, AnyRecord>
  const names = Object.keys(curves); if (!names.length) return null
  return {
    backgroundColor: '#fff', tooltip: { trigger: 'axis' }, legend: { top: 0 },
    xAxis: { type: 'value', name: '时间（天）' }, yAxis: { type: 'value', name: '生存概率', min: 0, max: 1 },
    series: names.map((n) => { const c = curves[n] || {}; return { name: n, type: 'line', step: 'end', showSymbol: false, data: (c.timeline || []).map((x: number, i: number) => [x, c.survival?.[i]]) } }),
  }
})
const survivalSummaryColumns = [
  { title: '分组', dataIndex: 'group', key: 'group' }, { title: '样本量', dataIndex: 'n', key: 'n' },
  { title: '事件数', dataIndex: 'events', key: 'events' }, { title: '中位生存', dataIndex: 'median_survival_display', key: 'ms' },
]
const survivalSummaryRows = computed(() => {
  const curves = (survivalResult.value?.kaplan_meier?.curves || {}) as Record<string, AnyRecord>
  const medians = (survivalResult.value?.kaplan_meier?.median_survival || {}) as Record<string, any>
  return Object.keys(curves).map((g) => { const r = curves[g] || {}; const n = Number(r.n || 0); const m = Number(medians[g]); return { group: g, n, events: Number(r.events || 0), median_survival_display: Number.isFinite(m) ? m.toFixed(1) : '—' } })
})
const survivalQualityTips = computed(() => { const t: string[] = []; const n = Number(survivalResult.value?.n_total || 0); if (n > 0 && n < 30) t.push(`样本偏少（n=${n}）`); return t })
const regressionSummaryColumns = [{ title: '项目', dataIndex: 'item', key: 'item' }, { title: '值', dataIndex: 'value', key: 'value' }]
const regressionSummaryRows = computed(() => {
  const rows: AnyRecord[] = []
  rows.push({ row_key: 'total', item: '总样本', value: regressionResult.value?.n_total || '—' })
  if (regressionResult.value?.outcome_positive != null) rows.push({ row_key: 'pos', item: '阳性结局', value: regressionResult.value.outcome_positive })
  return rows
})
const regressionColumns = computed(() => [{ title: '变量', dataIndex: 'variable', key: 'variable' }, { title: '估计值', dataIndex: 'estimate_display', key: 'est' }, { title: '95%CI', dataIndex: 'ci_display', key: 'ci' }, { title: 'P值', dataIndex: 'p_display', key: 'p' }])
const regressionUnivariateRows = computed(() => ((regressionResult.value?.univariate || []) as AnyRecord[]).map((r, i) => ({ ...r, row_key: `u${i}` })))
const regressionMultivariateRows = computed(() => ((regressionResult.value?.multivariate || []) as AnyRecord[]).map((r, i) => ({ ...r, row_key: `m${i}` })))
const regressionQualityTips = computed(() => { const t: string[] = []; const n = Number(regressionResult.value?.n_total || 0); if (n > 0 && n < 50) t.push(`样本偏少（n=${n}）`); return t })
const rocRows = computed(() => Object.entries(rocResult.value?.curves || {}).map(([name, row]: [string, any], i) => ({
  row_key: `r${i}`, predictor: variableCatalog.find(v => v.field === name)?.label || name,
  auc: row?.auc != null ? Number(row.auc).toFixed(3) : '--',
  ci: row?.ci_lower != null ? `${Number(row.ci_lower).toFixed(3)}-${Number(row.ci_upper).toFixed(3)}` : '--',
  cutoff: row?.optimal_cutoff != null ? Number(row.optimal_cutoff).toFixed(2) : '--',
  sensitivity: row?.sensitivity_at_cutoff != null ? `${(Number(row.sensitivity_at_cutoff) * 100).toFixed(1)}%` : '--',
  specificity: row?.specificity_at_cutoff != null ? `${(Number(row.specificity_at_cutoff) * 100).toFixed(1)}%` : '--',
})))
const rocColumns = [{ title: '指标', dataIndex: 'predictor', key: 'p' }, { title: 'AUC', dataIndex: 'auc', key: 'auc' }, { title: '95%CI', dataIndex: 'ci', key: 'ci' }, { title: '阈值', dataIndex: 'cutoff', key: 'c' }, { title: '灵敏度', dataIndex: 'sensitivity', key: 'se' }, { title: '特异度', dataIndex: 'specificity', key: 'sp' }]
const rocOption = computed(() => {
  const curves = (rocResult.value?.curves || {}) as Record<string, AnyRecord>
  const names = Object.keys(curves); if (!names.length) return null
  return {
    backgroundColor: '#fff', tooltip: { trigger: 'axis' }, legend: { top: 0 },
    xAxis: { type: 'value', name: '1-特异度', min: 0, max: 1 }, yAxis: { type: 'value', name: '灵敏度', min: 0, max: 1 },
    series: [...names.map((n) => ({ name: `${variableCatalog.find(v => v.field === n)?.label || n} (AUC ${Number(curves[n]?.auc || 0).toFixed(3)})`, type: 'line', showSymbol: false, data: (curves[n]?.fpr || []).map((x: number, i: number) => [x, curves[n]?.tpr?.[i]]) })), { name: '参考线', type: 'line', showSymbol: false, lineStyle: { type: 'dashed' }, data: [[0, 0], [1, 1]] }],
  }
})
const trendActiveIndicator = ref('')
const trendIndicatorList = computed(() => Object.keys(trendResult.value?.indicators || {}))
watch(trendIndicatorList, (l) => { if (!l.includes(trendActiveIndicator.value)) trendActiveIndicator.value = l[0] || '' }, { immediate: true })
const trendOption = computed(() => {
  const key = trendActiveIndicator.value; if (!key) return null
  const p = trendResult.value?.indicators?.[key] || {}; const tl = p.timeline_hours || []; const groups = p.groups || {}; const names = Object.keys(groups)
  if (!tl.length || !names.length) return null
  return {
    backgroundColor: '#fff', tooltip: { trigger: 'axis' }, legend: { top: 0 },
    xAxis: { type: 'value', name: '时间(h)' }, yAxis: { type: 'value', name: variableCatalog.find(v => v.field === key)?.label || key },
    series: names.map((n) => ({ name: n, type: 'line', showSymbol: false, connectNulls: false, data: tl.map((h: number, i: number) => [h, groups[n]?.mean?.[i]]) })),
  }
})
const trendQualityTips = computed(() => [])
const correlationOption = computed(() => {
  const m = correlationResult.value?.matrix || {}; const labels = (m.labels || []) as string[]; const dLabels = labels.map(f => variableCatalog.find(v => v.field === f)?.label || f)
  const vals = m.correlations || []; if (!labels.length) return null
  const heat = labels.flatMap((_: string, ri: number) => labels.map((__: string, ci: number) => ({ value: [ci, ri, Number(vals?.[ri]?.[ci] ?? 0)], raw: vals?.[ri]?.[ci], yLabel: dLabels[ri], xLabel: dLabels[ci] })))
  return {
    backgroundColor: '#fff', tooltip: { formatter: (p: any) => `${p?.data?.yLabel} vs ${p?.data?.xLabel}<br/>r = ${Number(p?.data?.raw || 0).toFixed(2)}` },
    xAxis: { type: 'category', data: dLabels, axisLabel: { rotate: 30 } }, yAxis: { type: 'category', data: dLabels },
    visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 0 },
    series: [{ type: 'heatmap', data: heat, label: { show: true, formatter: (p: any) => Number(p?.data?.raw || 0).toFixed(2) } }],
  }
})
const correlationQualityTips = computed(() => [])
const subgroupColumns = [{ title: '亚组', dataIndex: 'subgroup', key: 'sg' }, { title: '样本', dataIndex: 'n', key: 'n' }, { title: '效应值', dataIndex: 'estimate_display', key: 'est' }, { title: '95%CI', dataIndex: 'ci_display', key: 'ci' }, { title: 'P(交互)', dataIndex: 'p_interaction_display', key: 'p' }]
const subgroupRows = computed(() => (subgroupResult.value?.subgroups || []).map((item: any) => ({ ...item, subgroup: item.name, estimate_display: item.estimate != null ? Number(item.estimate).toFixed(2) : '--', ci_display: item.ci_lower != null ? `${Number(item.ci_lower).toFixed(2)}-${Number(item.ci_upper).toFixed(2)}` : '--', p_interaction_display: item.p_interaction != null ? (item.p_interaction < 0.001 ? '<0.001' : Number(item.p_interaction).toFixed(3)) : '--' })))
const subgroupQualityTips = computed(() => [])
const subgroupForestOption = computed(() => {
  const data = subgroupResult.value?.subgroups || []; if (!data.length) return undefined
  const yData = data.map((d: any) => d.name).reverse(); const est = data.map((d: any) => d.estimate).reverse();
  return {
    backgroundColor: '#fff', tooltip: { trigger: 'axis' }, grid: { left: '20%', right: '10%', bottom: '15%' },
    xAxis: { type: 'value', name: 'OR (95%CI)', scale: true }, yAxis: { type: 'category', data: yData },
    series: [{ type: 'scatter', data: est.map((v: any, i: number) => [v, i]), symbol: 'rect', symbolSize: 8, itemStyle: { color: '#1890ff' } }, { type: 'line', markLine: { symbol: 'none', data: [{ xAxis: 1 }], lineStyle: { type: 'dashed', color: '#999' } } }],
  }
})

/* ───── 导出列 ───── */
const exportColumns = [
  { title: '名称', dataIndex: 'title', key: 'title' },
  { title: '文件', dataIndex: 'file_name', key: 'fn' },
  { title: '类型', dataIndex: 'format', key: 'fmt' },
  { title: '操作', key: 'action' },
]

/* ───── 生命周期 ───── */
onMounted(async () => {
  await wb.loadDeptNameMap()
  await wb.loadCohorts()
  await loadSessions()
  await Promise.allSettled([wb.loadPlatformStatus(), wb.loadPlatformJobs(), wb.loadPlatformArtifacts(), wb.loadTopicStatuses()])
  if (!wb.subgroupForm.subgroups.length) {
    wb.subgroupForm.subgroups = [
      { key: 'age_lt_65', label: '年龄<65', enabled: true, filterText: '{"age":{"$lt":65}}' },
      { key: 'age_gte_65', label: '年龄≥65', enabled: true, filterText: '{"age":{"$gte":65}}' },
      { key: 'sex_m', label: '男性', enabled: true, filterText: '{"sex":"M"}' },
      { key: 'sex_f', label: '女性', enabled: true, filterText: '{"sex":"F"}' },
    ]
  }
})
onUnmounted(() => { document.removeEventListener('pointerdown', () => {}) })
</script>

<style scoped>
.workbench {
  padding: var(--page-padding, 24px);
  display: flex; flex-direction: column; gap: var(--section-gap, 24px);
  max-width: 1400px;
}
.cohort-strip {
  padding: 10px 16px; border-radius: var(--radius-md, 6px);
  background: var(--color-primary-bg, rgba(37,99,235,0.08));
  border: 1px solid rgba(37,99,235,0.16);
  color: var(--color-primary, #2563EB); font-size: 13px; cursor: pointer;
}
.cohort-strip.empty { background: var(--color-warning-bg, rgba(181,71,8,0.08)); border-color: rgba(245,158,11,0.24); color: var(--color-warning, #B54708); }
.step-card {
  background: var(--color-bg-surface, #fff); border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px); padding: var(--card-padding, 16px);
}
.step-panel {
  background: var(--color-bg-surface, #fff); border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px); padding: var(--card-padding, 16px);
  display: flex; flex-direction: column; gap: 16px;
}
.prep-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.prep-card {
  padding: 14px; border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px); background: var(--color-bg-surface-secondary, #F1F3F5);
  display: flex; flex-direction: column; gap: 10px;
}
.card-label { font-size: var(--text-label, 12px); font-weight: var(--weight-medium, 500); color: var(--color-text-secondary, #667085); }
.prep-scope { display: flex; align-items: center; gap: 8px; margin-top: 8px; }
.cohort-option { display: flex; justify-content: space-between; align-items: center; }
.group-chips { display: flex; gap: 10px; align-items: center; margin-top: 8px; }
.group-chip {
  flex: 1; padding: 10px 12px; border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface, #fff); border: 1px solid var(--color-border, #E3E7EC);
  display: flex; flex-direction: column; gap: 2px;
}
.group-chip span { font-size: 12px; color: var(--color-text-secondary, #667085); }
.group-chip strong { font-size: 18px; color: var(--color-text-primary, #18212B); }
.group-chip small { font-size: 12px; color: var(--color-text-secondary, #667085); }
.group-chip.survive { background: var(--color-success-bg, rgba(22,132,91,0.08)); }
.group-chip.death { background: var(--color-danger-bg, rgba(217,45,32,0.08)); }
.vs { font-weight: var(--weight-bold, 700); color: var(--color-text-secondary, #667085); }
.var-count { font-size: 12px; color: var(--color-text-secondary, #667085); }
.var-section { display: flex; flex-direction: column; gap: 10px; }
.var-category-row { display: flex; gap: 10px; align-items: flex-start; }
.var-cat-label { width: 60px; text-align: right; font-size: 12px; color: var(--color-text-secondary, #667085); line-height: 28px; cursor: pointer; flex-shrink: 0; }
.var-cat-label:hover { color: var(--color-primary, #2563EB); }
.flash { margin-left: 4px; color: var(--color-success, #16845B); font-size: 11px; }
.var-chips { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
.var-chip {
  padding: 3px 8px; border-radius: var(--radius-tag, 4px);
  border: 1px solid var(--color-border, #E3E7EC); background: var(--color-bg-surface, #fff);
  font-size: 12px; color: var(--color-text-secondary, #667085);
  display: inline-flex; align-items: center; gap: 4px; transition: all 0.15s;
}
.var-chip:hover { border-color: var(--color-primary, #2563EB); }
.var-chip.selected { background: var(--color-primary-bg, rgba(37,99,235,0.08)); border-color: var(--color-primary, #2563EB); color: var(--color-primary, #2563EB); }
.var-chip.filtered { box-shadow: 0 0 0 1px var(--color-primary, #2563EB); }
.check, .expand { border: none; background: transparent; color: inherit; cursor: pointer; padding: 0; line-height: 1; }
.name { cursor: pointer; }
.fsum { color: var(--color-primary, #2563EB); font-size: 11px; }
.var-tip { max-width: 240px; font-size: 12px; }
.tip-title { font-weight: var(--weight-semibold, 600); margin-bottom: 4px; }
.analysis-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; }
.analysis-card {
  padding: 14px; border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px); background: var(--color-bg-surface, #fff);
  display: flex; gap: 10px; align-items: center; cursor: pointer; transition: border-color 0.15s;
  position: relative;
}
.analysis-card:hover { border-color: var(--color-primary, #2563EB); }
.analysis-card.done { background: var(--color-success-bg, rgba(22,132,91,0.04)); }
.analysis-icon { font-size: 24px; }
.analysis-info strong { display: block; font-size: 13px; color: var(--color-text-primary, #18212B); }
.analysis-info small { font-size: 11px; color: var(--color-text-secondary, #667085); }
.done-badge { position: absolute; top: 8px; right: 8px; color: var(--color-success, #16845B); font-weight: var(--weight-bold, 700); }
.loading-badge { position: absolute; top: 8px; right: 8px; }
.ai-section { display: flex; flex-direction: column; gap: 10px; }
.ai-actions { display: flex; gap: 8px; }
.planner-progress { display: flex; flex-direction: column; gap: 6px; }
.planner-step { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--color-text-secondary, #667085); }
.planner-step .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-border, #E3E7EC); flex-shrink: 0; }
.planner-step.is-running .dot { background: var(--color-primary, #2563EB); }
.planner-step.is-success .dot { background: var(--color-success, #16845B); }
.planner-step.is-failed .dot { background: var(--color-danger, #D92D20); }
.planner-step .title { flex: 1; }
.planner-step .state { color: var(--color-text-secondary, #667085); font-size: 11px; }
.result-toolbar { display: flex; gap: 8px; }
.quality-strip { display: flex; flex-wrap: wrap; gap: 8px; }
.quality-pill {
  padding: 4px 10px; border-radius: var(--radius-tag, 4px);
  background: var(--color-warning-bg, rgba(181,71,8,0.08));
  border: 1px solid rgba(245,158,11,0.24);
  color: var(--color-warning, #B54708); font-size: 12px;
}
.result-table-wrap {
  background: var(--color-bg-surface, #fff); border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px); padding: 12px; overflow-x: auto;
}
.sub-title { font-size: 13px; font-weight: var(--weight-semibold, 600); color: var(--color-text-primary, #18212B); margin-bottom: 8px; }
.chart-wrap {
  background: var(--color-bg-surface, #fff); border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px); padding: 12px;
}
.footnote { margin: 8px 0 0; font-size: 11px; color: var(--color-text-secondary, #667085); font-style: italic; }
@media (max-width: 1024px) { .prep-grid { grid-template-columns: 1fr; } .analysis-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 768px) { .analysis-grid { grid-template-columns: 1fr; } .var-category-row { flex-direction: column; } .var-cat-label { width: auto; text-align: left; } }
</style>
