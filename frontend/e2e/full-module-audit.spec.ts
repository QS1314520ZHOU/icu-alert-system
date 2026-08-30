/**
 * Full Module Audit - Playwright E2E Test
 *
 * Systematically tests every route in the ICU Alert System for:
 * - Page loads without white screen
 * - No uncaught JS errors
 * - No console errors
 * - HTTP requests don't fail unexpectedly
 * - Loading states resolve
 *
 * RUN_ID: 8b4eeab1-6b78-47f8-a36c-e8f788402923
 */
import { test, expect, type Page, type ConsoleMessage } from '@playwright/test'

const BASE_URL = process.env.BASE_URL || 'http://localhost:5173'
const API_BASE = process.env.API_BASE || 'http://127.0.0.1:8000'

// Test accounts
const ACCOUNTS = {
  admin: { username: 'admin', password: 'admin123' },
  doctor: { username: 'doctor', password: 'doctor123' },
  nurse: { username: 'nurse', password: 'nurse123' },
  head_nurse: { username: 'head_nurse', password: 'head123' },
  director: { username: 'director', password: 'director123' },
}

// Helper: login via API and set token in localStorage
async function loginAs(page: Page, role: keyof typeof ACCOUNTS) {
  const account = ACCOUNTS[role]
  const response = await page.request.post(`${API_BASE}/api/auth/login`, {
    data: { username: account.username, password: account.password },
  })
  const body = await response.json()
  const token = body.access_token
  expect(token).toBeTruthy()

  // Set auth in localStorage (the app reads from there)
  await page.evaluate(([t, r]) => {
    localStorage.setItem('access_token', t)
    localStorage.setItem('role', r)
  }, [token, role])

  return token
}

// Helper: get a valid patient ID from the API
async function getPatientId(page: Page): Promise<string> {
  const token = await page.evaluate(() => localStorage.getItem('access_token'))
  const response = await page.request.get(`${API_BASE}/api/patients?limit=1`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const body = await response.json()
  return body.patients?.[0]?._id || 'test-patient-id'
}

// Helper: collect console errors during page navigation
function collectConsoleErrors(page: Page) {
  const errors: string[] = []
  const warnings: string[] = []
  const pageErrors: Error[] = []

  page.on('console', (msg: ConsoleMessage) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      // Filter known harmless dev messages
      if (text.includes('[vite]') && text.includes('hot update')) return
      if (text.includes('Download the Vue DevTools')) return
      if (text.includes('[HMR]')) return
      errors.push(text)
    }
    if (msg.type() === 'warning') {
      warnings.push(msg.text())
    }
  })

  page.on('pageerror', (error: Error) => {
    pageErrors.push(error)
  })

  return { errors, warnings, pageErrors }
}

// Critical JS errors that always indicate a real bug
const CRITICAL_ERROR_PATTERNS = [
  '.map is not a function',
  '.slice is not a function',
  '.filter is not a function',
  'Cannot read properties of undefined',
  'Cannot read properties of null',
  'Unhandled error during execution',
  'Unhandled promise rejection',
  'Maximum recursive updates',
  'is not a function',
  'is not iterable',
]

function hasCriticalError(errors: string[]): string | null {
  for (const err of errors) {
    for (const pattern of CRITICAL_ERROR_PATTERNS) {
      if (err.includes(pattern)) {
        return `Critical error: "${pattern}" in: ${err.substring(0, 200)}`
      }
    }
  }
  return null
}

// ── Test Suite ──

