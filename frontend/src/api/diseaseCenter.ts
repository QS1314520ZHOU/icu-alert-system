/**
 * 病种中心 API 模块
 * 代理规则核心服务，提供术语编码、评分规则等功能
 */
import api from './index'

// ---- 评分系统 ----

export interface ScoringSystem {
  id: string
  name: string
  description?: string
  variants?: Array<{
    id: string
    name: string
    version?: string
  }>
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

/** 获取所有评分系统列表 */
export const getScoringSystems = () =>
  api.get<{ systems: ScoringSystem[] }>('/api/disease-center/scoring/systems')

/** 获取评分规则详情 */
export const getScoringRule = (ruleId: string) =>
  api.get<ScoringRule>(`/api/disease-center/scoring/rules/${ruleId}`)

/** 执行评分计算 */
export const evaluateScore = (payload: {
  patient_id: string
  score_system: string
  score_variant?: string
  inputs?: Record<string, any>
}) => api.post<ScoringResult>('/api/disease-center/scoring/evaluate', payload)

/** 执行测试病例 */
export const runTestCase = (payload: {
  rule_id: string
  test_case: TestCase
}) => api.post<TestCaseResult>('/api/disease-center/scoring/test-case', payload)

// ---- 术语编码 ----

export interface TerminologyItem {
  id: string
  name: string
  icd10?: string
  icd11?: string
  category?: string
  synonyms?: string[]
  related_diseases?: Array<{
    id: string
    name: string
  }>
  usage_count?: number
  status?: string
  updated_at?: string
}

export interface TerminologyCategory {
  id: string
  name: string
  count: number
}

/** 搜索术语 */
export const searchTerminology = (params: {
  q: string
  category?: string
  limit?: number
}) => api.get<{ items: TerminologyItem[] }>('/api/disease-center/terminology/search', { params })

/** 获取术语分类列表 */
export const getTerminologyCategories = () =>
  api.get<{ categories: TerminologyCategory[] }>('/api/disease-center/terminology/categories')

/** 获取术语详情 */
export const getTerminologyDetail = (termId: string) =>
  api.get<TerminologyItem>(`/api/disease-center/terminology/${termId}`)

// ---- 病种 ----

export interface Disease {
  id: string
  name: string
  icd10?: string
  icd11?: string
  category?: string
  status?: string
  version?: string
  description?: string
  synonyms?: string[]
  related_scores?: Array<{
    id: string
    name: string
  }>
  related_rules?: Array<{
    id: string
    name: string
  }>
  updated_at?: string
}

/** 获取病种列表 */
export const getDiseases = (params?: {
  category?: string
  status?: string
  limit?: number
}) => api.get<{ diseases: Disease[] }>('/api/disease-center/diseases', { params })

/** 获取病种详情 */
export const getDiseaseDetail = (diseaseId: string) =>
  api.get<Disease>(`/api/disease-center/diseases/${diseaseId}`)

// ---- 表型规则 ----

export interface PhenotypeRule {
  id: string
  name: string
  disease_id?: string
  disease_name?: string
  version?: string
  status?: string
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
  description?: string
  updated_at?: string
}

/** 获取表型规则列表 */
export const getPhenotypeRules = (params?: {
  disease_id?: string
  limit?: number
}) => api.get<{ rules: PhenotypeRule[] }>('/api/disease-center/phenotypes', { params })

/** 获取表型规则详情 */
export const getPhenotypeRule = (ruleId: string) =>
  api.get<PhenotypeRule>(`/api/disease-center/phenotypes/${ruleId}`)

// ---- 健康检查 ----

export const checkRuleCoreHealth = () =>
  api.get<{ rule_core: { status: string } }>('/api/disease-center/health')
