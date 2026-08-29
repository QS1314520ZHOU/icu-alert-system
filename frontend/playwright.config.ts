import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright 配置 — ICU Alert System 前端端到端测试
 *
 * 自动启动 Vite 开发服务器，无需手动提前启动。
 */
export default defineConfig({
  testDir: './e2e',
  testRegex: '.*\\.spec\\.ts$',
  timeout: 30_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['html', { open: 'never' }],
    ['list'],
  ],
  use: {
    baseURL: 'http://localhost:5173',
    screenshot: 'only-on-failure',
    trace: 'off',
    video: 'off',
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        channel: 'chrome',
      },
    },
  ],
  webServer: {
    command: 'npm run dev',
    port: 5173,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
})
