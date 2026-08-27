<template>
  <div class="academic-page">
    <PageHeader title="科室学术科研支撑" subtitle="从临床问题发现到课题立项、数据质量评估的一站式科研入口">
      <template #actions>
        <a-button :loading="loading" @click="loadAll">刷新</a-button>
        <a-button type="primary" :loading="topicLoading" @click="generateTopics">AI 生成课题建议</a-button>
      </template>
    </PageHeader>

    <MetricStrip :metrics="kpiMetrics" />

    <!-- 主内容区：Tab 划分 -->
    <div class="main-tabs">
      <a-tabs v-model:activeKey="activeTab">
        <!-- Tab 1：项目管理 -->
        <a-tab-pane key="projects" tab="科研项目">
          <div class="tab-panel">
            <SectionHeader title="科研项目看板" description="管理论文、课题、基金和伦理项目">
              <template #actions>
                <a-button type="primary" size="small" @click="openProjectDrawer">新建项目</a-button>
              </template>
            </SectionHeader>

            <template v-if="projects.length">
              <div class="project-grid">
                <article v-for="project in projects" :key="project.project_id" class="project-card">
                  <div class="project-head">
                    <a-tag color="blue">{{ project.type || '课题' }}</a-tag>
                    <a-tag :color="statusColor(project.status)">{{ project.status || '计划中' }}</a-tag>
                  </div>
                  <h3>{{ project.title }}</h3>
                  <p>负责人：{{ ownerLabel(project.owner) }}</p>
                  <small>{{ project.journal_or_funding_source || project.remarks || '暂无备注' }}</small>
                </article>
              </div>

              <!-- 项目分布 -->
              <div class="sub-section">
                <SectionHeader title="项目状态分布" />
                <div class="distribution-grid">
                  <article v-for="row in statusRows" :key="row.key">
                    <span>{{ row.key }}</span>
                    <strong>{{ row.value }}</strong>
                  </article>
                </div>
              </div>

              <!-- 近期里程碑 -->
              <div class="sub-section">
                <SectionHeader title="近期里程碑" />
                <template v-if="milestones.length">
                  <div class="milestone-list">
                    <article v-for="item in milestones" :key="`${item.project_id}-${item.title}-${item.date}`">
                      <strong>{{ item.title }}</strong>
                      <span>{{ item.project_title }}</span>
                      <small>{{ item.date || '未设置日期' }} · {{ item.status }}</small>
                    </article>
                  </div>
                </template>
                <EmptyState v-else title="暂无里程碑" description="建议为项目补充伦理递交、数据锁库等节点" />
              </div>
            </template>

            <EmptyState v-else-if="!loading" title="还没有科研项目" description="可从 AI 课题推荐中选择方向一键转为项目">
              <template #action>
                <a-space>
                  <a-button type="primary" @click="openProjectDrawer">手动新建</a-button>
                  <a-button :loading="topicLoading" @click="generateTopics">生成课题建议</a-button>
                </a-space>
              </template>
            </EmptyState>
          </div>
        </a-tab-pane>

        <!-- Tab 2：数据质量 -->
        <a-tab-pane key="quality" tab="数据质量">
          <div class="tab-panel">
            <SectionHeader title="数据质量与 OMOP 导出" description="检查缺失率、异常值，治理后导出脱敏数据" />

            <MetricStrip :metrics="qualityMetrics" />

            <div class="quality-table-card">
              <div class="table-title">字段缺失率</div>
              <div v-if="missingRows.length" class="quality-table">
                <div class="quality-row quality-row--head">
                  <span>字段</span><span>缺失率</span>
                </div>
                <div v-for="row in missingRows.slice(0, 10)" :key="row.field" class="quality-row">
                  <span>{{ fieldLabel(row.field) }}</span><span>{{ row.rate }}</span>
                </div>
              </div>
              <div v-else class="soft-empty">当前未发现明显字段缺失。</div>
            </div>

            <!-- 数据治理建议 -->
            <div v-if="governance.length" class="sub-section">
              <SectionHeader title="数据治理建议" />
              <div class="governance-list">
                <article v-for="item in governance" :key="item.title" class="governance-card">
                  <a-tag :color="item.priority === 'high' ? 'red' : item.priority === 'medium' ? 'gold' : 'green'">
                    {{ item.priority === 'high' ? '优先' : item.priority === 'medium' ? '建议' : '通过' }}
                  </a-tag>
                  <div>
                    <strong>{{ item.title }}</strong>
                    <p>{{ item.detail }}</p>
                  </div>
                </article>
              </div>
            </div>

            <!-- OMOP 导出 -->
            <div class="omop-section">
              <div class="omop-note">
                <strong>OMOP 导出说明</strong>
                <p>默认脱敏，提供 PERSON、VISIT、CONDITION 等最小表集。</p>
              </div>
              <a-button :loading="omopLoading" @click="exportOmop">导出 OMOP 数据包</a-button>
            </div>
          </div>
        </a-tab-pane>

        <!-- Tab 3：AI 课题推荐 -->
        <a-tab-pane key="topics" tab="AI 课题推荐">
          <div class="tab-panel">
            <SectionHeader title="AI 潜在课题推荐" :description="topicSourceLabel + '，需 PI 人工确认'">
              <template #actions>
                <a-button :loading="topicLoading" @click="generateTopics">刷新课题</a-button>
              </template>
            </SectionHeader>

            <template v-if="topics.length">
              <div class="topic-grid">
                <article v-for="topic in topics" :key="topic.suggestion_id || topic.title" class="topic-card">
                  <div class="topic-title-row">
                    <h3>{{ localizeTitle(topic.title) }}</h3>
                    <a-button size="small" type="primary" ghost @click="createProjectFromTopic(topic)">转为项目</a-button>
                  </div>
                  <div v-if="showOriginalTitle(topic.title)" class="topic-original">原题：{{ topic.title }}</div>
                  <div class="topic-meta">
                    <span>{{ localizeStudyDesign(topic.study_design) }}</span>
                    <span>可行性 {{ topic.feasibility_score || '—' }}</span>
                    <span>{{ confidenceLabel(topic.confidence) }}</span>
                  </div>
                  <p class="topic-question">{{ localizeQuestion(topic.clinical_question) }}</p>
                  <div class="evidence-box">
                    <strong>数据依据</strong>
                    <span>{{ localizeText(topic.data_basis) }}</span>
                  </div>
                  <div class="topic-detail-row">
                    <div><dt>主要结局</dt><dd>{{ localizeOutcome(topic.primary_outcome) }}</dd></div>
                    <div><dt>伦理风险</dt><dd>{{ localizeEthicalRisk(topic.ethical_risk) }}</dd></div>
                  </div>
                  <div class="topic-foot">
                    <span>{{ topic.multi_center_potential ? '适合多中心' : '单中心优先' }}</span>
                    <span>需 PI 复核</span>
                  </div>
                </article>
              </div>
            </template>
            <EmptyState v-else title="暂无课题建议" description="点击上方 AI 生成课题建议 开始发现选题" />
          </div>
        </a-tab-pane>
      </a-tabs>
    </div>

    <!-- 新建项目抽屉 -->
    <a-drawer v-model:open="drawerOpen" width="520" title="新建科研项目">
      <a-alert class="drawer-tip" type="info" show-icon message="建议先填写最小信息，后续再补充。" />
      <a-form layout="vertical">
        <a-form-item label="项目标题"><a-input v-model:value="form.title" placeholder="例如：ARDS 俯卧位治疗质量改进研究" /></a-form-item>
        <a-form-item label="项目类型"><a-select v-model:value="form.type" :options="typeOptions" /></a-form-item>
        <a-form-item label="负责人 / PI"><a-input v-model:value="form.owner" placeholder="请输入负责人" /></a-form-item>
        <a-form-item label="项目状态"><a-select v-model:value="form.status" :options="statusOptions" /></a-form-item>
        <a-form-item label="期刊 / 基金来源"><a-input v-model:value="form.journal_or_funding_source" /></a-form-item>
        <a-form-item label="备注"><a-textarea v-model:value="form.remarks" :rows="4" /></a-form-item>
        <ActionBar>
          <a-button type="primary" :loading="saving" @click="saveProject">保存</a-button>
          <a-button @click="drawerOpen = false">取消</a-button>
        </ActionBar>
      </a-form>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  Alert as AAlert, Button as AButton, Drawer as ADrawer, Form as AForm, FormItem as AFormItem,
  Input as AInput, Select as ASelect, Space as ASpace, Tabs as ATabs, Tag as ATag, Textarea as ATextarea,
} from 'ant-design-vue'
import { PageHeader, SectionHeader, MetricStrip, ActionBar, EmptyState } from '../components/common/design-system'
import { useAcademicResearch } from '../composables/useAcademicResearch'

