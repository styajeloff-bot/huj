import { expect, test, type Page, type Route } from '@playwright/test'

const APPLICATION_ID = '22282000-0000-4000-8000-000000000005'
const LEASING_COMPANY_ID = '679a4e4d-8fcc-4cf2-9d1c-af927988ab2d'
const LCA_ID = '22282000-0000-4000-8000-000000000009'

test.use({
  baseURL: 'http://localhost',
  viewport: { width: 1280, height: 900 },
  navigationTimeout: 30_000,
})

let authCookies: Array<{ name: string; value: string; domain: string; path: string }> = []

test.beforeAll(async ({ playwright }) => {
  const request = await playwright.request.newContext({ baseURL: 'http://localhost' })
  const login = await request.post('/api/v1/auth/login', { data: { phone: '+76661234571' } })
  expect([200, 403]).toContain(login.status())
  const verification = await request.post('/api/v1/auth/verify-phone', {
    data: { phone: '+76661234571', code: '0000' },
  })
  expect(verification.status()).toBe(200)
  const state = await request.storageState()
  authCookies = state.cookies
  await request.dispose()
})

test.beforeEach(async ({ context }) => {
  await context.addCookies(authCookies)
})

interface MockOptions {
  status: string
  finalSubmitted?: boolean
}

async function setupMocks(page: Page, options: MockOptions) {
  const fulfill = (route: Route, json: unknown, status = 200) =>
    route.fulfill({
      status,
      json,
      headers: {
        'access-control-allow-origin': route.request().headers().origin || '*',
        'access-control-allow-credentials': 'true',
      },
    })

  await page.route(`**/api/v1/leasing/applications/${APPLICATION_ID}/response**`, async (route) => {
    return fulfill(route, {
      link: {
        id: LCA_ID,
        application_id: APPLICATION_ID,
        leasing_company_id: LEASING_COMPANY_ID,
        status: options.status,
        submitted_at: '2026-09-24T10:00:00Z',
      },
      application: {
        id: APPLICATION_ID,
        display_number: '22282-TEST',
        status: 'active',
        company_name: 'ООО Тест Клиент',
        company_inn: '7712345678',
        leasing_company_name: 'Альфа Лизинг',
        vehicles: [],
      },
      proposals: options.finalSubmitted
        ? [
            {
              id: '22282000-0000-4000-8000-000000000099',
              kind: 'final',
              status: 'submitted',
              monthly_payment: 50000,
              lease_term_months: 36,
              advance_percent: 20,
            },
          ]
        : [],
      can_review: true,
      can_confirm_deal: options.status === 'selected_lc',
    })
  })

  await page.route(`**/api/v1/leasing/applications/${APPLICATION_ID}/documents**`, async (route) => {
    return fulfill(route, { documents: [] })
  })
}

test.describe('Отображение статуса заявки в кабинете ЛК (Bitrix #22282-3)', () => {
  test('При статусе selected_lc отображается текст «Выбрана ЛК» с фиолетовым бейджем', async ({ page }) => {
    await setupMocks(page, { status: 'selected_lc', finalSubmitted: true })

    await page.goto(`/workspace/leasing-applications/${APPLICATION_ID}?leasing_company_id=${LEASING_COMPANY_ID}`, {
      waitUntil: 'domcontentloaded',
    })

    // Проверяем верхний бейдж статуса в заголовке заявки
    const statusBadge = page.locator('span.rounded-full', { hasText: 'Выбрана ЛК' })
    await expect(statusBadge).toBeVisible()
    await expect(statusBadge).toHaveClass(/bg-purple-100/)
    await expect(statusBadge).toHaveClass(/text-purple-800/)

    // Убеждаемся, что сырой технический код "selected_lc" нигде не выводится
    await expect(page.getByText('selected_lc')).toHaveCount(0)

    // Переключаемся на вкладку «Действия»
    await page.getByRole('button', { name: 'Действия' }).click()

    // Проверяем блок итогового решения
    const decisionSection = page.locator('section', { hasText: 'Ответ отправлен клиенту' })
    await expect(decisionSection).toBeVisible()
    await expect(decisionSection.locator('strong', { hasText: 'Выбрана ЛК' })).toBeVisible()
  })

  test('При статусе submitted отображается «Подана»', async ({ page }) => {
    await setupMocks(page, { status: 'submitted' })

    await page.goto(`/workspace/leasing-applications/${APPLICATION_ID}?leasing_company_id=${LEASING_COMPANY_ID}`, {
      waitUntil: 'domcontentloaded',
    })

    const statusBadge = page.locator('span.rounded-full', { hasText: 'Подана' })
    await expect(statusBadge).toBeVisible()
    await expect(statusBadge).toHaveClass(/bg-blue-100/)
    await expect(statusBadge).toHaveClass(/text-blue-800/)
  })
})
