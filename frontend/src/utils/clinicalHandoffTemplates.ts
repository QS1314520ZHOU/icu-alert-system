export type ClinicalSection = {
  key: string
  code?: string
  title: string
  text: string
  items?: string[]
  mode?: 'text' | 'list' | 'chips'
}

const TECHNICAL_FIELD_RE = /^(patient_id|patientId|id|_id|role|source|data_source|generated_at|created_at|updated_at|code)\s*[:：]/i
const SMART_PATIENT_FIELDS = {
  name: ['name', 'hisName'],
  bed: ['hisBed', 'bed'],
  sex: ['hisSex'],
  age: ['hisAge'],
  hisPid: ['hisPid'],
  dept: ['hisDept'],
  deptCode: ['deptCode'],
  diagnosis: ['clinicalDiagnosis', 'admissionDiagnosis', 'diagnosis', 'hisDiagnose', 'hisDiagnosis'],
} as const

function textValue(value: any): string {
  if (value == null) return ''
  if (Array.isArray(value)) return value.map(textValue).filter(Boolean).join('\n')
  if (typeof value === 'object') {
    for (const key of ['text', 'summary', 'content', 'description', 'detail', 'value', 'label', 'handoff_text', 'note']) {
      const text = textValue(value?.[key])
      if (text) return text
    }
    return ''
  }
  return String(value).trim()
}

export function formatClinicalText(value: any): string {
  return textValue(value)
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !TECHNICAL_FIELD_RE.test(line))
    .map((line) => line.replace(/^(handoff_text|summary|story|content)\s*[:：]\s*/i, ''))
    .filter(Boolean)
    .join('\n')
}

export function firstClinicalText(row: any, keys: readonly string[], fallback = '') {
  for (const key of keys) {
    const text = formatClinicalText(row?.[key])
    if (text) return text
  }
  return fallback
}

export function listClinicalText(value: any): string[] {
  if (Array.isArray(value)) return value.map(formatClinicalText).filter(Boolean)
  const text = formatClinicalText(value)
  return text ? text.split(/[；;\n]/).map((item) => item.trim()).filter(Boolean) : []
}

function joinParts(values: any[], fallback = '') {
  const text = values.map(formatClinicalText).filter(Boolean).join('；')
  return text || fallback
}

function normalizeGender(value: any) {
  const raw = String(value ?? '').trim().toLowerCase()
  if (['m', 'male', 'man', '1', '男', '男性'].includes(raw)) return '男'
  if (['f', 'female', 'woman', '2', '女', '女性'].includes(raw)) return '女'
  return String(value ?? '').trim()
}

function normalizeAge(value: any) {
  return String(value ?? '').trim().replace(/岁/g, '')
}

function smartPatientText(patient: any, field: keyof typeof SMART_PATIENT_FIELDS) {
  if (!patient || typeof patient !== 'object') return ''
  return firstClinicalText(patient, SMART_PATIENT_FIELDS[field])
}

function pickSection(data: any, keys: string[]) {
  if (!data || typeof data !== 'object') return ''
  for (const key of keys) {
    const text = formatClinicalText(data?.[key])
    if (text) return text
  }
  return ''
}

function lineContaining(text: string, keywords: string[]) {
  const lowerKeywords = keywords.map((item) => item.toLowerCase())
  return text
    .split(/\r?\n|。|；/)
    .map((line) => line.trim())
    .find((line) => {
      const lower = line.toLowerCase()
      return lowerKeywords.some((key) => lower.includes(key))
    }) || ''
}

function patientDiagnosis(patient: any) {
  return smartPatientText(patient, 'diagnosis') || '诊断待补充'
}

function patientIdentity(patient: any, context: any) {
  const age = normalizeAge(smartPatientText(patient, 'age'))
  return joinParts(
    [
      context?.handoffActor ? `交班：${context.handoffActor}` : '',
      context?.receiver ? `接班：${context.receiver}` : '',
      smartPatientText(patient, 'name'),
      normalizeGender(smartPatientText(patient, 'sex')),
      age ? `${age}岁` : '',
      smartPatientText(patient, 'bed') ? `${smartPatientText(patient, 'bed')}床` : '',
      smartPatientText(patient, 'hisPid') ? `住院号${smartPatientText(patient, 'hisPid')}` : '',
      smartPatientText(patient, 'dept'),
      patientDiagnosis(patient),
    ],
    '患者身份信息待补充',
  )
}