const ATabPane = ATabs.TabPane

const {
  loading, topicLoading, omopLoading, saving, drawerOpen,
  projects, topics, quality, governance,
  form, typeOptions, statusOptions,
  missingRows, topicSourceLabel, statusRows, milestones,
  localizeTitle, showOriginalTitle, localizeQuestion, localizeStudyDesign,
  localizeOutcome, localizeEthicalRisk, localizeText, fieldLabel,
  ownerLabel, statusColor, confidenceLabel,
  openProjectDrawer, createProjectFromTopic,
  loadAll, generateTopics, exportOmop, saveProject,
} = useAcademicResearch()

const activeTab = ref('projects')

const kpiMetrics = computed(() => [
  { label: '在管项目', value: projects.value.length, variant: 'info' as const },
  { label: 'AI 课题', value: topics.value.length, variant: 'default' as const },
  { label: '数据仓患者', value: quality.value.patient_count || 0, variant: 'default' as const },
  { label: '数据问题', value: (quality.value.time_logic_errors?.length || 0), variant: 'warning' as const },
])

const qualityMetrics = computed(() => [
  { label: '缺失字段', value: missingRows.value.length, variant: 'warning' as const },
  { label: '异常值', value: quality.value.outliers?.length || 0, variant: 'danger' as const },
  { label: '单位问题', value: quality.value.unit_inconsistencies?.length || 0, variant: 'warning' as const },
])
</script>

