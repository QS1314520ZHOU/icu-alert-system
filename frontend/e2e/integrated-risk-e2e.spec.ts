/**
 * 综合风险模块端到端测试。
 *
 * 使用 Playwright 真实浏览器测试，不使用 if(count>0) 跳过。
 * 通过 URL 参数设置身份，不依赖后端登录接口。
 *
 * 测试覆盖：
 * - 打开综合风险页面
 * - 监听 pageerror 和 console error
 * - 断言不存在 "chain.map is not a function"
 * - 断言加载结束后显示成功、空数据或错误状态之一
 * - 不允许无限 loading
 * - 不允许条件式跳过
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

test.describe('综合风险模块端到端', () => {
  test('综合风险页面加载成功，无 JS 崩溃', async ({ page }) => {
    const errors: string[] = []

    // 监听 pageerror（未捕获异常）
    page.on('pageerror', (err) => {
      errors.push(err.message)
    })

    // 监听 console.error
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        errors.push(msg.text())
      }
    })

    await page.goto(
      urlWithAuth('/embed/patient/test-001/integrated-risk', {
        role: 'doctor',
        userId: 'test_doc_001',
      }),
    )
    await page.waitForLoadState('networkidle')

    // 等待加载结束（最多 15 秒）
    // 加载结束后应显示以下状态之一：成功报告、空数据提示、错误提示
    await expect(async () => {
      const body = await page.textContent('body')
      const hasSuccess = body?.includes('风险') || body?.includes('正常') || false
      const hasEmpty = body?.includes('暂无') || false
      const hasError = body?.includes('重试') || body?.includes('失败') || body?.includes('不可用') || false
      const hasLoading = body?.includes('正在分析') || false

      // 加载结束后不能还在 loading
      expect(hasLoading).toBe(false)
      // 必须处于三种状态之一
      expect(hasSuccess || hasEmpty || hasError).toBe(true)
    }).toPass({ timeout: 15000 })

    // 断言不存在 "chain.map is not a function"
    const hasChainMapError = errors.some(
      (e) => e.includes('chain.map') || e.includes('is not a function'),
    )
    expect(hasChainMapError).toBe(false)
  })

  test('综合风险页面不显示无限 loading', async ({ page }) => {
    await page.goto(
      urlWithAuth('/embed/patient/test-001/integrated-risk', {
        role: 'doctor',
        userId: 'test_doc_001',
      }),
    )
    await page.waitForLoadState('networkidle')

    // 等待足够时间后，不应仍在 loading
    await page.waitForTimeout(5000)
    const body = await page.textContent('body')
    expect(body).not.toContain('正在分析综合风险')
  })

  test('embed 综风险页面无侧边栏', async ({ page }) => {
    await page.goto(
      urlWithAuth('/embed/patient/test-001/integrated-risk', {
        role: 'doctor',
        userId: 'test_doc_001',
      }),
    )
    await page.waitForLoadState('networkidle')

    // embed 页面不应有侧边栏
    const sideNav = page.locator('.side-nav')
    await expect(sideNav).toHaveCount(0)
  })
})
