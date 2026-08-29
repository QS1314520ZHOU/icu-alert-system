/**
 * 病种中心 API 模块
 * 提供评分系统、病种管理、术语编码、表型规则等功能
 */
import api from './index'

// ---- 评分系统 ----

export interface ScoringSystem {
  name: string
  score_name: string
  rulepack_version: string
  status: string
}

export interface ScoringRule {
  id: string
  name: string
  score_system: string
  score_variant?: string
  version: string
  description?: string
  inputs: Array<{
    name: string
    label: string
    type: string
    unit?: string
    required?: boolean
  }>
  thresholds?: Array<{
    range: [number, number]
    label: string
    severity?: string
  }>
  missing_policy?: string
  time_window?: string
}

export interface ScoringResult {
  score_system: string
  score_variant?: string
  rule_id: string
  rule_version: string
  evaluation_time: string
  component_scores: Record<string, number>
  total_score: number
  missing_inputs: string[]
  evidence: Array<{
    input: string
    value: any
    source?: string
  }>
  input_snapshot_hash: string
}

export interface TestCase {
  name: string
  inputs: Record<string, any>
  expected_total?: number
  expected_components?: Record<string, number>
}

export interface TestCaseResult {
  test_case: TestCase
  result: ScoringResult
  passed: boolean
  diff?: {
    total: number
    components: Record<string, number>
  }
}

/** 评分系统健康检查 */
export const getScoringHealth = () =>
  api.get<{ status: string; scores: Record<string, any> }>('/api/disease-center/scoring/health')

/** 获取所有评分系统列表 */
export const getScoringSystems = () =>
  api.get<ScoringSystem[]>('/api/disease-center/scoring/list')

/** 获取评分规则详情 */
export const getScoringRule = (scoreName: string) =>
  api.get<ScoringRule>(`/api/disease-center/scoring/${scoreName}`)

/** 执行评分计算 */
export const evaluateScore = (scoreName: string, observations: Array<{
  code: string
  display_name: string
  value: number
  unit?: string
  timestamp?: string
}>) =>
  api.post<ScoringResult>('/api/disease-center/scoring/evaluate', observations, {
    params: { score_name: scoreName }
  })

/** 执行测试病例 */
export const runTestCase = (scoreName: string, testCase: TestCase) =>
  api.post<TestCaseResult>('/api/disease-center/scoring/test-case', testCase, {
    params: { score_name: scoreName }
  })

// ---- 病种管理 ----

export interface Disease {
  id: string
  code?: string
  name: string
  english_name?: string
  short_name?: string
  category_id?: string
  description?: string
  definition?: string
  diagnostic_criteria?: string
  icd10_codes?: string[]
  icd11_codes?: string[]
  local_codes?: string[]
  status?: string
  version?: string
  revision?: number
  created_at?: string
  updated_at?: string
}

/** 获取病种列表 */
export const getDiseases = (params?: {
  status?: string
  category?: string
  limit?: number
}) => api.get<Disease[]>('/api/disease-center/diseases', { params })

/** 获取病种详情 */
export const getDiseaseDetail = (diseaseId: string) =>
  api.get<Disease>(`/api/disease-center/diseases/${diseaseId}`)

/** 创建病种 */
export const createDisease = (disease: Partial<Disease>) =>
  api.post<Disease>('/api/disease-center/diseases', disease)

/** 更新病种 */
export const updateDisease = (diseaseId: string, updates: Partial<Disease>) =>
  api.put<Disease>(`/api/disease-center/diseases/${diseaseId}`, updates)

/** 删除病种 */
export const deleteDisease = (diseaseId: string) =>
  api.delete(`/api/disease-center/diseases/${diseaseId}`)

/** 提交病种审核 */
export const submitDiseaseReview = (diseaseId: string, submitterId: string) =>
  api.post(`/api/disease-center/diseases/${diseaseId}/submit-review`, null, {
    params: { submitter_id: submitterId }
  })

// ---- 病种关系 ----

export interface DiseaseRelation {
  id: string
  source_id: string
  target_id: string
  relation_type: string
  description?: string
}

/** 获取病种关系列表 */
export const getDiseaseRelations = (diseaseId: string) =>
  api.get<DiseaseRelation[]>(`/api/disease-center/diseases/${diseaseId}/relations`)

/** 创建病种关系 */
export const createDiseaseRelation = (relation: Partial<DiseaseRelation>) =>
  api.post<DiseaseRelation>('/api/disease-center/relations', relation)

/** 删除病种关系 */
export const deleteDiseaseRelation = (relationId: string) =>
  api.delete(`/api/disease-center/relations/${relationId}`)