export function buildIsbarSections(patient: any = {}, handoff: any = {}, context: any = {}): ClinicalSection[] {
  const data = handoff?.handoff || handoff || {}
  const clean = formatClinicalText(data)
  const alerts = Array.isArray(context?.alerts) ? context.alerts : []
  const actions = listClinicalText(data?.action_list || data?.actions || data?.recommendations)
  const awareness = listClinicalText(data?.situation_awareness || data?.awareness)
  const alertLine = alerts
    .slice(0, 3)
    .map((item: any) => firstClinicalText(item, ['name', 'title', 'alert_name', 'alert_type', 'message']))
    .filter(Boolean)
    .join('；')

  return [
    {
      key: 'identity',
      code: 'I',
      title: '识别 / 身份确认',
      text: pickSection(data, ['identity', 'identify', 'identification', 'i']) || patientIdentity(patient, context),
      mode: 'text',
    },
    {
      key: 'situation',
      code: 'S',
      title: '现状 / 当前主要问题',
      text:
        pickSection(data, ['situation', 's', 'current_status', 'patient_summary']) ||
        lineContaining(clean, ['现状', '生命体征', '血压', '氧合', '呼吸机', '主诉']) ||
        '当前现状暂无结构化摘要，请接班后优先复核心率、血压、氧合、呼吸支持和最突出的临床问题。',
      mode: 'text',
    },
    {
      key: 'background',
      code: 'B',
      title: '背景 / 病史与已处理',
      text:
        pickSection(data, ['background', 'b', 'history', 'past_history']) ||
        joinParts([patientDiagnosis(patient), lineContaining(clean, ['既往', '治疗', '检查', '过敏', '手术'])], '背景资料待补充'),
      mode: 'text',
    },
    {
      key: 'assessment',
      code: 'A',
      title: '评估 / 系统问题与风险',
      text:
        pickSection(data, ['assessment', 'a', 'evaluation']) ||
        joinParts([lineContaining(clean, ['评估', 'SOFA', 'APACHE', '循环', '呼吸', '感染', '肾']), alertLine], '暂无高危未闭环事项，仍需按 ICU 系统评估复核。'),
      items: awareness,
      mode: awareness.length ? 'list' : 'text',
    },
    {
      key: 'recommendation',
      code: 'R',
      title: '建议 / 下一班重点',
      text:
        pickSection(data, ['recommendation', 'r', 'plan', 'next_steps']) ||
        (actions.length ? '' : '建议复核未闭环告警、待执行医嘱、复查指标、家属沟通事项和夜间风险预案。'),
      items: actions,
      mode: actions.length ? 'list' : 'text',
    },
  ]
}

