/**
 * 综合风险模块 Vitest 单元测试。
 *
 * 测试覆盖：
 * 1. causal_chain 为数组时正常渲染
 * 2. causal_chain 为对象时不崩溃
 * 3. causal_chain.nodes 为数组时正确兼容
 * 4. causal_chain 为字符串时显示降级文本
 * 5. organ_status 为对象映射时正确转换
 * 6. top_actions 为 null 时不崩溃
 * 7. evidence 为对象时不崩溃
 * 8. 接口 error 字段显示错误状态
 * 9. HTTP 429/503 显示 AI 服务不可用
 * 10. 页面不能无限显示"正在分析"
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import IntegratedRiskView from '../views/embed/integrated-risk/IntegratedRiskView.vue'

// ── Mock API ──
const mockGetReport = vi.fn()
vi.mock('../api', () => ({
  getAiIntegratedRiskReport: (...args: any[]) => mockGetReport(...args),
}))

// ── Mock useEmbedBridge ──
const mockSendReportError = vi.fn()
const mockSendUpdateTitle = vi.fn()
vi.mock('../composables/useEmbedBridge', () => ({
  useEmbedBridge: () => ({
    sendUpdateTitle: mockSendUpdateTitle,
    sendReportError: mockSendReportError,
    sendResize: vi.fn(),
  }),
}))

// ── Router ──
function createTestRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/embed/patient/:patientId/integrated-risk', component: IntegratedRiskView },
    ],
  })
}

// ── Helper: mount component ──
async function mountView(patientId = 'test-patient-001') {
  const router = createTestRouter()
  router.push(`/embed/patient/${patientId}/integrated-risk`)
  await router.isReady()

  const wrapper = mount(IntegratedRiskView, {
    global: { plugins: [router] },
  })
  return wrapper
}

describe('IntegratedRiskView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ── Test 1: causal_chain 为数组时正常渲染 ──
  it('causal_chain 为数组时正常渲染因果链节点', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'high',
          summary: '多系统风险',
          causal_chain: [
            { label: '感染', time: '10:00', level: 'danger' },
            { label: '休克', time: '10:30', level: 'warning' },
          ],
          top_actions: [{ text: '抗感染', priority: 'critical', evidence: '血培养阳性' }],
          evidence: [{ time: '09:00', type: '感染', text: '体温升高', level: 'high' }],
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('感染')
    expect(wrapper.text()).toContain('休克')
    expect(wrapper.text()).toContain('抗感染')
    expect(wrapper.text()).toContain('体温升高')
  })

  // ── Test 2: causal_chain 为对象时不崩溃 ──
  it('causal_chain 为对象时降级为空，不崩溃', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'warning',
          summary: '测试',
          causal_chain: { some_key: 'some_value' },
          top_actions: [],
          evidence: [],
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    // 不崩溃，且无因果链节点
    expect(wrapper.findAll('.ir-chain-node')).toHaveLength(0)
  })

  // ── Test 3: causal_chain.nodes 为数组时正确兼容 ──
  it('causal_chain 为 { nodes: [...] } 时正确提取', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'high',
          summary: '测试',
          causal_chain: {
            nodes: [
              { label: '出血', time: '11:00', level: 'danger' },
              { label: '贫血', time: '11:30', level: 'warning' },
            ],
          },
          top_actions: [],
          evidence: [],
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('出血')
    expect(wrapper.text()).toContain('贫血')
  })

  // ── Test 4: causal_chain 为字符串时显示降级文本 ──
  it('causal_chain 为字符串时显示降级文本', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'warning',
          summary: '测试',
          causal_chain: '感染导致循环衰竭，需紧急处理',
          top_actions: [],
          evidence: [],
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('感染导致循环衰竭，需紧急处理')
    expect(wrapper.findAll('.ir-chain-node')).toHaveLength(0)
  })

  // ── Test 5: organ_status 为对象映射时正确转换 ──
  it('organ_status 为对象映射时正确转换为数组', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'warning',
          summary: '测试',
          organ_status: {
            respiratory: { status: 'impaired' },
            renal: { status: 'normal' },
          },
          causal_chain: [],
          top_actions: [],
          evidence: [],
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('呼吸')
    expect(wrapper.text()).toContain('肾脏')
    expect(wrapper.text()).toContain('受损')
    expect(wrapper.text()).toContain('正常')
  })

  // ── Test 6: top_actions 为 null 时不崩溃 ──
  it('top_actions 为 null 时不崩溃', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'normal',
          summary: '测试',
          causal_chain: [],
          top_actions: null,
          evidence: [],
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.findAll('.ir-action-card')).toHaveLength(0)
  })

  // ── Test 7: evidence 为对象时不崩溃 ──
  it('evidence 为对象时降级为空，不崩溃', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'normal',
          summary: '测试',
          causal_chain: [],
          top_actions: [],
          evidence: { some_key: 'some_value' },
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.findAll('.ir-evidence-item')).toHaveLength(0)
  })

  // ── Test 8: 接口 error 字段显示错误状态 ──
  it('接口返回 error 字段时显示错误状态', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: null,
        error: '预警引擎未就绪，无法生成综合风险报告',
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('预警引擎未就绪')
    expect(wrapper.text()).toContain('重试')
  })

  // ── Test 9: HTTP 503 显示 AI 服务不可用 ──
  it('HTTP 503 显示 AI 服务不可用', async () => {
    mockGetReport.mockRejectedValueOnce({
      response: { status: 503, data: { detail: 'AI服务额度不足，暂时无法生成综合风险报告' } },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('AI服务额度不足')
    expect(wrapper.text()).toContain('重试')
  })

  // ── Test 10: 页面不能无限显示"正在分析" ──
  it('加载完成后不再显示"正在分析"', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'normal',
          summary: '正常',
          causal_chain: [],
          top_actions: [],
          evidence: [],
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).not.toContain('正在分析综合风险')
    expect(wrapper.text()).toContain('正常')
  })

  // ── 额外: HTTP 401 显示登录失效 ──
  it('HTTP 401 显示登录状态失效', async () => {
    mockGetReport.mockRejectedValueOnce({
      response: { status: 401 },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('登录状态已失效')
  })

  // ── 额外: HTTP 403 显示无权访问 ──
  it('HTTP 403 显示无权访问', async () => {
    mockGetReport.mockRejectedValueOnce({
      response: { status: 403 },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('无权访问')
  })

  // ── 额外: top3_actions 字段兼容 ──
  it('top3_actions 字段正确映射为 top_actions', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'high',
          summary: '测试',
          causal_chain: [],
          top3_actions: [
            { action: '抗感染', priority: 'critical', rationale: '血培养阳性' },
          ],
          evidence: [],
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('抗感染')
    expect(wrapper.text()).toContain('血培养阳性')
  })

  // ── 额外: stale 报告显示提示 ──
  it('stale 报告显示过期提示', async () => {
    mockGetReport.mockResolvedValueOnce({
      data: {
        report: {
          risk_level: 'warning',
          summary: '历史报告',
          causal_chain: [],
          top_actions: [],
          evidence: [],
          stale: true,
          generation_status: 'llm_quota_exhausted',
        },
      },
    })

    const wrapper = await mountView()
    await flushPromises()

    expect(wrapper.text()).toContain('AI服务额度不足，暂时无法更新')
  })
})