// ---- 临床路径 ----

export interface PathwayNode {
  id: string
  type: string
  label: string
  config?: Record<string, any>
}

export interface PathwayEdge {
  id: string
  source: string
  target: string
  condition?: string
}

export interface ClinicalPathway {
  id: string
  disease_id: string
  name: string
  version: string
  nodes: PathwayNode[]
  edges: PathwayEdge[]
}

/** 获取临床路径 */
export const getPathway = (diseaseId: string) =>
  api.get<ClinicalPathway>(`/api/disease-center/diseases/${diseaseId}/pathway`)

/** 创建临床路径 */
export const createPathway = (pathway: Partial<ClinicalPathway>) =>
  api.post<ClinicalPathway>('/api/disease-center/pathways', pathway)

/** 更新临床路径 */
export const updatePathway = (diseaseId: string, updates: Partial<ClinicalPathway>) =>
  api.put<ClinicalPathway>(`/api/disease-center/diseases/${diseaseId}/pathway`, updates)

// ---- 术语编码 ----

export interface TerminologyItem {
  id: string
  standard_name: string
  english_name?: string
  abbreviation?: string
  synonyms?: string[]
  category?: string
  icd10_codes?: string[]
  icd11_codes?: string[]
  local_codes?: string[]
  snomed_code?: string
  unit?: string
  description?: string
  related_disease_ids?: string[]
  status?: string
  version?: string
  source?: string
  source_version?: string
  created_by?: string
  created_at?: string
  updated_by?: string
  updated_at?: string
  reviewed_by?: string
  published_by?: string
  published_at?: string
  revision?: number
  content_hash?: string
}

export interface TerminologyCategory {
  id?: string
  name: string
  count: number
}

/** 获取术语列表 */
export const getTerminologies = (params?: {
  category?: string
  status?: string
  keyword?: string
  limit?: number
}) => api.get<TerminologyItem[]>('/api/disease-center/terminology', { params })

/** 获取术语分类列表 */
export const getTerminologyCategories = () =>
  api.get<TerminologyCategory[]>('/api/disease-center/terminology/categories')

/** 获取术语详情 */
export const getTerminologyDetail = (termId: string) =>
  api.get<TerminologyItem>(`/api/disease-center/terminology/${termId}`)

/** 创建术语 */
export const createTerminology = (terminology: Partial<TerminologyItem>) =>
  api.post<TerminologyItem>('/api/disease-center/terminology', terminology)

/** 更新术语 */
export const updateTerminology = (termId: string, updates: Partial<TerminologyItem>) =>
  api.put<TerminologyItem>(`/api/disease-center/terminology/${termId}`, updates)

/** 删除术语 */
export const deleteTerminology = (termId: string) =>
  api.delete(`/api/disease-center/terminology/${termId}`)

/** 批量导入术语 */
export const importTerminologyBatch = (terms: Array<Partial<TerminologyItem>>) =>
  api.post<{ total: number; success: number; failed: number }>('/api/disease-center/terminology/import', terms)

/** 搜索术语 (别名，兼容旧代码) */
export const searchTerminology = (params?: {
  q?: string
  category?: string
  status?: string
  limit?: number
}) => api.get<TerminologyItem[]>('/api/disease-center/terminology', { params })

// ---- 表型规则 ----

export interface LogicNode {
  id: string
  operator: string
  inputs: string[]
  output: string
}

export interface OutputAction {
  type: string
  target: string
  params?: Record<string, any>
}

export interface PhenotypeRule {
  id: string
  name: string
  disease_id?: string
  disease_name?: string
  phenotype_type?: string
  logic_nodes?: LogicNode[]
  output_actions?: OutputAction[]
  description?: string
  status?: string
  version?: string
  dsl?: {
    operator: 'ALL' | 'ANY' | 'NOT'
    conditions: Array<{
      type: string
      field: string
      operator: string
      value: any
      time_window?: string
    }>
  }
  created_at?: string
  updated_at?: string
}

/** 获取表型规则列表 */
export const getPhenotypeRules = (params?: {
  disease_id?: string
  status?: string
  phenotype_type?: string
  limit?: number
}) => api.get<PhenotypeRule[]>('/api/disease-center/phenotypes', { params })

/** 获取表型规则统计 */
export const getPhenotypeStats = () =>
  api.get<{ total: number; by_status: Record<string, number>; by_type: Record<string, number> }>('/api/disease-center/phenotypes/stats')

/** 获取表型规则详情 */
export const getPhenotypeRule = (phenotypeId: string) =>
  api.get<PhenotypeRule>(`/api/disease-center/phenotypes/${phenotypeId}`)