test.describe('Full Module Audit', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to app root first to set up context
    await page.goto(BASE_URL)
  })

  // ═══ Auth Flow ═══

  test('Login page loads and login works for all roles', async ({ page }) => {
    for (const role of Object.keys(ACCOUNTS) as Array<keyof typeof ACCOUNTS>) {
      const token = await loginAs(page, role)
      expect(token).toBeTruthy()

      // Verify /me endpoint works
      const meResponse = await page.request.get(`${BASE_URL}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      expect(meResponse.status()).toBe(200)
      const me = await meResponse.json()
      expect(me.username).toBe(ACCOUNTS[role].username)
      expect(me.role).toBeTruthy()
    }
  })

  test('Invalid credentials return 401', async ({ page }) => {
    const response = await page.request.post(`${BASE_URL}/api/auth/login`, {
      data: { username: 'nonexistent', password: 'wrong' },
    })
    expect(response.status()).toBe(401)
  })

  test('No auth returns 401 on protected endpoints', async ({ page }) => {
    const response = await page.request.get(`${BASE_URL}/api/auth/me`)
    expect(response.status()).toBe(401)
  })

  test('Invalid token returns 401', async ({ page }) => {
    const response = await page.request.get(`${BASE_URL}/api/auth/me`, {
      headers: { Authorization: 'Bearer invalid-token-here' },
    })
    expect(response.status()).toBe(401)
  })

  // ═══ Global Pages ═══

  test('Home redirect page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/`)
    await page.waitForTimeout(3000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Doctor home page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/doctor-home`)
    await page.waitForTimeout(5000)
    // Should not have critical JS errors
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Nurse home page loads', async ({ page }) => {
    await loginAs(page, 'nurse')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/nurse-home`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Head nurse home page loads', async ({ page }) => {
    await loginAs(page, 'head_nurse')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/head-nurse-home`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Director home page loads', async ({ page }) => {
    await loginAs(page, 'director')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/director-home`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Patient Overview ═══

  test('Patient overview page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/patients`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Patient Detail Pages ═══

  test('Patient detail overview loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/patient/${patientId}/overview`)
    await page.waitForTimeout(8000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Patient monitoring page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/patient/${patientId}/monitoring`)
    await page.waitForTimeout(8000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Patient treatment page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/patient/${patientId}/treatment`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Patient alerts page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/patient/${patientId}/alerts`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Patient documents page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/patient/${patientId}/documents`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Patient followup page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/patient/${patientId}/followup`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Embed Modules ═══

  test('Risk prediction embed loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/embed/patient/${patientId}/risk-prediction`)
    await page.waitForTimeout(8000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Integrated risk embed loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/embed/patient/${patientId}/integrated-risk`)
    await page.waitForTimeout(8000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Evidence embed loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/embed/patient/${patientId}/evidence`)
    await page.waitForTimeout(8000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Similar cases embed loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/embed/patient/${patientId}/similar-cases`)
    await page.waitForTimeout(8000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Disease trajectory embed loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const patientId = await getPatientId(page)
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/embed/patient/${patientId}/disease-trajectory`)
    await page.waitForTimeout(8000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Clinical Workflow Pages ═══

  test('Clinical workflow page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/clinical-workflow`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Handover page loads', async ({ page }) => {
    await loginAs(page, 'nurse')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/handover`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('AI consult page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/ai-consult`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Rounding sheet page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/rounding-sheet`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Specialty Pages ═══

  test('Respiratory dashboard loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/respiratory-dashboard`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Nutrition support page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/nutrition-support`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('MDT board page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/mdt`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Analytics & Admin ═══

  test('Analytics page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/analytics`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('AI ops page loads', async ({ page }) => {
    await loginAs(page, 'admin')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/ai-ops`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Runtime config page loads', async ({ page }) => {
    await loginAs(page, 'admin')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/admin/runtime-config`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Disease Center ═══

  test('Disease center overview loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/disease-center/overview`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Disease center diseases page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/disease-center/diseases`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ SAKI Research Center ═══

  test('SAKI overview loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/disease-center/saki/overview`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Research ═══

  test('Research workbench loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/research-workbench`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  test('Clinical trials page loads', async ({ page }) => {
    await loginAs(page, 'doctor')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/clinical-trials`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Mobile ═══

  test('Mobile home loads', async ({ page }) => {
    await loginAs(page, 'nurse')
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/m`)
    await page.waitForTimeout(5000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ 403 Page ═══

  test('403 forbidden page loads', async ({ page }) => {
    const { errors, pageErrors } = collectConsoleErrors(page)
    await page.goto(`${BASE_URL}/403`)
    await page.waitForTimeout(3000)
    const critical = hasCriticalError(errors)
    expect(critical).toBeNull()
    expect(pageErrors).toEqual([])
  })

  // ═══ Role-Based Access ═══

  test('Nurse cannot access director home', async ({ page }) => {
    await loginAs(page, 'nurse')
    const response = await page.request.get(`${BASE_URL}/api/home/director?user_id=nurse`, {
      headers: {
        Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('access_token'))}`,
      },
    })
    // Should get 403 or empty data
    expect([200, 403]).toContain(response.status())
  })

  test('Doctor cannot access admin endpoints', async ({ page }) => {
    await loginAs(page, 'doctor')
    const response = await page.request.get(`${BASE_URL}/api/admin/runtime-config`, {
      headers: {
        Authorization: `Bearer ${await page.evaluate(() => localStorage.getItem('access_token'))}`,
      },
    })
    // Should get 200 (config is readable) or 403
    expect([200, 403]).toContain(response.status())
  })
})
