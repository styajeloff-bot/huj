import { expect, test, type Page, type Route } from '@playwright/test'
import type { CommerceApplicationItem } from '../../../features/commerce/types'

const USER_ID = '22282000-0000-4000-8000-000000000001'
const COMPANY_A = '22282000-0000-4000-8000-000000000002'
const COMPANY_B = '22282000-0000-4000-8000-000000000003'
const APPLICATION_ID = '22282000-0000-4000-8000-000000000005'
const VEHICLE_ID = '22282000-0000-4000-8000-000000000004'
const LCA_ID = '22282000-0000-4000-8000-000000000009'
const LCA_ID_2 = '22282000-0000-4000-8000-000000000010'

const step = (page: Page, number: number) => page.getByTestId('application-step-' + number)
const stepBubble = (page: Page, number: number) => page.getByTestId('application-step-bubble-' + number)
const stepLabel = (page: Page, number: number) => page.getByTestId('application-step-label-' + number)

const PRIMARY_BUBBLE_BACKGROUND = /bg-\[color:rgb\(var\(--storefront-primary-rgb,37_99_235\)\/var\(--tw-bg-opacity,1\)\)\]/
const PRIMARY_BUBBLE_TEXT = /text-\[color:var\(--storefront-text,#ffffff\)\]/
const PRIMARY_BUBBLE_RING = /ring-\[color:var\(--storefront-border,#dbeafe\)\]/
const PRIMARY_LABEL_TEXT = /text-\[color:var\(--storefront-primary,#2563eb\)\]/
const MUTED_BUBBLE_BACKGROUND = /bg-\[color:rgb\(var\(--storefront-surface-muted-rgb,229_231_235\)\/var\(--tw-bg-opacity,1\)\)\]/
const MUTED_TEXT = /text-\[color:var\(--storefront-text-muted,#4b5563\)\]/

async function expectStepState(page: Page, number: number, state: 'current' | 'completed' | 'upcoming') {
  const bubble = stepBubble(page, number)
  const label = stepLabel(page, number)
  await expect(step(page, number)).toHaveAttribute('data-state', state)
  if (state === 'completed') {
    const checkmark = bubble.locator('svg')
    await expect(checkmark).toBeVisible()
  } else {
    await expect(bubble).toHaveText(String(number))
    await expect(bubble.locator('svg')).toHaveCount(0)
  }

  if (state === 'current') {
    await expect(bubble).toHaveClass(PRIMARY_BUBBLE_BACKGROUND)
    await expect(bubble).toHaveClass(PRIMARY_BUBBLE_TEXT)
    await expect(bubble).toHaveClass(/ring-4/)
    await expect(bubble).toHaveClass(PRIMARY_BUBBLE_RING)
    await expect(label).toHaveClass(PRIMARY_LABEL_TEXT)
    return
  }

  await expect(bubble).toHaveClass(MUTED_BUBBLE_BACKGROUND)
  await expect(bubble).toHaveClass(MUTED_TEXT)
}

interface ApiFixturesOptions {
  leasingCompanyApplications?: Array<Record<string, unknown>>
  finalApprovalOffers?: Array<Record<string, unknown>>
}

async function installApiFixtures(page: Page, options: ApiFixturesOptions = {}) {
  await page.route(/https:\/\/(?:fonts\.googleapis\.com|fonts\.gstatic\.com|mc\.yandex\.ru|static\.me-talk\.ru)\//, route => route.abort())
  let lcaItems = options.leasingCompanyApplications ? [...options.leasingCompanyApplications] : []

  const fulfill = (route: Route, json: unknown, status = 200) => route.fulfill({
    status,
    json,
    headers: {
      'access-control-allow-origin': route.request().headers().origin || '*',
      'access-control-allow-credentials': 'true',
    },
  })

  await page.route(url => url.pathname.startsWith('/api/'), async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname.replace(/\/$/, '')
    const method = request.method()

    if (method === 'OPTIONS') {
      return route.fulfill({
        status: 204,
        headers: {
          'access-control-allow-origin': request.headers().origin || '*',
          'access-control-allow-credentials': 'true',
          'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
          'access-control-allow-headers': '*',
        },
      })
    }

    if (path === '/api/v1/auth/me') {
      return fulfill(route, { user: {
        id: USER_ID,
        role: 'client',
        sub_role: 'administrator',
        company_id: COMPANY_A,
        company_name: 'Основная компания A',
        name: 'Тестовый клиент',
        phone: '+79990000018',
        email: 'fixture@example.test',
        scopes: [],
        can_create_applications: true,
        can_view_applications: true,
      } })
    }
    if (path === '/api/v1/users/me/companies') {
      return fulfill(route, { companies: [
        { id: COMPANY_A, name: 'Основная компания A', inn: '7701000001', can_create_applications: true },
      ] })
    }
    if (path === '/api/v1/companies/' + COMPANY_A + '/profile' || path === '/api/v1/companies/profile') {
      return fulfill(route, {
        id: COMPANY_A,
        name: 'Основная компания A',
        inn: '7701000001',
        legal_address: 'Москва, ул. Тестовая, 1',
      })
    }
    if (path === '/api/v1/applications/' + APPLICATION_ID && method === 'GET') {
      return fulfill(route, {
        id: APPLICATION_ID,
        status: 'active',
        company_id: COMPANY_A,
        company: { id: COMPANY_A, name: 'Основная компания A', inn: '7701000001' },
        items: [{
          id: 'item-1',
          type: 'vehicle',
          title: 'Тестовый автомобиль',
          price: '2000000',
          quantity: 1,
        }],
        items_count: 1,
        total_items_price: '2000000',
        vehicles: [],
        questionnaire: {
          legal_address: 'Москва, ул. Тестовая, 1',
          actual_address: 'Москва, ул. Тестовая, 1',
          actual_address_same_as_legal: true,
          contacts: [{ name: 'Тестовый клиент', phone: '+79990000018', email: 'fixture@example.test', position: '' }],
        },
        leasing_company_applications: lcaItems,
      })
    }
    if (path === '/api/v1/leasing-company-applications' && method === 'GET') {
      return fulfill(route, { items: lcaItems })
    }
    if (path === '/api/v1/applications/' + APPLICATION_ID + '/leasing-responses') {
      return fulfill(route, {
        approval_offers: {
          preliminary: [],
          final: options.finalApprovalOffers || [],
        },
      })
    }
    if (path === '/api/v1/applications/leasing-purposes') {
      return fulfill(route, { purposes: [{ purpose_name: 'business', purpose_display_name: 'Для бизнеса' }] })
    }
    if (path === '/api/v1/applications/leasing-regions') {
      return fulfill(route, { regions: [{ region_name: 'moscow', region_display_name: 'Москва', region_number: '77' }] })
    }
    if (path === '/api/v1/applications/' + APPLICATION_ID + '/sopd-signer-candidates') {
      return fulfill(route, { candidates: [] })
    }

    return fulfill(route, {})
  })

  return {
    setLcaItems: (items: Array<Record<string, unknown>>) => {
      lcaItems = [...items]
    },
  }
}

test.describe('Bitrix 22282-4 — автоматическое переключение шагов заявки при смене статуса', () => {
  test.use({ viewport: { width: 1280, height: 900 }, navigationTimeout: 30_000 })

  test('при открытии распределенной заявки без указания шага автоматически открывается шаг 3 (Выбранные ЛК)', async ({ page }) => {
    const lca = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'submitted',
    }
    await installApiFixtures(page, { leasingCompanyApplications: [lca] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=3'))
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'current')
    await expectStepState(page, 4, 'upcoming')
    await expect(stepLabel(page, 3)).toHaveText('Выбранные ЛК')
    await expect(page.getByRole('heading', { name: 'Предварительное одобрение' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Одобрение' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Назначенные лизинговые компании' })).toBeVisible()
  })

  test('при открытии заявки с предварительными офферами автоматически открывается шаг 4 (Предварительные)', async ({ page }) => {
    const lca1 = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'submitted',
    }
    const lca2 = {
      id: LCA_ID_2,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'approved_scoring',
    }
    await installApiFixtures(page, { leasingCompanyApplications: [lca1, lca2] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=4'))
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'current')
  })

  test('при обновлении статуса ЛК на лету происходит автопереход с шага 3 на шаг 4', async ({ page }) => {
    const lca1 = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'submitted',
      created_at: '2026-09-23T12:00:00Z',
    }
    const lca2 = {
      id: LCA_ID_2,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'submitted',
      created_at: '2026-09-23T12:00:00Z',
    }
    const api = await installApiFixtures(page, { leasingCompanyApplications: [lca1, lca2] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=3'))
    await expectStepState(page, 3, 'current')

    // Вторая ЛК одобрила скоринг — статус обновляется до approved_scoring (шаг 4)
    const approvedLca2 = {
      ...lca2,
      status: 'approved_scoring',
      updated_at: '2026-09-23T12:05:00Z',
    }
    api.setLcaItems([lca1, approvedLca2])

    // Нажимаем кнопку "Обновить"
    await page.getByRole('button', { name: 'Обновить' }).click()

    // Ждем обновления шага на 4
    await expect.poll(() => page.url(), { timeout: 10000 }).toMatch(/step=4/)
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'current')
  })

  test('при открытии заявки с итоговым КП автоматически открывается шаг 5 (Итоговое)', async ({ page }) => {
    const lca1 = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'submitted',
    }
    const lca2 = {
      id: LCA_ID_2,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'approved_final',
    }
    await installApiFixtures(page, { leasingCompanyApplications: [lca1, lca2] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=5'))
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'completed')
    await expectStepState(page, 5, 'current')
    await expectStepState(page, 6, 'upcoming')
    await expectStepState(page, 7, 'upcoming')
    await expect(page.getByRole('heading', { name: 'Итоговое одобрение' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Назначенные лизинговые компании без итогового КП' })).toBeVisible()
  })

  test('на шаге 7 «Сделка» отображается выбранная ЛК и скрыта таблица карточек', async ({ page }) => {
    const lca = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      leasing_company_name: 'Тестовая лизинговая',
      status: 'deal',
    }
    const proposalId = '22282000-0000-4000-8000-000000000011'
    await installApiFixtures(page, {
      leasingCompanyApplications: [lca],
      finalApprovalOffers: [{
        lca: {
          id: LCA_ID,
          application_id: APPLICATION_ID,
          leasing_company_id: COMPANY_A,
          status: 'deal',
        },
        leasing_company: { id: COMPANY_A, name: 'Тестовая лизинговая', inn: '7701000001' },
        proposal: {
          id: proposalId,
          leasing_company_application_id: LCA_ID,
          kind: 'final',
          position: 1,
          monthly_payment: '50000',
          diff: [],
        },
      }],
    })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=7'))
    await expect(page.getByRole('heading', { name: 'Выбранная лизинговая компания' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Выбрать', exact: true })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: /Офферы|Назначенные/ })).toHaveCount(0)
  })

  test('ручной переход пользователя на более ранний доступный шаг не сбрасывается при рутинном опросе', async ({ page }) => {
    const lca1 = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'submitted',
      created_at: '2026-09-23T12:00:00Z',
    }
    const lca2 = {
      id: LCA_ID_2,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'approved_scoring',
      created_at: '2026-09-23T12:00:00Z',
    }
    await installApiFixtures(page, { leasingCompanyApplications: [lca1, lca2] })

    // Открываем заявку — автоматически попадаем на шаг 4
    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=4'))
    await expectStepState(page, 4, 'current')

    // Пользователь вручную кликает на шаг 3 (Выбранные ЛК)
    await step(page, 3).click()
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=3'))
    await expectStepState(page, 3, 'current')
    await expect(page.getByRole('heading', { name: 'Назначенные лизинговые компании' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Предварительное одобрение' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Одобрение' })).toHaveCount(0)

    // Срабатывает обновление (опрос), но состав статусов не изменился
    await page.getByRole('button', { name: 'Обновить' }).click()

    // Пользователь должен остаться на шаге 3, его выбор не сбрасывается
    await page.waitForTimeout(500)
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=3'))
    await expectStepState(page, 3, 'current')
  })

  test('seven permanent numbered stages remain visible without documents at supported desktop widths', async ({ page }) => {
    await installApiFixtures(page, { leasingCompanyApplications: [{
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'approved_final',
    }] })

    for (const width of [768, 1280, 1440]) {
      await page.setViewportSize({ width, height: 900 })
      await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })
      await expect(page.locator('[data-testid^="application-step-"]:not([data-testid^="application-step-bubble-"]):not([data-testid^="application-step-label-"])')).toHaveCount(7)
      await expect(page.getByTestId('application-step-documents')).toHaveCount(0)
      for (const number of [1, 2, 3, 4, 5, 6, 7]) {
        await expect(step(page, number)).toBeVisible()
      }
      const centers = await page.locator('[data-testid^="application-step-bubble-"]').evaluateAll(bubbles =>
        bubbles.map(bubble => {
          const rect = bubble.getBoundingClientRect()
          return rect.left + rect.width / 2
        }),
      )
      expect(centers).toHaveLength(7)
      expect(centers.every((center, index) => index === 0 || center > centers[index - 1])).toBe(true)
    }
  })

  test('actual approved_scoring without display_status falls back to the actual status and does not show documents', async ({ page }) => {
    await installApiFixtures(page, { leasingCompanyApplications: [{
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'approved_scoring',
    }] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=4'))
    await expect(page.getByTestId('application-step-documents')).toHaveCount(0)
    await expectStepState(page, 4, 'current')
  })

  test('raw approved_scoring with display_status=documents_required is available in both preliminary and document sections', async ({ page }) => {
    const leasingCompanyName = 'ЛК с запросом документов'
    await installApiFixtures(page, { leasingCompanyApplications: [{
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      leasing_company_name: leasingCompanyName,
      status: 'approved_scoring',
      display_status: 'documents_required',
    }] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })

    await expect(page.getByTestId('application-step-documents')).toHaveAttribute('data-state', 'current')
    await expect(page.getByTestId('application-step-bubble-documents')).toHaveText('!')
    await expect(step(page, 4)).toBeVisible()

    const documentsSection = page.locator('section').filter({
      has: page.getByRole('heading', { name: 'Офферы: Доп. документы' }),
    })
    const documentCard = documentsSection.locator('article').filter({
      has: page.getByRole('heading', { name: leasingCompanyName }),
    })
    await expect(documentCard).toBeVisible()
    await expect(documentCard.getByText('Запрос дополнительных документов', { exact: true })).toBeVisible()

    await step(page, 4).click()
    await expectStepState(page, 4, 'current')
    await expect(page.getByRole('heading', { name: 'Предварительное одобрение' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Назначенные лизинговые компании без КП' })).toBeVisible()
  })

  test('documents from one LC remain visible without pulling back a final view from another LC', async ({ page }) => {
    const final = { id: LCA_ID, application_id: APPLICATION_ID, leasing_company_id: COMPANY_A, status: 'approved_final' }
    const documents = {
      id: LCA_ID_2,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_B,
      status: 'approved_scoring',
      display_status: 'under_review_with_docs',
    }
    const api = await installApiFixtures(page, { leasingCompanyApplications: [final] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=5'))
    await expectStepState(page, 5, 'current')

    api.setLcaItems([final, documents])
    await page.getByRole('button', { name: 'Обновить' }).click()

    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=5'))
    await expect(page.getByTestId('application-step-documents')).toBeVisible()
    await expect(page.getByTestId('application-step-documents')).toHaveAttribute('data-state', 'completed')
    await expect(page.getByTestId('application-step-bubble-documents')).toHaveText('!')
    await expect(page.getByTestId('application-step-bubble-documents').locator('svg')).toHaveCount(0)
    const documentsBox = await page.getByTestId('application-step-documents').boundingBox()
    const finalBox = await page.getByTestId('application-step-5').boundingBox()
    expect(documentsBox).not.toBeNull()
    expect(finalBox).not.toBeNull()
    expect(documentsBox!.x).toBeLessThan(finalBox!.x)
    await expectStepState(page, 5, 'current')
  })

  test('documents disappearance falls back to the latest available section with a stale-link notice', async ({ page }) => {
    const documents = { id: LCA_ID, application_id: APPLICATION_ID, leasing_company_id: COMPANY_A, status: 'documents_required' }
    const final = { id: LCA_ID_2, application_id: APPLICATION_ID, leasing_company_id: COMPANY_A, status: 'approved_final' }
    const api = await installApiFixtures(page, { leasingCompanyApplications: [documents, final] })

    await page.goto('/application/' + APPLICATION_ID + '?section=documents', { waitUntil: 'domcontentloaded' })
    await expect(page.getByTestId('application-step-documents')).toHaveAttribute('data-state', 'current')

    api.setLcaItems([final])
    await page.getByRole('button', { name: 'Обновить' }).click()

    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=5'))
    await expectStepState(page, 5, 'current')
    await expect(page.getByRole('status').filter({ hasText: 'Открыт актуальный доступный раздел' })).toBeVisible()
    await expect(page.getByTestId('application-step-documents')).toHaveCount(0)
  })

  test('stale section=documents opens the latest available section and explains the fallback', async ({ page }) => {
    await installApiFixtures(page, { leasingCompanyApplications: [{
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'approved_final',
    }] })

    await page.goto('/application/' + APPLICATION_ID + '?section=documents', { waitUntil: 'domcontentloaded' })

    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=5'))
    await expectStepState(page, 5, 'current')
    await expect(page.getByRole('status').filter({ hasText: 'Открыт актуальный доступный раздел' })).toBeVisible()
  })

  test('при возврате назад из шага 4 на шаги 2 и 1 пройденные шаги сохраняют галочки и не становятся цифрами', async ({ page }) => {
    const lca1 = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'submitted',
    }
    const lca2 = {
      id: LCA_ID_2,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'approved_scoring',
    }
    await installApiFixtures(page, { leasingCompanyApplications: [lca1, lca2] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=4'))
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'current')
    await expectStepState(page, 5, 'upcoming')

    // Возврат на шаг 2 («О компании»)
    await step(page, 2).click()
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=company'))
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'current')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'upcoming')

    // Возврат на шаг 1 («Анкета»)
    await step(page, 1).click()
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=1'))
    await expectStepState(page, 1, 'current')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'upcoming')

    // Переход вперёд на шаг 4 («Предварительные»)
    await step(page, 4).click()
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=4'))
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'current')
    await expectStepState(page, 5, 'upcoming')
  })

  test('при возврате назад из шага 5 на шаг 2 все пройденные шаги 1, 3, 4 сохраняют галочки', async ({ page }) => {
    const lca1 = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'submitted',
    }
    const lca2 = {
      id: LCA_ID_2,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'approved_final',
    }
    await installApiFixtures(page, { leasingCompanyApplications: [lca1, lca2] })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=5'))
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'completed')
    await expectStepState(page, 5, 'current')
    await expectStepState(page, 6, 'upcoming')

    // Возврат на шаг 2 («О компании»)
    await step(page, 2).click()
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=company'))
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'current')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'completed')
    await expectStepState(page, 5, 'upcoming')

    // Возврат на шаг 1 («Анкета»)
    await step(page, 1).click()
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=1'))
    await expectStepState(page, 1, 'current')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'completed')
    await expectStepState(page, 5, 'upcoming')
  })

  test('на шаге 6 «Выбор ЛК» отображается выбранная компания, карточки удалены, и доступен возврат на шаг 3', async ({ page }) => {
    const lca1 = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      leasing_company_name: 'Тестовая ЛК 1',
      status: 'submitted',
    }
    const lca2 = {
      id: LCA_ID_2,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_B,
      leasing_company_name: 'Тестовая ЛК 2',
      status: 'selected_lc',
    }
    const proposalId = '22282000-0000-4000-8000-000000000015'
    await installApiFixtures(page, {
      leasingCompanyApplications: [lca1, lca2],
      finalApprovalOffers: [{
        lca: lca2,
        leasing_company: { id: COMPANY_B, name: 'Тестовая ЛК 2', inn: '7701000002' },
        proposal: {
          id: proposalId,
          leasing_company_application_id: LCA_ID_2,
          kind: 'final',
          position: 1,
          monthly_payment: '60000',
          diff: [],
        },
      }],
    })

    await page.goto('/application/' + APPLICATION_ID, { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=6'))
    await expectStepState(page, 6, 'current')
    await expect(page.getByRole('heading', { name: 'Выбранная лизинговая компания' })).toBeVisible()
    await expect(page.getByRole('heading', { name: /Офферы|Назначенные/ })).toHaveCount(0)

    // Клик на шаг 3 («Выбранные ЛК») не заблокирован
    await step(page, 3).click()
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=3'))
    await expectStepState(page, 3, 'current')
    await expect(page.getByRole('heading', { name: 'Назначенные лизинговые компании' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Одобрение' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Выбранная лизинговая компания' })).toHaveCount(0)
  })
})