/** 创建表型规则 */
export const createPhenotypeRule = (phenotype: Partial<PhenotypeRule>) =>
  api.post<PhenotypeRule>('/api/disease-center/phenotypes', phenotype)

/** 更新表型规则 */
export const updatePhenotypeRule = (phenotypeId: string, updates: Partial<PhenotypeRule>) =>
  api.put<PhenotypeRule>(`/api/disease-center/phenotypes/${phenotypeId}`, updates)

/** 删除表型规则 */
export const deletePhenotypeRule = (phenotypeId: string) =>
  api.delete(`/api/disease-center/phenotypes/${phenotypeId}`)

/** 验证表型规则逻辑 */
export const validatePhenotypeRule = (phenotype: Partial<PhenotypeRule>) =>
  api.post<{ valid: boolean; errors: string[]; warnings: string[] }>('/api/disease-center/phenotypes/validate', phenotype)

// ---- 审核管理 ----

export interface ReviewTask {
  id: string
  resource_type: string
  resource_id: string
  resource_version: string
  type?: string
  title?: string
  description?: string
  status: string
  submitter_id: string
  submitted_by?: string
  submitted_at: string
  reviewer_id?: string
  reviewed_at?: string
  review_comment?: string
  version_from?: string
  version_to?: string
  impact?: string
  changes?: Array<{ type: string; text: string }>
}

/** 获取审核列表 */
export const getReviews = (params?: {
  status?: string
}) => api.get<ReviewTask[]>('/api/disease-center/reviews', { params })

/** 获取审核详情 */
export const getReviewDetail = (reviewId: string) =>
  api.get<ReviewTask>(`/api/disease-center/reviews/${reviewId}`)

/** 通过审核 */
export const approveReview = (reviewId: string, reviewerId: string) =>
  api.post<ReviewTask>(`/api/disease-center/reviews/${reviewId}/approve`, null, {
    params: { reviewer_id: reviewerId }
  })

/** 拒绝审核 */
export const rejectReview = (reviewId: string, reviewerId: string, comment: string) =>
  api.post<ReviewTask>(`/api/disease-center/reviews/${reviewId}/reject`, null, {
    params: { reviewer_id: reviewerId, comment }
  })

// ---- 离线包管理 ----

export interface OfflinePackage {
  id: string
  name: string
  type?: string
  package_type?: string
  version?: string
  description?: string
  target_device?: string
  status: string
  icd_version?: string
  guide_version?: string
  model_version?: string
  prompt_version?: string
  sha256?: string
  size?: string
  file_size_mb?: number
  file_size?: number
  checksum?: string
  uploaded_at?: string
  build_started_at?: string
  build_completed_at?: string
  published_at?: string
  created_at?: string
  updated_at?: string
}

/** 获取离线包列表 */
export const getOfflinePackages = (params?: {
  status?: string
  target_device?: string
  limit?: number
}) => api.get<OfflinePackage[]>('/api/disease-center/offline-packages', { params })

/** 获取离线包统计 */
export const getOfflinePackageStats = () =>
  api.get<{ total: number; by_status: Record<string, number>; total_size_mb: number }>('/api/disease-center/offline-packages/stats')

/** 获取离线包详情 */
export const getOfflinePackageDetail = (packageId: string) =>
  api.get<OfflinePackage>(`/api/disease-center/offline-packages/${packageId}`)

/** 创建离线包 */
export const createOfflinePackage = (pkg: Partial<OfflinePackage>) =>
  api.post<OfflinePackage>('/api/disease-center/offline-packages', pkg)

/** 构建离线包 */
export const buildOfflinePackage = (packageId: string) =>
  api.post<OfflinePackage>(`/api/disease-center/offline-packages/${packageId}/build`)

/** 发布离线包 */
export const publishOfflinePackage = (packageId: string) =>
  api.post<OfflinePackage>(`/api/disease-center/offline-packages/${packageId}/publish`)

/** 删除离线包 */
export const deleteOfflinePackage = (packageId: string) =>
  api.delete(`/api/disease-center/offline-packages/${packageId}`)

// ---- 质量监控 ----

export interface QualityMetrics {
  total_rules: number
  validated_rules: number
  coverage_rate: number
  consistency_score: number
  terminology_mapping_rate: number
  pathway_integrity: number
  overall_score: number
}

export interface QualityIssue {
  id: string
  issue_type: string
  type?: string
  severity: string
  title?: string
  description: string
  affected_resource_id?: string
  affected_resource_type?: string
  affected_count?: number
  detected_at?: string
  status?: string
}

