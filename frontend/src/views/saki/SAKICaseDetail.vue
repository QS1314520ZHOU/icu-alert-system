<template>
  <div class="saki-case-detail" v-if="caseData">
    <a-page-header title="病例详情" @back="$router.back()">
      <template #extra>
        <a-tag :color="caseData.is_saki ? 'red' : 'green'" style="font-size:14px">
          {{ caseData.is_saki ? 'S-AKI 阳性' : 'S-AKI 阴性' }}
        </a-tag>
        <a-tag :color="stageColor(caseData.aki_stage)">AKI Stage {{ caseData.aki_stage }}</a-tag>
      </template>
    </a-page-header>

    <div class="detail-grid">
      <!-- 患者信息 -->
      <div class="card">
        <h3>患者信息</h3>
        <p><strong>ID:</strong> {{ caseData.patient_id }}</p>
        <p><strong>科室:</strong> {{ caseData.department }}</p>
        <p><strong>S-AKI 概率:</strong> {{ caseData.saki_probability }}</p>
      </div>

      <!-- 脓毒症表型 -->
      <div class="card">
        <h3>脓毒症表型</h3>
        <p>SOFA 评分: <strong>{{ caseData.sepsis_phenotype?.sofa_score ?? '-' }}</strong></p>
        <p>SOFA Δ: <strong>{{ caseData.sepsis_phenotype?.sofa_delta ?? '-' }}</strong></p>
        <p>感染证据: <a-tag :color="caseData.sepsis_phenotype?.infection_evidence?.verdict === 'supported' ? 'green' : 'default'">
          {{ caseData.sepsis_phenotype?.infection_evidence?.verdict ?? '-' }}
        </a-tag></p>
      </div>

      <!-- AKI 表型 -->
      <div class="card">
        <h3>AKI 表型 (KDIGO)</h3>
        <p>基线肌酐: <strong>{{ caseData.aki_phenotype?.creatinine_baseline ?? '-' }} umol/L</strong></p>
        <p>当前肌酐: <strong>{{ caseData.aki_phenotype?.creatinine_current ?? '-' }} umol/L</strong></p>
        <p>肌酐比值: <strong>{{ caseData.aki_phenotype?.creatinine_ratio?.toFixed(2) ?? '-' }}</strong></p>
        <p>类型: {{ caseData.aki_phenotype?.aki_type ?? '-' }}</p>
      </div>

      <!-- 时间关联 -->
      <div class="card">
        <h3>时间关联</h3>
        <p>脓毒症识别: {{ formatTime(caseData.temporal_association?.sepsis_onset_time) }}</p>
        <p>AKI 发生: {{ formatTime(caseData.temporal_association?.aki_onset_time) }}</p>
        <p>时间差: <strong>{{ caseData.temporal_association?.time_delta_hours?.toFixed(1) ?? '-' }} h</strong></p>
        <a-tag :color="caseData.temporal_association?.associated ? 'green' : 'red'">
          {{ caseData.temporal_association?.associated ? '时间关联' : '无时间关联' }}
        </a-tag>
      </div>

      <!-- 风险因素 -->
      <div class="card full-width">
        <h3>危险因素</h3>
        <a-tag v-for="f in caseData.risk_factors" :key="f.factor" color="orange" style="margin:2px">
          {{ f.factor }} ({{ f.source }})
        </a-tag>
        <span v-if="!caseData.risk_factors?.length" style="color:#bbb">未识别到危险因素</span>
      </div>

      <!-- 审核 -->
      <div class="card full-width">
        <h3>人工复核</h3>
        <p>当前状态: <a-tag>{{ reviewLabel(caseData.review_status) }}</a-tag></p>
        <div class="review-actions">
          <a-button type="primary" size="small" @click="submitReview('confirmed')">✅ 确认</a-button>
          <a-button danger size="small" @click="submitReview('rejected')">❌ 驳回</a-button>
          <a-button size="small" @click="submitReview('modified')">✏️ 修改</a-button>
        </div>
        <a-textarea v-model:value="reviewNotes" placeholder="复核备注" :rows="2" style="margin-top:8px;max-width:400px" />
      </div>
    </div>
  </div>
  <div v-else class="empty-state">加载中...</div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { message } from 'ant-design-vue'
import { getSakiCaseDetail, reviewSakiCase } from '../../api/saki'

const route = useRoute()
const caseData = ref<any>(null)
const reviewNotes = ref('')
const stageColor = (s: number) => ['green', 'orange', 'red', 'volcano'][s] || 'default'
const reviewLabel = (s: string) => ({ pending: '待审', confirmed: '已确认', rejected: '已驳回', modified: '已修改' }[s] || s)
const formatTime = (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-'

const loadCase = async () => {
  const id = route.params.caseId as string
  try {
    const res = await getSakiCaseDetail(id)
    caseData.value = res.data
  } catch (e) {
    message.error('加载病例失败')
  }
}

const submitReview = async (result: string) => {
  const id = route.params.caseId as string
  try {
    await reviewSakiCase(id, { reviewer_id: 'current_user', result, notes: reviewNotes.value })
    message.success('复核已提交')
    loadCase()
  } catch (e) {
    message.error('提交失败')
  }
}

onMounted(loadCase)
</script>

<style scoped>
.saki-case-detail { display: flex; flex-direction: column; gap: 16px; }
.detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.card { background: #fff; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }
.card h3 { margin: 0 0 8px; font-size: 14px; color: #1a1a2e; }
.card p { margin: 4px 0; font-size: 13px; }
.full-width { grid-column: 1 / -1; }
.review-actions { display: flex; gap: 8px; margin-top: 8px; }
.empty-state { text-align: center; padding: 60px; color: #bbb; }
</style>