<style scoped>
.academic-page {
  padding: var(--page-padding, 24px);
  display: flex;
  flex-direction: column;
  gap: var(--section-gap, 24px);
  max-width: 1400px;
}
.main-tabs {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
}
.tab-panel { display: flex; flex-direction: column; gap: 20px; padding-top: 8px; }
.sub-section { margin-top: 8px; }
.project-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.project-card {
  padding: 14px;
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface, #fff);
  display: flex; flex-direction: column; gap: 8px;
}
.project-card h3 { margin: 0; font-size: var(--text-card-title, 14px); color: var(--color-text-primary, #18212B); }
.project-card p { margin: 0; font-size: var(--text-caption, 12px); color: var(--color-text-secondary, #667085); }
.project-card small { color: var(--color-text-secondary, #667085); font-size: 12px; }
.project-head { display: flex; justify-content: space-between; }
.distribution-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px;
}
.distribution-grid article {
  padding: 12px; border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px); background: var(--color-bg-surface-secondary, #F1F3F5);
}
.distribution-grid span { display: block; font-size: 12px; color: var(--color-text-secondary, #667085); }
.distribution-grid strong { display: block; margin-top: 4px; font-size: 20px; color: var(--color-text-primary, #18212B); }
.milestone-list { display: grid; gap: 8px; }
.milestone-list article {
  padding: 10px 12px; border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface-secondary, #F1F3F5); display: grid; gap: 3px;
}
.milestone-list strong { color: var(--color-text-primary, #18212B); font-size: 13px; }
.milestone-list span { color: var(--color-text-secondary, #667085); font-size: 12px; }
.milestone-list small { color: var(--color-text-secondary, #667085); font-size: 12px; }
.quality-table-card {
  background: var(--color-bg-surface, #fff);
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px);
  padding: var(--card-padding, 16px);
}
.table-title { font-size: var(--text-card-title, 14px); font-weight: var(--weight-semibold, 600); color: var(--color-text-primary, #18212B); margin-bottom: 12px; }
.quality-table {
  border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-md, 6px); overflow: hidden;
}
.quality-row {
  display: grid; grid-template-columns: 1fr 90px;
  padding: 9px 10px; border-bottom: 1px solid var(--color-border, #E3E7EC);
  font-size: var(--text-table, 13px);
}
.quality-row--head { font-weight: var(--weight-semibold, 600); background: var(--color-bg-surface-secondary, #F1F3F5); color: var(--color-text-primary, #18212B); }
.soft-empty { padding: 16px 0; text-align: center; color: var(--color-text-secondary, #667085); font-size: 13px; }
.governance-list { display: grid; gap: 8px; }
.governance-card {
  display: grid; grid-template-columns: 58px minmax(0, 1fr); gap: 8px;
  align-items: flex-start; padding: 10px 12px;
  border-radius: var(--radius-md, 6px); background: var(--color-bg-surface-secondary, #F1F3F5);
}
.governance-card strong { display: block; color: var(--color-text-primary, #18212B); font-size: 13px; }
.governance-card p { margin: 3px 0 0; color: var(--color-text-secondary, #667085); font-size: 12px; }
.omop-section {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 14px; border-radius: var(--radius-lg, 8px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border: 1px solid var(--color-border, #E3E7EC);
}
.omop-note strong { color: var(--color-text-primary, #18212B); font-size: 13px; }
.omop-note p { margin: 4px 0 0; color: var(--color-text-secondary, #667085); font-size: 12px; }
/* 课题推荐 */
.topic-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); gap: 14px; }
.topic-card {
  padding: 16px; border: 1px solid var(--color-border, #E3E7EC);
  border-radius: var(--radius-lg, 8px); background: var(--color-bg-surface, #fff);
  display: flex; flex-direction: column; gap: 12px;
}
.topic-title-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.topic-card h3 { margin: 0; font-size: var(--text-section-title, 16px); color: var(--color-text-primary, #18212B); line-height: 1.4; }
.topic-original { color: var(--color-text-secondary, #667085); font-size: 12px; margin-top: -8px; }
.topic-meta { display: flex; flex-wrap: wrap; gap: 8px; }
.topic-meta span {
  padding: 3px 10px; border-radius: var(--radius-tag, 4px);
  border: 1px solid var(--color-border, #E3E7EC);
  background: var(--color-primary-bg, rgba(37,99,235,0.08));
  color: var(--color-primary, #2563EB); font-size: 12px;
}
.topic-question {
  margin: 0; color: var(--color-text-primary, #18212B);
  font-size: var(--text-body, 14px); line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.evidence-box {
  padding: 12px; border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
  border: 1px solid var(--color-border, #E3E7EC); display: grid; gap: 6px;
}
.evidence-box strong { color: var(--color-primary, #2563EB); font-size: 12px; }
.evidence-box span {
  color: var(--color-text-secondary, #667085); font-size: 13px; line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.topic-detail-row {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px;
}
.topic-detail-row > div {
  padding: 10px 12px; border-radius: var(--radius-md, 6px);
  background: var(--color-bg-surface-secondary, #F1F3F5);
}
.topic-detail-row dt { color: var(--color-primary, #2563EB); font-size: 12px; margin: 0; }
.topic-detail-row dd {
  margin: 2px 0 0; color: var(--color-text-primary, #18212B); font-size: 13px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.topic-foot { display: flex; justify-content: space-between; font-size: 12px; color: var(--color-text-secondary, #667085); }
.drawer-tip { margin-bottom: 12px; }
@media (max-width: 1024px) {
  .topic-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .project-grid { grid-template-columns: 1fr; }
  .distribution-grid { grid-template-columns: repeat(2, 1fr); }
  .omop-section { flex-direction: column; align-items: flex-start; }
}
</style>