export interface QualitySnapshot {
  id: string
  resource_type?: string
  resource_id?: string
  resource_version?: string
  completeness?: number
  terminology_consistency?: number
  coding_quality?: number
  source_coverage?: number
  test_pass_rate?: number
  false_positive_rate?: number
  false_negative_rate?: number
  precision?: number
  recall?: number
  specificity?: number
  sensitivity?: number
  validation_sample_size?: number
  calculated_at?: string
  calculation_version?: string
  issues?: QualityIssue[]
}

/** 获取质量快照列表 */
export const getQualitySnapshots = (params?: {
  disease_id?: string
  limit?: number
}) => api.get<QualitySnapshot[]>('/api/disease-center/quality/snapshots', { params })

/** 获取质量快照详情 */
export const getQualitySnapshotDetail = (snapshotId: string) =>
  api.get<QualitySnapshot>(`/api/disease-center/quality/snapshots/${snapshotId}`)

/** 获取质量摘要 */
export const getQualitySummary = (diseaseId: string) =>
  api.get<{
    disease_id: string
    total_snapshots: number
    latest_score: number | null
    issues_count: number
    metrics: QualityMetrics
  }>(`/api/disease-center/quality/summary/${diseaseId}`)

/** 获取质量趋势 */
export const getQualityTrend = (diseaseId: string, days?: number) =>
  api.get<Array<{ date: string; score: number; issues_count: number }>>(
    `/api/disease-center/quality/trend/${diseaseId}`,
    { params: { days } }
  )

/** 运行质量检查 */
export const runQualityCheck = (diseaseId: string) =>
  api.post<{
    disease_id: string
    score: number
    issues: QualityIssue[]
    passed: boolean
  }>(`/api/disease-center/quality/check/${diseaseId}`)

/** 获取质量问题列表 (兼容旧代码，从快照中提取 issues) */
export const getQualityIssues = async (params?: {
  disease_id?: string
  limit?: number
}): Promise<{ data: QualityIssue[] }> => {
  const { data: snapshots } = await getQualitySnapshots(params)
  const allIssues: QualityIssue[] = []
  if (Array.isArray(snapshots)) {
    for (const snap of snapshots) {
      if (snap.issues && Array.isArray(snap.issues)) {
        allIssues.push(...snap.issues)
      }
    }
  }
  return { data: allIssues }
}

// ---- AI 咨询 ----

export interface AiProposal {
  id: string
  disease_id: string
  proposal_type: string
  title: string
  content: string
  context: Record<string, any>
  confidence: number
  model_id: string
  model_version: string
  status: string
  reviewer_id?: string
  reviewed_at?: string
  rejection_reason?: string
  created_at?: string
  updated_at?: string
}

/** 获取 AI 提案列表 */
export const getAiProposals = (params?: {
  disease_id?: string
  proposal_type?: string
  status?: string
  limit?: number
}) => api.get<AiProposal[]>('/api/disease-center/ai/proposals', { params })

/** 获取 AI 咨询统计 */
export const getAiStats = () =>
  api.get<{
    total: number
    by_status: Record<string, number>
    by_type: Record<string, number>
    average_confidence: number
  }>('/api/disease-center/ai/stats')

/** 获取 AI 提案详情 */
export const getAiProposalDetail = (proposalId: string) =>
  api.get<AiProposal>(`/api/disease-center/ai/proposals/${proposalId}`)

/** 创建 AI 提案 */
export const createAiProposal = (proposal: {
  disease_id: string
  proposal_type: string
  title: string
  content: string
  context: Record<string, any>
  confidence: number
  model_id: string
  model_version: string
}) => api.post<AiProposal>('/api/disease-center/ai/proposals', proposal)

/** 通过 AI 提案 */
export const approveAiProposal = (proposalId: string, reviewerId: string) =>
  api.post<AiProposal>(`/api/disease-center/ai/proposals/${proposalId}/approve`, null, {
    params: { reviewer_id: reviewerId }
  })

/** 拒绝 AI 提案 */
export const rejectAiProposal = (proposalId: string, reviewerId: string, reason: string) =>
  api.post<AiProposal>(`/api/disease-center/ai/proposals/${proposalId}/reject`, null, {
    params: { reviewer_id: reviewerId, reason }
  })

// ---- 审计日志 ----

export interface AuditEvent {
  id: string
  action: string
  resource_type: string
  resource_id: string
  resource_version?: string
  before?: Record<string, any>
  after?: Record<string, any>
  result: string
  error_message?: string
  timestamp: string
}

/** 获取审计事件列表 */
export const getAuditEvents = (params?: {
  resource_type?: string
  resource_id?: string
  limit?: number
}) => api.get<AuditEvent[]>('/api/disease-center/audit', { params })
