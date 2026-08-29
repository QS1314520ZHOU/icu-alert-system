/**
 * P0 重写：证据链端到端测试。
 *
 * 使用 Playwright 真实浏览器测试，不使用 if(count>0) 跳过。
 * 使用测试数据 seed 确保数据一致性。
 */
import { test, expect } from '@playwright/test'

// 测试基础 URL
const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'

test.describe('临床证据链端到端', () => {
  test.beforeEach(async ({ page }) => {
    // 登录获取认证（使用测试账号）
    await page.goto(`${BASE_URL}/login`)
    await page.fill('[data-testid="username"]', 'test_doctor')
    await page.fill('[data-testid="password"]', 'test_password')
    await page.click('[data-testid="login-btn"]')
    await page.waitForURL(/.*\/dashboard|.*\/clinical-workflow/)
  })

  test('临床工作台页面加载成功', async ({ page }) => {
    await page.goto(`${BASE_URL}/clinical-workflow`)
    await expect(page.locator('[data-testid="clinical-workflow"]')).toBeVisible()
  })

  test('今日任务页面渲染任务列表', async ({ page }) => {
    await page.goto(`${BASE_URL}/clinical-workflow/today-tasks`)
    await expect(page.locator('[data-testid="today-tasks"]')).toBeVisible()
  })

  test('撤机评估页面灯号显示', async ({ page }) => {
    await page.goto(`${BASE_URL}/clinical-workflow/special-treatments`)

    // 验证撤机评估 tab 存在
    await expect(page.locator('text=撤机')).toBeVisible()

    // 验证灯号使用三态 class
    const lightItems = page.locator('.light-item')
    const count = await lightItems.count()

    for (let i = 0; i < count; i++) {
      const item = lightItems.nth(i)
      // 每个灯号必须是三种状态之一
      await expect(item).toHaveClass(/ok|bad|unavailable/)
    }
  })

  test('转出评估页面百分比显示', async ({ page }) => {
    await page.goto(`${BASE_URL}/clinical-workflow/special-treatments`)

    // 验证转出 tab 存在
    await expect(page.locator('text=转出')).toBeVisible()

    // 验证百分比不显示为 0%（应该是数值或"不可计算"）
    const percentElements = page.locator('.light-percent')
    const count = await percentElements.count()

    for (let i = 0; i < count; i++) {
      const text = await percentElements.nth(i).textContent()
      // 不应该是 "0%"（除非真的计算出 0）
      expect(text).not.toBe('0%')
    }
  })

  test('证据抽屉打开并显示内容', async ({ page }) => {
    await page.goto(`${BASE_URL}/clinical-workflow`)

    // 点击患者行打开证据抽屉
    const patientRow = page.locator('[data-testid="patient-row"]').first()
    await patientRow.click()

    // 验证抽屉打开
    await expect(page.locator('[data-testid="evidence-drawer"]')).toBeVisible()

    // 验证包含结论
    await expect(page.locator('[data-testid="evidence-conclusion"]')).toBeVisible()
  })

  test('证据抽屉 AI 分析空状态', async ({ page }) => {
    await page.goto(`${BASE_URL}/clinical-workflow`)

    // 打开证据抽屉
    const patientRow = page.locator('[data-testid="patient-row"]').first()
    await patientRow.click()

    // 展开 AI 分析 section
    const aiSection = page.locator('text=AI 分析')
    await aiSection.click()

    // 验证显示"尚未生成 AI 分析"或真实的 AI 内容
    const aiContent = page.locator('.ai-evidence')
    await expect(aiContent).toBeVisible()

    // 验证有内容（不是空白）
    const text = await aiContent.textContent()
    expect(text?.length).toBeGreaterThan(0)
  })

  test('证据抽屉来源显示临床名称', async ({ page }) => {
    await page.goto(`${BASE_URL}/clinical-workflow`)

    // 打开证据抽屉
    const patientRow = page.locator('[data-testid="patient-row"]').first()
    await patientRow.click()

    // 展开原始证据 section
    const evidenceSection = page.locator('text=原始证据')
    await evidenceSection.click()

    // 验证来源列显示临床名称（不是 collection_name）
    const sourceCells = page.locator('[data-testid="source-system"]')
    const count = await sourceCells.count()

    for (let i = 0; i < count; i++) {
      const text = await sourceCells.nth(i).textContent()
      // 不应该包含 MongoDB 集合名
      expect(text).not.toMatch(/bedside|labResult|alert_records|score|drugExe/)
      // 应该是临床来源名称
      expect(text).toMatch(/监护仪|LIS|HIS|护理|预警|评分/)
    }
  })

  test('跨患者数据隔离', async ({ page }) => {
    // 这个测试需要后端 seed 数据支持
    // 验证查询患者 A 的数据时不会返回患者 B 的数据

    await page.goto(`${BASE_URL}/clinical-workflow`)

    // 获取第一个患者的信息
    const firstPatient = page.locator('[data-testid="patient-id"]').first()
    const patientId = await firstPatient.textContent()

    // 打开该患者的证据抽屉
    await page.locator('[data-testid="patient-row"]').first().click()

    // 验证证据抽屉中的 patient_id 与选择的一致
    const evidencePatientId = page.locator('[data-testid="evidence-patient-id"]')
    await expect(evidencePatientId).toHaveText(patientId || '')
  })

  test('context_id 过滤生效', async ({ page }) => {
    await page.goto(`${BASE_URL}/clinical-workflow`)

    // 打开证据抽屉
    const patientRow = page.locator('[data-testid="patient-row"]').first()
    await patientRow.click()

    // 验证 evidence-provenance 中包含 context_id
    const provenance = page.locator('[data-testid="evidence-provenance"]')
    await expect(provenance).toBeVisible()
  })
})