export function buildIcuRoundingSections(patient: any = {}, summary: any = {}, context: any = {}): ClinicalSection[] {
  const text = formatClinicalText(summary)
  const systems = summary?.systems && typeof summary.systems === 'object' ? summary.systems : {}
  const priorities = Array.isArray(summary?.clinical_priorities) ? summary.clinical_priorities : []
  const tasks = Array.isArray(summary?.completion?.tasks) ? summary.completion.tasks : []
  const systemText = (key: string, keywords: string[], fallback: string) => {
    const rows = Array.isArray(systems[key]) ? systems[key] : []
    const fromRows = rows.map((item: any) => formatClinicalText(item?.title || item?.summary || item?.type)).filter(Boolean).slice(0, 3).join('；')
    return fromRows || lineContaining(text, keywords) || fallback
  }
  const taskText = tasks.map((item: any) => formatClinicalText(item?.title || item?.action)).filter(Boolean).slice(0, 4).join('；')
  const priorityText = priorities.map((item: any) => formatClinicalText(item?.title)).filter(Boolean).slice(0, 4).join('；')
  const age = normalizeAge(smartPatientText(patient, 'age'))

  return [
    { key: 'basic', title: '基本情况回顾', text: joinParts([smartPatientText(patient, 'bed') ? `${smartPatientText(patient, 'bed')}床` : '', smartPatientText(patient, 'name'), normalizeGender(smartPatientText(patient, 'sex')), age ? `${age}岁` : '', smartPatientText(patient, 'hisPid') ? `住院号${smartPatientText(patient, 'hisPid')}` : '', patientDiagnosis(patient), context?.icuDays ? `ICU第${context.icuDays}天` : ''], '核对患者身份、入科诊断和关键诊治经过。') },
    { key: 'changes', title: '24小时变化', text: lineContaining(text, ['24', '变化', '事件', '抢救', '转运']) || priorityText || '回顾过去24小时病情波动、特殊事件、抢救、操作、转运和关键转折点。' },
    { key: 'vitals', title: '生命体征与监测', text: lineContaining(text, ['生命体征', '体温', '心率', '血压', 'MAP', 'SpO2', 'CVP', 'PiCCO']) || '复核心率心律、动脉压/MAP、呼吸频率、SpO2、体温、CVP及必要的有创血流动力学参数。' },
    { key: 'neuro', title: '神经系统', text: systemText('neuro', ['GCS', 'RASS', 'CPOT', '瞳孔', 'CAM', '谵妄', '镇静'], '评估意识、GCS/RASS/CPOT、瞳孔、肢体活动、CAM-ICU及镇痛镇静目标。') },
    { key: 'circulation', title: '循环系统', text: systemText('circulation', ['循环', '血压', '乳酸', '升压', '心超', '出入量'], '评估血压/MAP、外周灌注、血管活性药、出入量、乳酸及心脏超声结果。') },
    { key: 'respiratory', title: '呼吸系统', text: systemText('respiratory', ['呼吸', '氧合', 'PEEP', 'FiO2', '血气', '脱机', '气道'], '评估呼吸机模式参数、氧合指数、血气、分泌物、人工气道和脱机条件。') },
    { key: 'gi', title: '消化与营养', text: systemText('nutrition', ['营养', '胃残余', '肠鸣', '排便', '肝功能'], '评估腹部体征、肠内/肠外营养、目标达成、胃残余、排便和应激性溃疡预防。') },
    { key: 'renal', title: '泌尿与肾脏', text: systemText('renal', ['尿量', '肌酐', '尿素氮', 'CRRT', '电解质'], '评估小时尿量、24小时尿量、肌酐、尿素氮、电解质、容量状态和CRRT需求。') },
    { key: 'coagulation', title: '血液与凝血', text: systemText('coagulation', ['血红蛋白', '血小板', '凝血', 'PT', 'APTT', 'INR', 'D-二聚体'], '评估血红蛋白、血小板、凝血、出血/血栓倾向、抗凝和DVT预防。') },
    { key: 'infection', title: '感染', text: systemText('infection', ['感染', '体温', '白细胞', 'CRP', 'PCT', '培养', '抗生素'], '评估体温曲线、炎症指标、培养、抗菌药疗程/降阶梯、感染源控制和院感风险。') },
    { key: 'metabolic', title: '内分泌与代谢', text: lineContaining(text, ['血糖', '钠', '钾', '钙', '镁', '磷', '酸碱']) || '复核血糖、电解质、酸碱平衡及必要的内分泌功能。' },
    { key: 'skin_lines', title: '皮肤与导管', text: systemText('others', ['皮肤', '压疮', '导管', '气管插管', '中心静脉', '尿管', '引流'], '评估皮肤完整性、Braden风险、各类导管位置通畅性、感染征象和拔除可能。') },
    { key: 'tests_drugs', title: '辅助检查与用药', text: lineContaining(text, ['检查', '影像', '血气', '用药', '抗凝', '镇静', '抗生素']) || '回顾血常规、生化、血气、凝血、感染指标、影像、微生物和当前所有关键用药。' },
    { key: 'plan', title: '问题列表与诊疗计划', text: taskText || priorityText || '列出活动性问题并按优先级制定处理计划，明确治疗目标和复评时间。' },
    { key: 'fast_hugs', title: 'FAST HUGS IN BED', text: '核对喂养、镇痛、镇静、血栓预防、床头抬高、溃疡预防、血糖控制、自主呼吸试验、肠道、管路和降阶梯。' },
    { key: 'communication', title: '转出/升级、家属沟通与MDT', text: lineContaining(text, ['转出', '升级', 'ECMO', 'CRRT', '家属', '会诊', 'MDT']) || '评估转出ICU或升级治疗需求，明确家属沟通、知情同意和多学科协作事项。' },
  ]
}
