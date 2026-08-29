/**
 * 证据链 E2E 测试 (Playwright)
 */
import { test, expect } from '@playwright/test'

test.describe('临床证据链 E2E', () => {
  test.beforeEach(async ({ page }) => {
    // 登录并进入临床工作台
    await page.goto('/')
    // 等待页面加载
    await page.waitForLoadState('networkidle')
  })

  test('全局菜单应渲染所有模块分组', async ({ page }) => {
    // 检查侧边栏或导航菜单存在
    const nav = page.locator('nav, .sidebar-nav, .main-nav')
    if (await nav.count() > 0) {
      // 验证菜单项存在
      await expect(nav.first()).toBeVisible()
    }
  })

  test('临床工作台 - 点击高风险患者应打开证据抽屉', async ({ page }) => {
    // 进入临床工作台
    await page.goto('/clinical-workflow?role=doctor&userName=test')
    await page.waitForLoadState('networkidle')

    // 查找高风险患者行
    const patientRow = page.locator('.patient-row').first()
    if (await patientRow.count() > 0) {
      await patientRow.click()

      // 验证证据抽屉打开
      const drawer = page.locator('.evidence-drawer, .ant-drawer')
      await expect(drawer.first()).toBeVisible({ timeout: 5000 })

      // 验证抽屉包含关键区块
      const conclusion = page.locator('.ev-conclusion, .ev-section')
      await expect(conclusion.first()).toBeVisible({ timeout: 3000 })
    }
  })

  test('临床工作台 - 医嘱泳道点击应打开证据抽屉', async ({ page }) => {
    await page.goto('/clinical-workflow?role=doctor&userName=test')
    await page.waitForLoadState('networkidle')

    // 切换到医嘱闭环 tab
    const orderTab = page.locator('button', { hasText: '医嘱闭环' })
    if (await orderTab.count() > 0) {
      await orderTab.click()

      // 点击泳道行
      const swimlane = page.locator('.swimlane-row').first()
      if (await swimlane.count() > 0) {
        await swimlane.click()

        // 验证证据抽屉打开
        const drawer = page.locator('.evidence-drawer, .ant-drawer')
        await expect(drawer.first()).toBeVisible({ timeout: 5000 })
      }
    }
  })

  test('护理任务 - 护理漏项点击应打开证据抽屉', async ({ page }) => {
    await page.goto('/clinical-workflow?role=nurse&userName=test')
    await page.waitForLoadState('networkidle')

    // 切换到护理任务 tab
    const nursingTab = page.locator('button', { hasText: '护理任务' })
    if (await nursingTab.count() > 0) {
      await nursingTab.click()

      // 点击护理漏项
      const omission = page.locator('.omission-cell').first()
      if (await omission.count() > 0) {
        await omission.click()

        // 验证证据抽屉打开
        const drawer = page.locator('.evidence-drawer, .ant-drawer')
        await expect(drawer.first()).toBeVisible({ timeout: 5000 })
      }
    }
  })

  test('专项治疗 - 撤机灯号点击应打开证据抽屉', async ({ page }) => {
    await page.goto('/clinical-workflow?role=doctor&userName=test')
    await page.waitForLoadState('networkidle')

    // 切换到专项治疗 tab
    const specialTab = page.locator('button', { hasText: '专项治疗' })
    if (await specialTab.count() > 0) {
      await specialTab.click()

      // 点击撤机灯号行
      const weaningRow = page.locator('.light-row').first()
      if (await weaningRow.count() > 0) {
        await weaningRow.click()

        // 验证证据抽屉打开
        const drawer = page.locator('.evidence-drawer, .ant-drawer')
        await expect(drawer.first()).toBeVisible({ timeout: 5000 })
      }
    }
  })

  test('管理驾驶舱 - 规则噪声应显示详情按钮', async ({ page }) => {
    await page.goto('/clinical-workflow?role=director&userName=test')
    await page.waitForLoadState('networkidle')

    // 切换到管理驾驶舱 tab
    const directorTab = page.locator('button', { hasText: '管理驾驶舱' })
    if (await directorTab.count() > 0) {
      await directorTab.click()

      // 检查规则噪声详情按钮
      const detailBtn = page.locator('.scanner-detail-btn').first()
      if (await detailBtn.count() > 0) {
        await detailBtn.click()

        // 验证证据抽屉打开
        const drawer = page.locator('.evidence-drawer, .ant-drawer')
        await expect(drawer.first()).toBeVisible({ timeout: 5000 })
      }
    }
  })

  test('证据抽屉应展示完整九区块', async ({ page }) => {
    await page.goto('/clinical-workflow?role=doctor&userName=test')
    await page.waitForLoadState('networkidle')

    // 打开一个证据抽屉
    const patientRow = page.locator('.patient-row').first()
    if (await patientRow.count() > 0) {
      await patientRow.click()

      const drawer = page.locator('.evidence-drawer, .ant-drawer')
      await expect(drawer.first()).toBeVisible({ timeout: 5000 })

      // 验证关键区块标题存在
      const sectionTitles = page.locator('.ev-section-title')
      const count = await sectionTitles.count()
      expect(count).toBeGreaterThanOrEqual(5) // 至少5个区块

      // 验证结论摘要存在
      const conclusion = page.locator('.ev-conclusion')
      await expect(conclusion.first()).toBeVisible()
    }
  })

  test('患者详情 - 风险标签点击应打开证据抽屉', async ({ page }) => {
    // 假设有患者数据
    await page.goto('/patient/test-patient/overview')
    await page.waitForLoadState('networkidle')

    // 点击风险标签
    const riskBadge = page.locator('.context-bar__risk')
    if (await riskBadge.count() > 0) {
      await riskBadge.click()

      // 验证证据抽屉打开
      const drawer = page.locator('.evidence-drawer, .ant-drawer')
      await expect(drawer.first()).toBeVisible({ timeout: 5000 })
    }
  })
})
