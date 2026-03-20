const SCENARIO_GROUP_LABELS: Record<string, string> = {
  respiratory_failure: '呼吸衰竭',
  postoperative_general: '术后综合管理',
  post_liver_transplant: '肝移植术后',
  post_cardiac_surgery: '心外术后',
  drug_interactions: '药物相互作用',
  device_complications: '装置并发症',
  nutrition_endocrine: '营养与内分泌',
  infection_sepsis: '感染与脓毒症',
  renal_metabolic: '肾脏与代谢',
  rare_critical: '罕见危重症',
  post_neurosurgery: '神经外科术后',
  hemodynamic_instability: '血流动力学不稳定',
  hematology_transfusion: '血液与输血',
  neuro_critical: '神经重症',
}

const COMPOSITE_GROUP_LABELS: Record<string, string> = {
  sepsis_group: '脓毒症主题',
  bleeding_group: '出血主题',
  respiratory_group: '呼吸主题',
}

const COMPOSITE_CHAIN_LABELS: Record<string, string> = {
  shock_chain: '休克链',
  respiratory_failure_chain: '呼衰链',
  sepsis_progression_chain: '脓毒症进展链',
  bleeding_chain: '失血链',
  multi_organ_progression: '多器官进展',
}

export function formatScenarioGroupLabel(value: any) {
  const key = String(value || '').trim()
  if (!key) return '未分组'
  return SCENARIO_GROUP_LABELS[key] || key.replace(/_/g, ' ')
}

export function formatCompositeGroupLabel(value: any) {
  const key = String(value || '').trim()
  if (!key) return '未分组'
  return COMPOSITE_GROUP_LABELS[key] || key.replace(/_/g, ' ')
}

export function formatCompositeChainLabel(value: any) {
  const key = String(value || '').trim()
  if (!key) return '未定义链路'
  return COMPOSITE_CHAIN_LABELS[key] || key.replace(/_/g, ' ')
}
