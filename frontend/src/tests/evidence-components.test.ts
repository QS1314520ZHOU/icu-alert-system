/**
 * P0 重写：证据链组件单元测试。
 *
 * 使用真实组件渲染，不 mock 返回值。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import RuleCalculationPanel from '../components/evidence/RuleCalculationPanel.vue'
import AiEvidenceAnalysis from '../components/evidence/AiEvidenceAnalysis.vue'
import EvidenceMetricCards from '../components/evidence/EvidenceMetricCards.vue'

describe('RuleCalculationPanel', () => {
  const mockRuleCalc = {
    score_type: 'discharge_readiness',
    total_score: 80,
    calculable: true,
    items: [
      { label: '循环稳定', status: 'pass', ok: true },
      { label: '氧合达标', status: 'pass', ok: true },
      { label: 'SOFA ≤ 6', status: 'unavailable', ok: null },
    ],
    lights: [
      { label: 'RSBI < 105', status: 'pass', ok: true },
      { label: 'SpO2 > 90%', status: 'pass', ok: true },
      { label: 'SBT 通过', status: 'unavailable', ok: null },
    ],
    description: '撤机评估',
  }

  it('渲染灯号三态', () => {
    const wrapper = mount(RuleCalculationPanel, {
      props: { ruleCalc: mockRuleCalc },
    })

    // 验证灯号元素存在
    const lights = wrapper.findAll('.light-item')
    expect(lights.length).toBe(3)

    // 验证三态 class（组件使用 status 值作为 CSS class）
    expect(lights[0].classes()).toContain('pass')
    expect(lights[1].classes()).toContain('pass')
    expect(lights[2].classes()).toContain('unavailable')
  })

  it('渲染评分明细三态', () => {
    const wrapper = mount(RuleCalculationPanel, {
      props: { ruleCalc: mockRuleCalc },
    })

    const items = wrapper.findAll('.calc-item')
    expect(items.length).toBe(3)

    // 验证"不可计算"文本
    const unavailableStatus = wrapper.findAll('.item-status.unavailable')
    expect(unavailableStatus.length).toBeGreaterThan(0)
  })

  it('空数据显示提示', () => {
    const wrapper = mount(RuleCalculationPanel, {
      props: { ruleCalc: null },
    })
    expect(wrapper.text()).toContain('暂无评分')
  })

  it('total_score 为 null 时不显示总分', () => {
    const wrapper = mount(RuleCalculationPanel, {
      props: {
        ruleCalc: {
          ...mockRuleCalc,
          total_score: null,
          calculable: false,
        },
      },
    })
    expect(wrapper.text()).not.toContain('总分')
  })
})

describe('AiEvidenceAnalysis', () => {
  const mockAiAnalysis = {
    supporting_evidence: ['乳酸升高', '心率加快'],
    opposing_evidence: ['血压稳定'],
    uncertainties: ['可能为感染性休克'],
    disclaimer: 'AI生成，待临床确认',
    model: 'gpt-4',
    generated_at: '2024-01-01T00:00:00Z',
  }

  it('渲染支持/反对/不确定证据', () => {
    const wrapper = mount(AiEvidenceAnalysis, {
      props: { aiAnalysis: mockAiAnalysis },
    })

    expect(wrapper.text()).toContain('乳酸升高')
    expect(wrapper.text()).toContain('血压稳定')
    expect(wrapper.text()).toContain('可能为感染性休克')
    expect(wrapper.text()).toContain('AI生成')
  })

  it('null 显示"尚未生成 AI 分析"', () => {
    const wrapper = mount(AiEvidenceAnalysis, {
      props: { aiAnalysis: null },
    })
    expect(wrapper.text()).toContain('尚未生成')
  })

  it('空数组显示"尚未生成 AI 分析"', () => {
    const wrapper = mount(AiEvidenceAnalysis, {
      props: {
        aiAnalysis: {
          ...mockAiAnalysis,
          supporting_evidence: [],
          opposing_evidence: [],
          uncertainties: [],
        },
      },
    })
    expect(wrapper.text()).toContain('尚未生成')
  })
})

describe('EvidenceMetricCards', () => {
  const mockMetrics = [
    {
      code: 'HR',
      name: '心率',
      value: 120,
      unit: 'bpm',
      observed_at: '2024-01-01T00:00:00Z',
      reference_range: '60-100 bpm',
      abnormal_flag: 'high' as const,
    },
    {
      code: 'SpO2',
      name: '血氧饱和度',
      value: 98,
      unit: '%',
      observed_at: '2024-01-01T00:00:00Z',
      reference_range: '≥95%',
      abnormal_flag: 'normal' as const,
    },
    {
      code: 'Cr',
      name: '肌酐',
      value: null,
      unit: 'mg/dL',
      observed_at: null,
      reference_range: '0.6-1.2 mg/dL',
      abnormal_flag: 'missing' as const,
    },
  ]

  it('渲染指标卡片', () => {
    const wrapper = mount(EvidenceMetricCards, {
      props: { metrics: mockMetrics },
    })

    expect(wrapper.text()).toContain('心率')
    expect(wrapper.text()).toContain('血氧饱和度')
    expect(wrapper.text()).toContain('肌酐')
  })

  it('异常值标红', () => {
    const wrapper = mount(EvidenceMetricCards, {
      props: { metrics: mockMetrics },
    })

    const cards = wrapper.findAll('.metric-card')
    expect(cards.length).toBe(3)

    // 验证异常卡片有 flag-high class（组件使用 flag- 前缀）
    expect(cards[0].classes()).toContain('flag-high')
    expect(cards[1].classes()).toContain('flag-normal')
  })

  it('缺失值显示"不可计算"', () => {
    const wrapper = mount(EvidenceMetricCards, {
      props: { metrics: mockMetrics },
    })

    expect(wrapper.text()).toContain('不可计算')
  })

  it('空指标列表显示提示', () => {
    const wrapper = mount(EvidenceMetricCards, {
      props: { metrics: [] },
    })
    expect(wrapper.text()).toContain('暂无指标数据')
  })
})
