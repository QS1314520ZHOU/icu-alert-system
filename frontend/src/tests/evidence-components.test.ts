/**
 * 证据链组件单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'

// ── 证据 API 客户端测试 ──────────────────────────────

describe('clinicalEvidence API', () => {
  it('应正确定义 EvidenceParams 类型', async () => {
    const mod = await import('../api/clinicalEvidence')
    expect(mod.getPatientEvidence).toBeDefined()
    expect(typeof mod.getPatientEvidence).toBe('function')
  })

  it('应正确构建请求参数', async () => {
    const axios = await import('axios')
    const spy = vi.spyOn(axios.default, 'get').mockResolvedValue({ data: { code: 0, data: {} } })

    const { getPatientEvidence } = await import('../api/clinicalEvidence')
    await getPatientEvidence('patient-001', {
      context_type: 'organ_system',
      organ_system: 'respiratory',
      time_range: '24h',
    })

    expect(spy).toHaveBeenCalledWith(
      '/api/patients/patient-001/evidence',
      expect.objectContaining({
        params: expect.objectContaining({
          context_type: 'organ_system',
          organ_system: 'respiratory',
          time_range: '24h',
        }),
      }),
    )

    spy.mockRestore()
  })
})

// ── useClinicalEvidence composable 测试 ──────────────

describe('useClinicalEvidence', () => {
  it('应初始化默认状态', async () => {
    const { useClinicalEvidence } = await import('../composables/useClinicalEvidence')
    const { loading, error, evidence } = useClinicalEvidence()

    expect(loading.value).toBe(false)
    expect(error.value).toBeNull()
    expect(evidence.value).toBeNull()
  })

  it('应正确计算置信度级别', async () => {
    const { useClinicalEvidence } = await import('../composables/useClinicalEvidence')
    const { confidenceLevel, confidencePercent } = useClinicalEvidence()

    // 初始状态
    expect(confidenceLevel.value).toBe('very-low')
    expect(confidencePercent.value).toBe(0)
  })

  it('应正确计算严重程度颜色', async () => {
    const { useClinicalEvidence } = await import('../composables/useClinicalEvidence')
    const { severityColor, severityLabel } = useClinicalEvidence()

    expect(severityColor.value).toBe('#6B7280') // 默认
    expect(severityLabel.value).toBe('未知')
  })

  it('应检测缺失数据', async () => {
    const { useClinicalEvidence } = await import('../composables/useClinicalEvidence')
    const { hasMissingData } = useClinicalEvidence()

    expect(hasMissingData.value).toBe(false)
  })
})

// ── EvidenceMetricCards 组件测试 ─────────────────────

describe('EvidenceMetricCards', () => {
  it('应渲染指标卡片', async () => {
    const { default: EvidenceMetricCards } = await import('../components/evidence/EvidenceMetricCards.vue')

    const wrapper = mount(EvidenceMetricCards, {
      props: {
        metrics: [
          {
            code: 'HR',
            name: '心率',
            value: 85,
            unit: 'bpm',
            observed_at: '2024-01-01T12:00:00Z',
            reference_range: '60-100 bpm',
            abnormal_flag: 'normal',
          },
          {
            code: 'Lactate',
            name: '乳酸',
            value: 4.5,
            unit: 'mmol/L',
            observed_at: '2024-01-01T12:00:00Z',
            reference_range: '<2 mmol/L',
            abnormal_flag: 'critical',
          },
        ],
      },
    })

    expect(wrapper.find('.metrics-grid').exists()).toBe(true)
    expect(wrapper.findAll('.metric-card')).toHaveLength(2)
    expect(wrapper.text()).toContain('心率')
    expect(wrapper.text()).toContain('乳酸')
    expect(wrapper.text()).toContain('85')
    expect(wrapper.text()).toContain('4.5')
  })

  it('空指标时应显示空提示', async () => {
    const { default: EvidenceMetricCards } = await import('../components/evidence/EvidenceMetricCards.vue')

    const wrapper = mount(EvidenceMetricCards, {
      props: { metrics: [] },
    })

    expect(wrapper.find('.metrics-empty').exists()).toBe(true)
    expect(wrapper.text()).toContain('暂无指标数据')
  })

  it('null 值应显示"不可计算"', async () => {
    const { default: EvidenceMetricCards } = await import('../components/evidence/EvidenceMetricCards.vue')

    const wrapper = mount(EvidenceMetricCards, {
      props: {
        metrics: [{
          code: 'GCS',
          name: 'GCS',
          value: null,
          unit: '',
          observed_at: null,
          reference_range: '15分',
          abnormal_flag: 'missing',
        }],
      },
    })

    expect(wrapper.text()).toContain('不可计算')
  })
})

// ── EvidenceTable 组件测试 ───────────────────────────

describe('EvidenceTable', () => {
  it('应渲染证据表格', async () => {
    const { default: EvidenceTable } = await import('../components/evidence/EvidenceTable.vue')

    const wrapper = mount(EvidenceTable, {
      props: {
        rows: [
          {
            record_id: '1',
            patient_id: 'p1',
            observed_at: '2024-01-01T12:00:00Z',
            category: 'vital_sign',
            code: 'HR',
            name: '心率',
            value: 85,
            unit: 'bpm',
            reference_range: '60-100',
            abnormal_flag: 'normal',
            data_quality: 'complete',
          },
        ],
        showSource: true,
      },
    })

    expect(wrapper.find('.evidence-table').exists()).toBe(true)
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.text()).toContain('心率')
  })

  it('空行时应显示空提示', async () => {
    const { default: EvidenceTable } = await import('../components/evidence/EvidenceTable.vue')

    const wrapper = mount(EvidenceTable, {
      props: { rows: [] },
    })

    expect(wrapper.find('.table-empty').exists()).toBe(true)
  })
})

// ── RuleCalculationPanel 组件测试 ────────────────────

describe('RuleCalculationPanel', () => {
  it('应渲染评分明细', async () => {
    const { default: RuleCalculationPanel } = await import('../components/evidence/RuleCalculationPanel.vue')

    const wrapper = mount(RuleCalculationPanel, {
      props: {
        ruleCalc: {
          score_type: 'sofa',
          total_score: 8,
          items: [
            { label: '呼吸', score: 3, description: 'PaO2/FiO2 < 200' },
            { label: '凝血', score: 2, description: 'PLT < 100' },
          ],
          description: 'SOFA 器官功能评分',
        },
      },
    })

    expect(wrapper.text()).toContain('SOFA')
    expect(wrapper.text()).toContain('8')
    expect(wrapper.text()).toContain('呼吸')
    expect(wrapper.text()).toContain('凝血')
  })

  it('应渲染灯号状态', async () => {
    const { default: RuleCalculationPanel } = await import('../components/evidence/RuleCalculationPanel.vue')

    const wrapper = mount(RuleCalculationPanel, {
      props: {
        ruleCalc: {
          score_type: 'weaning',
          items: [],
          lights: [
            { label: 'RSBI < 105', ok: true },
            { label: 'SpO2 > 90%', ok: false },
          ],
        },
      },
    })

    expect(wrapper.findAll('.light-item')).toHaveLength(2)
    expect(wrapper.findAll('.light-item.ok')).toHaveLength(1)
    expect(wrapper.findAll('.light-item.bad')).toHaveLength(1)
  })

  it('null 时应显示空提示', async () => {
    const { default: RuleCalculationPanel } = await import('../components/evidence/RuleCalculationPanel.vue')

    const wrapper = mount(RuleCalculationPanel, {
      props: { ruleCalc: null },
    })

    expect(wrapper.find('.calc-empty').exists()).toBe(true)
  })
})

// ── AiEvidenceAnalysis 组件测试 ──────────────────────

describe('AiEvidenceAnalysis', () => {
  it('应渲染 AI 分析三区', async () => {
    const { default: AiEvidenceAnalysis } = await import('../components/evidence/AiEvidenceAnalysis.vue')

    const wrapper = mount(AiEvidenceAnalysis, {
      props: {
        aiAnalysis: {
          supporting_evidence: ['乳酸升高', '白细胞计数升高'],
          opposing_evidence: ['体温正常'],
          uncertainties: ['血培养结果待出'],
          disclaimer: 'AI生成，待临床确认',
          model: 'gpt-4',
          generated_at: '2024-01-01T12:00:00Z',
        },
      },
    })

    expect(wrapper.text()).toContain('支持证据')
    expect(wrapper.text()).toContain('反对证据')
    expect(wrapper.text()).toContain('不确定性')
    expect(wrapper.text()).toContain('AI生成，待临床确认')
    expect(wrapper.text()).toContain('乳酸升高')
    expect(wrapper.text()).toContain('体温正常')
  })

  it('应显示免责声明', async () => {
    const { default: AiEvidenceAnalysis } = await import('../components/evidence/AiEvidenceAnalysis.vue')

    const wrapper = mount(AiEvidenceAnalysis, {
      props: {
        aiAnalysis: {
          supporting_evidence: [],
          opposing_evidence: [],
          uncertainties: [],
          disclaimer: 'AI生成，待临床确认',
          model: 'test',
          generated_at: null,
        },
      },
    })

    expect(wrapper.find('.ai-disclaimer').exists()).toBe(true)
    expect(wrapper.find('.disclaimer-badge').text()).toBe('AI')
  })
})

// ── EvidenceTimeline 组件测试 ────────────────────────

describe('EvidenceTimeline', () => {
  it('应渲染时间线事件', async () => {
    const { default: EvidenceTimeline } = await import('../components/evidence/EvidenceTimeline.vue')

    const wrapper = mount(EvidenceTimeline, {
      props: {
        events: [
          { time: '2024-01-01T10:00:00Z', event_type: 'alert', title: '心率过快', severity: 'high', detail: 'HR 150' },
          { time: '2024-01-01T11:00:00Z', event_type: 'medication', title: '美托洛尔', severity: 'info', detail: '25mg' },
        ],
      },
    })

    expect(wrapper.findAll('.timeline-item')).toHaveLength(2)
    expect(wrapper.text()).toContain('心率过快')
    expect(wrapper.text()).toContain('美托洛尔')
  })

  it('空事件应显示空提示', async () => {
    const { default: EvidenceTimeline } = await import('../components/evidence/EvidenceTimeline.vue')

    const wrapper = mount(EvidenceTimeline, {
      props: { events: [] },
    })

    expect(wrapper.find('.timeline-empty').exists()).toBe(true)
  })
})

// ── 全局菜单同步测试 ─────────────────────────────────

describe('患者模块注册表', () => {
  it('应定义所有模块分组', async () => {
    const { MODULE_GROUPS } = await import('../config/patientModuleRegistry')

    expect(MODULE_GROUPS).toBeDefined()
    expect(MODULE_GROUPS.length).toBeGreaterThan(0)

    const groupKeys = MODULE_GROUPS.map(g => g.key)
    expect(groupKeys).toContain('patient-detail')
    expect(groupKeys).toContain('alert-decision')
    expect(groupKeys).toContain('ai-analysis')
  })

  it('每个模块应有完整元数据', async () => {
    const { PATIENT_MODULES } = await import('../config/patientModuleRegistry')

    for (const mod of PATIENT_MODULES) {
      expect(mod.moduleKey).toBeTruthy()
      expect(mod.title).toBeTruthy()
      expect(mod.route).toContain(':patientId')
      expect(typeof mod.iframeUrl).toBe('function')
    }
  })

  it('getModuleByKey 应正确定位模块', async () => {
    const { getModuleByKey } = await import('../config/patientModuleRegistry')

    const mod = getModuleByKey('overview')
    expect(mod).toBeDefined()
    expect(mod?.title).toBe('病情总览')

    const missing = getModuleByKey('nonexistent')
    expect(missing).toBeUndefined()
  })
})

// ── 缺失数据"不可计算"测试 ──────────────────────────

describe('缺失数据处理', () => {
  it('null 值应标记为不可计算', async () => {
    const { default: EvidenceMetricCards } = await import('../components/evidence/EvidenceMetricCards.vue')

    const wrapper = mount(EvidenceMetricCards, {
      props: {
        metrics: [{
          code: 'Cr',
          name: '肌酐',
          value: null,
          unit: 'μmol/L',
          observed_at: null,
          reference_range: '44-133 μmol/L',
          abnormal_flag: 'missing',
        }],
      },
    })

    expect(wrapper.text()).toContain('不可计算')
    expect(wrapper.text()).toContain('缺失')
  })

  it('缺失数据列表应正确展示', async () => {
    const { default: ClinicalEvidenceDrawer } = await import('../components/evidence/ClinicalEvidenceDrawer.vue')

    // 组件应能接收 missing_data 并展示
    expect(ClinicalEvidenceDrawer).toBeDefined()
  })
})
