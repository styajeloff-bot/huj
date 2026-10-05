import { expect, test, type Page, type Route } from '@playwright/test'

const APPLICATION_ID = '20418000-0000-4000-8000-000000000001'
const LEASING_COMPANY_ID = '20418000-0000-4000-8000-000000000002'
const LCA_ID = '20418000-0000-4000-8000-000000000003'
const DOCUMENT_ID = '20418000-0000-4000-8000-000000000004'
const DOCUMENT_NAME = 'Бухгалтерский баланс за 2025 год'
const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost'

test.use({
  baseURL: BASE_URL,
  viewport: { width: 1280, height: 900 },
  navigationTimeout: 30_000,
})

let authCookies: Array<{ name: string; value: string; domain: string; path: string }> = []

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: BASE_URL })
  const login = await request.post('/api/v1/auth/login', { data: { phone: '+766****4571' } })
  expect([200, 403]).toContain(login.status())
  const verification = await request.post('/api/v1/auth/verify-phone', {
    data: { phone: '+766****4571', code: '0000' },
  })
  expect(verification.status()).toBe(200)
  const state = await request.storageState()
  authCookies = state.cookies
  await request.dispose()
})

test.beforeEach(async ({ context }) => {
  await context.addCookies(authCookies)
})

async function setupMocks(page: Page) {
  let documentStatus = 'pending'
  let patchPayload: unknown
  let patchRequestReceived = false
  let releaseApprovalResponse: (() => void) | undefined
  const approvalResponseReleased = new Promise<void>(resolve => {
    releaseApprovalResponse = resolve
  })

  const fulfill = (route: Route, json: unknown, status = 200) => route.fulfill({
    status,
    json,
    headers: {
      'access-control-allow-origin': route.request().headers().origin || '*',
      'access-control-allow-credentials': 'true',
    },
  })

  await page.route(url => url.pathname === `/api/v1/leasing/applications/${APPLICATION_ID}/response`, async route => {
    if (route.request().method() !== 'GET') return route.fallback()
    return fulfill(route, {
      link: {
        id: LCA_ID,
        application_id: APPLICATION_ID,
        leasing_company_id: LEASING_COMPANY_ID,
        status: 'in_progress',
        submitted_at: '2026-09-24T10:00:00Z',
      },
      application: {
        id: APPLICATION_ID,
        display_number: '20418-TEST',
        status: 'active',
        company_name: 'ООО Тест Клиент',
        company_inn: '7712345678',
        leasing_company_name: 'Альфа Лизинг',
        vehicles: [],
      },
      proposals: [],
      can_review: true,
      can_confirm_deal: false,
      confirm_deal_disabled_reason: null,
    })
  })

  await page.route(url => url.pathname === `/api/v1/leasing/applications/${APPLICATION_ID}/documents`, async route => {
    if (route.request().method() !== 'GET') return route.fallback()
    return fulfill(route, {
      documents: [{
        id: DOCUMENT_ID,
        document_type: 'balance_sheet',
        display_name: DOCUMENT_NAME,
        period_label: '2025',
        file_name: 'balance-2025.pdf',
        file_size: 123_456,
        uploaded_at: '2026-09-24T10:00:00Z',
        status: 'provided',
        leasing_company_status: documentStatus,
        download_url: '/api/v1/documents/20418000-0000-4000-8000-000000000005/content',
      }],
    })
  })

  await page.route(url => url.pathname === `/api/v1/applications/${APPLICATION_ID}/document-requests`, async route => {
    if (route.request().method() !== 'GET') return route.fallback()
    return fulfill(route, { batches: [] })
  })

  await page.route(url => url.pathname === `/api/v1/leasing/applications/${APPLICATION_ID}/documents/${DOCUMENT_ID}/status`, async route => {
    if (route.request().method() !== 'PATCH') return route.fallback()
    patchPayload = route.request().postDataJSON()
    patchRequestReceived = true
    await approvalResponseReleased
    documentStatus = 'approved'
    return fulfill(route, {
      application_id: APPLICATION_ID,
      document_id: DOCUMENT_ID,
      leasing_company_id: LEASING_COMPANY_ID,
      status: 'approved',
      message: 'Документ принят',
    })
  })

  return {
    getPatchPayload: () => patchPayload,
    isPatchRequestReceived: () => patchRequestReceived,
    releaseApprovalResponse: () => releaseApprovalResponse?.(),
  }
}

test('10.10: ЛК принимает pending-документ', async ({ page }) => {
  const mocks = await setupMocks(page)

  await page.goto(`/workspace/leasing-applications/${APPLICATION_ID}?leasing_company_id=${LEASING_COMPANY_ID}`, {
    waitUntil: 'domcontentloaded',
  })

  const documentRow = page.locator('li', { hasText: DOCUMENT_NAME })
  await expect(documentRow).toBeVisible()
  await expect(documentRow.getByRole('button', { name: 'Принять', exact: true })).toBeVisible()
  await documentRow.getByRole('button', { name: 'Принять', exact: true }).click()

  const dialog = page.getByRole('dialog', { name: 'Принять документ' })
  await expect(dialog).toBeVisible()
  const confirmButton = dialog.getByRole('button', { name: 'Принять', exact: true })
  await confirmButton.click()

  await expect.poll(mocks.isPatchRequestReceived).toBe(true)
  await expect(dialog.getByText('Принимаем…', { exact: true })).toBeVisible()
  await expect(confirmButton).toBeDisabled()

  mocks.releaseApprovalResponse()
  await expect.poll(mocks.getPatchPayload).toEqual({ status: 'approved' })
  await expect(page.getByText('Документ принят', { exact: true })).toBeVisible()
  await expect(documentRow.getByText('Принят', { exact: true })).toBeVisible()
})
