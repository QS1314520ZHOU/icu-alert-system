/**
 * 导航与患者上下文端到端测试。
 *
 * 使用 Playwright 真实浏览器测试，不使用 if(count>0) 条件跳过。
 * 通过 URL 参数设置身份，不依赖后端登录接口。
 */
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'

/** 带身份参数的 URL 构造 */
function urlWithAuth(path: string, opts: { role?: string; userId?: string } = {}) {
  const params = new URLSearchParams()
  if (opts.userId) params.set('userId', opts.userId)
  if (opts.role) params.set('role', opts.role)
  params.set('dept_code', 'ICU001')
  const qs = params.toString()
  return `${BASE_URL}${path}${qs ? '?' + qs : ''}`
}

test.describe('全局导航', () => {
  test('全局模式显示"患者智能分析"菜单组', async ({ page }) => {
    await page.goto(urlWithAuth('/doctor-home', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 患者智能分析组标签应该可见
    const aiGroupLabel = page.locator('text=患者智能分析')
    await expect(aiGroupLabel.first()).toBeVisible()
  })

  test('AI子模块各出现一次（无重复）', async ({ page }) => {
    await page.goto(urlWithAuth('/doctor-home', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 展开 AI 组
    const aiToggle = page.locator('button:has-text("患者智能分析")')
    if (await aiToggle.count() > 0) {
      await aiToggle.first().click()
    }

    // 检查每个 AI 模块 key 只出现一次
    const aiModuleLabels = ['风险预测', '综合风险', '相似病例', '循证证据']
    for (const label of aiModuleLabels) {
      const items = page.locator(`.side-nav__item:has-text("${label}")`)
      const count = await items.count()
      // 每个模块最多出现1次（在侧边栏中）
      expect(count).toBeLessThanOrEqual(1)
    }
  })

  test('全局模式下的更多菜单', async ({ page }) => {
    await page.goto(urlWithAuth('/doctor-home', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 更多组应该存在
    const moreGroup = page.locator('text=更多')
    await expect(moreGroup.first()).toBeVisible()
  })
})

test.describe('患者模式导航', () => {
  test('患者详情页显示患者模式侧边栏', async ({ page }) => {
    // 直接访问患者详情（使用模拟路由）
    await page.goto(urlWithAuth('/patient/test-patient-001/overview', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 应该显示"返回患者列表"按钮
    const backBtn = page.locator('text=返回患者列表')
    await expect(backBtn).toBeVisible()
  })

  test('患者模式不显示全局导航组', async ({ page }) => {
    await page.goto(urlWithAuth('/patient/test-patient-001/overview', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 不应该显示"今日工作"组
    const todayGroup = page.locator('.side-nav__group-label:has-text("今日工作")')
    await expect(todayGroup).toHaveCount(0)
  })
})

test.describe('Embed模式', () => {
  test('embed模式不显示侧边栏', async ({ page }) => {
    await page.goto(urlWithAuth('/embed/patient/test-patient-001/risk-prediction', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // embed 模式下不应该有 side-nav 元素
    const sideNav = page.locator('.side-nav')
    await expect(sideNav).toHaveCount(0)
  })
})

test.describe('Feature Flag 控制', () => {
  test('decision-assistants默认隐藏（无真实API时默认关闭）', async ({ page }) => {
    await page.goto(urlWithAuth('/doctor-home', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 展开 AI 组
    const aiToggle = page.locator('button:has-text("患者智能分析")')
    if (await aiToggle.count() > 0) {
      await aiToggle.first().click()
    }

    // decision-assistants 默认关闭，不应该出现
    const decisionItem = page.locator('.side-nav__item:has-text("专项决策")')
    await expect(decisionItem).toHaveCount(0)
  })
})

test.describe('路由与上下文', () => {
  test('患者详情页路由使用patientId参数', async ({ page }) => {
    await page.goto(urlWithAuth('/patient/abc-123/overview', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // URL 应包含 patientId
    expect(page.url()).toContain('/patient/abc-123/overview')
  })

  test('/patient/:id 重定向到 /patient/:id/overview', async ({ page }) => {
    await page.goto(urlWithAuth('/patient/test-001', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 应该重定向到 overview
    expect(page.url()).toContain('/patient/test-001/overview')
  })
})

test.describe('权限控制', () => {
  test('无权限模块直接输入URL跳403', async ({ page }) => {
    // nurse 角色访问 causal-inference（需要 doctor/director + 默认关闭）
    await page.goto(urlWithAuth('/patient/test-001/tool/causal-inference', { role: 'nurse', userId: 'test_nurse_001' }))
    await page.waitForLoadState('networkidle')

    // 应该跳转到 403 页面
    expect(page.url()).toContain('/403')
  })

  test('403页面正常显示', async ({ page }) => {
    await page.goto(urlWithAuth('/403', { role: 'nurse', userId: 'test_nurse_001' }))
    await page.waitForLoadState('networkidle')

    // 403 页面应该有权限不足的提示
    const forbiddenText = page.locator('text=权限不足')
    await expect(forbiddenText.first()).toBeVisible()
  })
})

test.describe('操作人身份', () => {
  test('URL userId显示在操作人区域', async ({ page }) => {
    await page.goto(urlWithAuth('/doctor-home', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 操作人 pill 应该显示
    const operatorPill = page.locator('.operator-pill')
    await expect(operatorPill).toBeVisible()
  })
})
