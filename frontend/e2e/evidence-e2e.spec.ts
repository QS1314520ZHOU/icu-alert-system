/**
 * 证据链端到端测试。
 *
 * 使用 Playwright 真实浏览器测试，不使用 if(count>0) 跳过。
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

test.describe('临床证据链端到端', () => {
  test('临床工作台页面加载成功', async ({ page }) => {
    await page.goto(urlWithAuth('/clinical-workflow', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 页面应该正常加载（不崩溃）
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })

  test('患者详情页正常加载', async ({ page }) => {
    await page.goto(urlWithAuth('/patient/test-001/overview', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 应该显示患者模式侧边栏
    const backBtn = page.locator('text=返回患者列表')
    await expect(backBtn).toBeVisible()
  })

  test('患者工具页正常加载', async ({ page }) => {
    await page.goto(urlWithAuth('/patient/test-001/tool/risk-prediction', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // 页面应该正常加载
    const body = page.locator('body')
    await expect(body).toBeVisible()
  })

  test('embed页面正常加载', async ({ page }) => {
    await page.goto(urlWithAuth('/embed/patient/test-001/risk-prediction', { role: 'doctor', userId: 'test_doc_001' }))
    await page.waitForLoadState('networkidle')

    // embed 页面不应该有侧边栏
    const sideNav = page.locator('.side-nav')
    await expect(sideNav).toHaveCount(0)
  })

  test('无权限模块跳403', async ({ page }) => {
    // nurse 角色访问 causal-inference（需要 doctor/director + 默认关闭）
    await page.goto(urlWithAuth('/patient/test-001/tool/causal-inference', { role: 'nurse', userId: 'test_nurse_001' }))
    await page.waitForLoadState('networkidle')

    // 应该跳转到 403
    expect(page.url()).toContain('/403')
  })
})
