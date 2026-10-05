import { expect, test, type Page, type Route } from '@playwright/test'
import { writeFile } from 'node:fs/promises'
import type { AccountingReport } from '../../../features/checkout/composables/useCheckoutAccounting'
import type { CommerceApplicationItem, CommerceCheckoutLine } from '../../../features/commerce/types'

// Browser APIs are fixtures; the Nuxt server only needs its usual default
// storefront response for SSR. No test sends an application or an email.
const USER_ID = '22218000-0000-4000-8000-000000000001'
const COMPANY_A = '22218000-0000-4000-8000-000000000002'
const COMPANY_B = '22218000-0000-4000-8000-000000000003'
const VEHICLE_ID = '22218000-0000-4000-8000-000000000004'
const APPLICATION_ID = '22218000-0000-4000-8000-000000000005'
const LINE_ID = '22218000-0000-4000-8000-000000000006'
const CART_ID = '22218000-0000-4000-8000-000000000007'
const CREATE_KEY = '22218000-0000-4000-8000-000000000008'
const LCA_ID = '22218000-0000-4000-8000-000000000009'
const STORAGE_KEY = 'checkout-state:u' + USER_ID
const COMPANY_B_INN = '7701000002'
const ADDRESS_A = 'Москва, улица Основная, дом 1'
const ADDRESS_B = 'Саратов, улица Компании Б, дом 18'
const MANUAL_ADDRESS = 'Самара, улица Введённая вручную, дом 25'
const LOADING_REPORT = 'Загружаем данные компании и бухгалтерскую отчётность…'

const calculation = {
  total_amount: 1_740_000,
  down_payment: 348_000,
  down_payment_percent: 20,
  lease_term_months: 36,
  buyout_amount: 0,
  calculation: {
    monthlyPayment: 52_444,
    rate: 21,
    totalCost: 2_235_973,
    totalInterest: 147_973,
    buyoutAmount: 0,
    vatRefund: 0,
    profitTaxSavings: 0,
    totalSavings: 0,
  },
}

const companyB = {
  id: COMPANY_B,
  name: 'Компания Б — проверка 22218',
  full_name: 'Общество с ограниченной ответственностью Компания Б — проверка 22218',
  short_name: 'Компания Б — проверка 22218',
  inn: COMPANY_B_INN,
  kpp: '770101001',
  ogrn: '1027700000002',
  legal_address: ADDRESS_B,
  enrichment_status: 'success',
  status: 'ACTIVE',
  founders: [],
}

const cartItem = {
  cart_id: CART_ID,
  vehicle_id: VEHICLE_ID,
  mark_name: 'BMW',
  model_name: 'X3',
  year: 2025,
  base_price: 1_740_000,
  quantity: 1,
  is_selected: true,
  is_model_order: false,
  images: [],
  equipments: [],
  services: [],
  comment: '',
  has_support: false,
  applicable_support_programs: [],
}

const checkoutLine: CommerceCheckoutLine = {
  item: {
    ref: { type: 'vehicle', id: VEHICLE_ID },
    title: 'BMW X3',
    subtitle: null,
    image_url: null,
    detail_url: '/cars/' + VEHICLE_ID,
    price: '1740000',
    currency_code: 'RUB',
    availability: 'available',
    manufacturer: 'BMW',
    model: 'X3',
    modification: null,
    year: 2025,
    facts: [],
    capabilities: { can_lease: true, can_buy: true, can_preorder: true },
  },
  quantity: 1,
  custom_price: null,
  comment: '',
  equipments: [],
  services: [],
  leasing_purpose: null,
  leasing_purpose_comment: null,
  regions: [],
}

const applicationItem: CommerceApplicationItem = {
  id: LINE_ID,
  type: 'vehicle',
  item_id: VEHICLE_ID,
  title: 'BMW X3',
  quantity: 1,
  unit_price: '1740000',
  total_price: '1740000',
  currency_code: 'RUB',
  status: 'active',
  image_url: null,
  detail_url: null,
  snapshot: null,
  leasing_purpose: null,
  regions: [],
  region: null,
  comment: null,
}

const accounting: AccountingReport = {
  inn: COMPANY_B_INN,
  company_id: null,
  provider_name: 'Fixture FNS',
  period_years: [2025, 2024],
  organization: null,
  balance_sheet: [
    { code: '1600', name: 'Активы', values: { '2025': 441_332_000, '2024': 400_000_000 } },
    { code: '1300', name: 'Капитал', values: { '2025': 354_810_000, '2024': 300_000_000 } },
  ],
  financial_result: [
    { code: '2110', name: 'Выручка', values: { '2025': 3_709_785_000, '2024': 3_000_000_000 } },
    { code: '2400', name: 'Чистая прибыль', values: { '2025': 199_634_000, '2024': 100_000_000 } },
  ],
  cash_flow: [],
  capital_change: [],
  audit_report: null,
  clarification_url: null,
  year_files: [],
  computed_ratios: [],
  fetch_status: 'success',
  last_fetch_at: '2026-09-08T00:00:00Z',
  cached: false,
  stale: false,
}

const deferred = () => {
  let release!: () => void
  const promise = new Promise<void>((resolve) => { release = resolve })
  return { promise, release }
}

interface BrowserDiagnostics {
  pageErrors: string[]
  consoleErrors: Array<{ text: string, url: string }>
}
const browserDiagnostics = new WeakMap<Page, BrowserDiagnostics>()

interface ApiFixturesOptions {
  profileGate?: Promise<void>
  accountingGate?: Promise<void>
  savedAddress?: string
  leasingCompanyApplications?: Array<Record<string, unknown>>
}

async function installApiFixtures(page: Page, options: ApiFixturesOptions = {}) {
  await page.route(/https:\/\/(?:mc\.yandex\.ru|static\.me-talk\.ru)\//, route => route.abort())
  const diagnostics: BrowserDiagnostics = { pageErrors: [], consoleErrors: [] }
  browserDiagnostics.set(page, diagnostics)
  page.on('pageerror', error => diagnostics.pageErrors.push(error.message))
  page.on('console', message => {
    if (message.type() === 'error') diagnostics.consoleErrors.push({
      text: message.text(),
      url: message.location().url,
    })
  })
  const requests: Array<{ path: string, method: string, body: unknown, key?: string }> = []
  const unexpectedWrites: string[] = []
  let items = structuredClone(applicationItem)
  let savedQuestionnaire: Record<string, unknown> = options.savedAddress ? {
    legal_address: options.savedAddress,
    actual_address: options.savedAddress,
    actual_address_same_as_legal: true,
    contacts: [{ name: 'Тестовый клиент', phone: '+79990000018', email: 'fixture@example.test', position: '' }],
  } : {}
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
      await route.fulfill({
        status: 204,
        headers: {
          'access-control-allow-origin': request.headers().origin || '*',
          'access-control-allow-credentials': 'true',
          'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
          'access-control-allow-headers': '*',
        },
      })
      return
    }
    let body: unknown = null
    if (request.postData()) {
      try { body = request.postDataJSON() } catch { body = request.postData() }
    }
    requests.push({ path, method, body, key: request.headers()['idempotency-key'] })

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
    if (path === '/api/v1/users/me/companies') return fulfill(route, { companies: [
      { id: COMPANY_A, name: 'Основная компания A', inn: '7701000001', can_create_applications: true },
      { id: COMPANY_B, name: companyB.name, inn: COMPANY_B_INN, can_create_applications: true },
    ] })
    if (path === '/api/v1/users/me/company-select-history') {
      return fulfill(route, { company_id: COMPANY_B })
    }
    if (path === '/api/v1/companies/' + COMPANY_B + '/profile') {
      await options.profileGate
      return fulfill(route, companyB)
    }
    if (path === '/api/v1/companies/profile' || path === '/api/v1/companies/' + COMPANY_A + '/profile') {
      return fulfill(route, { ...companyB, id: COMPANY_A, name: 'Основная компания A', inn: '7701000001', legal_address: ADDRESS_A })
    }
    if (path === '/api/v1/accounting/' + COMPANY_B_INN) {
      await options.accountingGate
      return fulfill(route, accounting)
    }
    if (path === '/api/v1/cart') return fulfill(route, { items: [cartItem], count: 1 })
    if (path === '/api/v1/calculator/calculate') return fulfill(route, {
      calculation: calculation.calculation,
      support: null,
      support_per_vehicle: [],
      support_per_program: [],
      calculations_per_vehicle: [],
    })
    if (path === '/api/v1/calculator/support-status') return fulfill(route, { items: {
      [VEHICLE_ID]: { has_support: false, applicable_support_programs: [], eligible_program_ids: [] },
    } })
    if (path === '/api/v1/cars/check-availability') {
      return fulfill(route, { statuses: [{ vehicle_id: VEHICLE_ID, status: 'available' }] })
    }
    if (path === '/api/v1/cars/available-counts') {
      return fulfill(route, { counts: [{ vehicle_id: VEHICLE_ID, available_count: 1 }] })
    }
    if (path === '/api/v1/purchases/my-vehicle-ids') return fulfill(route, { vehicles: [] })
    if (path === '/api/v1/commerce/leasing-applications' && method === 'POST') {
      return fulfill(route, { application_id: APPLICATION_ID }, 201)
    }
    if (path === '/api/v1/applications/' + APPLICATION_ID + '/items' && method === 'PUT') {
      const update = (body as { items: Array<Partial<CommerceApplicationItem>> }).items[0]
      items = { ...items, ...update }
      return fulfill(route, { ok: true })
    }
    if (path === '/api/v1/applications/' + APPLICATION_ID && method === 'GET') {
      return fulfill(route, {
        id: APPLICATION_ID,
        status: 'draft',
        company_id: COMPANY_B,
        company: { id: COMPANY_B, name: companyB.name, inn: COMPANY_B_INN },
        items: [items],
        items_count: 1,
        total_items_price: '1740000',
        vehicles: [],
        questionnaire: savedQuestionnaire,
        leasing_company_applications: options.leasingCompanyApplications || [],
      })
    }
    if (path === '/api/v1/leasing-company-applications' && method === 'GET') {
      return fulfill(route, { items: options.leasingCompanyApplications || [] })
    }
    if (path === '/api/v1/applications/' + APPLICATION_ID + '/leasing-responses') {
      return fulfill(route, { approval_offers: { preliminary: [], final: [] } })
    }
    if (path === '/api/v1/applications/leasing-purposes') return fulfill(route, {
      purposes: [{ purpose_name: 'business', purpose_display_name: 'Для бизнеса' }],
    })
    if (path === '/api/v1/applications/leasing-regions') return fulfill(route, {
      regions: [{ region_name: 'saratov', region_display_name: 'Саратовская область', region_number: '64' }],
    })
    if (path === '/api/v1/applications/' + APPLICATION_ID + '/questionnaire' && method === 'PUT') {
      savedQuestionnaire = body as Record<string, unknown>
      return fulfill(route, { ok: true })
    }
    if (path === '/api/v1/applications/' + APPLICATION_ID + '/sopd-status') {
      return fulfill(route, { items: [] })
    }
    if (path.endsWith('/sopd-signer-candidates')) return fulfill(route, { candidates: [] })
    if (path === '/api/v1/notifications') return fulfill(route, {
      notifications: [], pagination: { page: 1, limit: 20, total: 0, pages: 0 }, total_count: 0, unread_count: 0,
    })
    if (method === 'GET' && /\/(favorites|documents|signatures|equipments|services|cart-items)(\/|$)/.test(path)) {
      return fulfill(route, { items: [], favorites: [], documents: [], signatures: [], equipments: [], services: [], count: 0 })
    }
    if (method === 'GET' && /\/section-visibility\/public$/.test(path)) {
      return fulfill(route, { sections: [
        { key: 'cars', is_visible: true },
        { key: 'special_equipment', is_visible: false },
      ] })
    }
    // All browser API traffic stays inside this fixture, including unexpected
    // writes; an unhandled action can never create a real order or send SMS.
    if (method !== 'GET') unexpectedWrites.push(method + ' ' + path)
    return fulfill(route, { detail: 'No fixture for ' + method + ' ' + path }, 404)
  })

  const initialState = {
    selectedCompanyId: COMPANY_B,
    selectedApplicationCompany: null,
    calculation,
    commerceItems: [checkoutLine],
    vehicles: [],
    applicationItems: [],
    applicationCreateIdempotencyKey: CREATE_KEY,
    questionnaireData: {},
    currentStep: 1,
  }
  await page.addInitScript(({ key, state }) => {
    // Seed once per test context. A reload must restore the app's own saved
    // state, rather than repairing a broken reload with another test write.
    if (!sessionStorage.getItem('fixture-22218-seeded')) {
      localStorage.setItem(key, JSON.stringify(state))
      sessionStorage.setItem('fixture-22218-seeded', 'true')
    }
  }, { key: STORAGE_KEY, state: initialState })

  return { requests, unexpectedWrites }
}

const conditionsPanel = (page: Page) => page.locator('section').filter({
  has: page.getByRole('heading', { name: 'Запрашиваемые условия', exact: true }),
})
const companyPanel = (page: Page) => page.locator('section').filter({
  has: page.getByRole('heading', { name: 'О компании', exact: true }),
})
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
  await expect(label).toHaveClass(MUTED_TEXT)
  await expect(bubble).not.toHaveClass(PRIMARY_BUBBLE_BACKGROUND)
  await expect(bubble).not.toHaveClass(PRIMARY_BUBBLE_TEXT)
  await expect(bubble).not.toHaveClass(/ring-4/)
  await expect(bubble).not.toHaveClass(PRIMARY_BUBBLE_RING)
  await expect(label).not.toHaveClass(PRIMARY_LABEL_TEXT)
}

async function expectConditions(page: Page) {
  const panel = conditionsPanel(page)
  await expect(panel).toBeVisible()
  await expect(panel).toContainText(/52\s*444\s*₽/)
  await expect(panel).toContainText(/1\s*740\s*000\s*₽/)
  await expect(panel).toContainText(/2\s*235\s*973\s*₽/)
  await expect(panel).toContainText('20%')
  await expect(panel).toContainText('36 мес.')
}

async function expectReport(page: Page) {
  const panel = companyPanel(page)
  await expect(panel.getByRole('button', { name: 'Бухгалтерская отчётность', exact: true })).toBeVisible()
  await expect(panel.getByText('Бухгалтерский баланс (форма 1)', { exact: true })).toBeVisible()
  await expect(panel.getByText(/3\s*709\s*785\s*000\s*₽/)).toBeVisible()
  await expect(panel.locator('canvas')).toHaveCount(2)
  await expect.poll(() => panel.locator('canvas').evaluateAll((nodes) => nodes.every((node) => {
    const canvas = node as HTMLCanvasElement
    const context = canvas.getContext('2d')
    return canvas.width > 0 && canvas.height > 0 && Boolean(context
      ?.getImageData(0, 0, canvas.width, canvas.height).data.some((value, index) => index % 4 === 3 && value > 0))
  }))).toBe(true)
  await panel.getByRole('button', { name: '2024', exact: true }).click()
  await expect(panel.getByText(/3\s*000\s*000\s*000\s*₽/)).toBeVisible()
  await panel.getByRole('button', { name: '2025', exact: true }).click()
  // Chart.js animates through intermediate values; wait for unchanged canvas
  // pixels so the captured report represents the final plotted amounts.
  let previousPixels = ''
  await expect.poll(async () => {
    const pixels = await panel.locator('canvas').evaluateAll(nodes => nodes
      .map(node => (node as HTMLCanvasElement).toDataURL()).join('|'))
    const stable = pixels === previousPixels
    previousPixels = pixels
    return stable
  }).toBe(true)
}

test.afterEach(async ({ page }, testInfo) => {
  const diagnostics = browserDiagnostics.get(page)
  if (!diagnostics) return
  const diagnosticsPath = testInfo.outputPath('browser-diagnostics.json')
  await writeFile(diagnosticsPath, JSON.stringify(diagnostics, null, 2))
  await testInfo.attach('browser-diagnostics.json', {
    path: diagnosticsPath,
    contentType: 'application/json',
  })
  expect(diagnostics.pageErrors, 'Unexpected browser runtime exceptions').toEqual([])
})

test.describe('Bitrix 22218 — оформление заявки с бухгалтерской отчётностью', () => {
  test.use({ navigationTimeout: 30_000 })

  test('корзина → отчётность → reload → транспорт → адрес компании заявки', async ({ page }, testInfo) => {
    const profile = deferred()
    const report = deferred()
    const api = await installApiFixtures(page, { profileGate: profile.promise, accountingGate: report.promise })
    await page.goto('/cart', { waitUntil: 'domcontentloaded' })
    const specialOffer = page.getByRole('button', { name: 'Получить специальное предложение', exact: true })
    await expect(specialOffer).toBeEnabled({ timeout: 15_000 })
    await expect(page.getByRole('button', { name: 'Оформить с онлайн оплатой', exact: true })).toHaveCount(0)
    await expect(page.getByRole('link', { name: 'Продолжить выбор', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Скачать PDF', exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Отправить на почту', exact: true })).toBeVisible()

    // The cart can expose its CTA before its initial asynchronous calculation
    // finishes. Start checkout from the completed quote displayed to the user.
    await expect(page.getByText(/^52\s*444\s*₽$/).filter({ visible: true }).first()).toBeVisible()
    await specialOffer.click()
    await expect(page).toHaveURL(/\/application\/new$/)
    await expect(companyPanel(page).getByText(LOADING_REPORT, { exact: true })).toBeVisible()
    await expectConditions(page)
    await page.screenshot({ path: testInfo.outputPath('01-loading.png'), fullPage: true })
    profile.release()
    await expect.poll(() => api.requests.some(request => request.path === '/api/v1/accounting/' + COMPANY_B_INN)).toBe(true)
    await expect(companyPanel(page).getByText(LOADING_REPORT, { exact: true })).toBeVisible()
    await expectConditions(page)
    report.release()
    await expectReport(page)
    await expectConditions(page)

    await page.screenshot({ path: testInfo.outputPath('02-report-and-conditions.png'), fullPage: true })
    const beforeReload = await page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{}'), STORAGE_KEY)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/\/application\/new$/)
    await expectConditions(page)
    await expectReport(page)
    const afterReload = await page.evaluate(key => JSON.parse(localStorage.getItem(key) || '{}'), STORAGE_KEY)
    expect(afterReload.calculation).toEqual(beforeReload.calculation)
    expect(afterReload.applicationCreateIdempotencyKey).toBe(beforeReload.applicationCreateIdempotencyKey)
    expect(afterReload.commerceItems).toEqual(beforeReload.commerceItems)

    await page.getByRole('button', { name: 'Далее', exact: true }).click()
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=items$'))
    await expect(page.getByRole('heading', { name: 'Транспортные средства в заявке', exact: true })).toBeVisible()
    await page.screenshot({ path: testInfo.outputPath('03-transport-items.png'), fullPage: true })
    const creates = api.requests.filter(request => request.path === '/api/v1/commerce/leasing-applications')
    expect(creates).toHaveLength(1)
    expect(creates[0]?.body).toMatchObject({ company_id: COMPANY_B })
    expect(creates[0]?.key).toBe(beforeReload.applicationCreateIdempotencyKey)

    await page.getByRole('button', { name: 'Создать заявку', exact: true }).click()
    await expect(page).toHaveURL(new RegExp('/(?:application|questionnaire)/' + APPLICATION_ID + '\\?step=1$'))
    await expect(page.locator('textarea[name="legal_address"]')).toHaveValue(ADDRESS_B)
    await page.screenshot({ path: testInfo.outputPath('04-company-address.png'), fullPage: true })
    expect(api.requests.filter(request => request.path === '/api/v1/companies/profile')).toHaveLength(0)
    expect(api.requests.filter(request => request.path === '/api/v1/applications/' + APPLICATION_ID + '/items')).toHaveLength(1)
    expect(api.unexpectedWrites).toEqual([])
  })

  test('сохранённый ручной адрес анкеты остаётся после задержанного ответа профиля', async ({ page }, testInfo) => {
    const profile = deferred()
    const api = await installApiFixtures(page, { profileGate: profile.promise, savedAddress: MANUAL_ADDRESS })
    await page.goto('/application/' + APPLICATION_ID + '?step=1', { waitUntil: 'domcontentloaded' })
    await expect.poll(() => api.requests.some(request => request.path === '/api/v1/companies/' + COMPANY_B + '/profile')).toBe(true)
    profile.release()
    const legal = page.locator('textarea[name="legal_address"]')
    const actual = page.locator('textarea[name="actual_address"]')
    await expect(legal).toHaveValue(MANUAL_ADDRESS)
    await page.screenshot({ path: testInfo.outputPath('05-saved-manual-address.png'), fullPage: true })
    await legal.fill('Казань, новый ручной адрес 22218')
    await page.getByLabel('Фактический адрес совпадает с юридическим', { exact: true }).check()
    await expect(actual).toHaveValue('Казань, новый ручной адрес 22218')
    await legal.fill('')
    await expect(legal).toHaveValue('')
    await expect(actual).toHaveValue('')
    expect(api.requests.filter(request => request.path === '/api/v1/companies/profile')).toHaveLength(0)
    expect(api.unexpectedWrites).toEqual([])
  })

  test('лента шагов показывает только текущий этап синим', async ({ page }, testInfo) => {
    const selectedLca = {
      id: LCA_ID,
      application_id: APPLICATION_ID,
      leasing_company_id: COMPANY_A,
      status: 'selected_lc',
    }
    const api = await installApiFixtures(page, { leasingCompanyApplications: [selectedLca] })

    await page.goto('/application/' + APPLICATION_ID + '?step=1', { waitUntil: 'domcontentloaded' })
    await expectStepState(page, 1, 'current')
    await expectStepState(page, 2, 'upcoming')
    const step1Screenshot = testInfo.outputPath('stepper-step-1-desktop.png')
    await page.screenshot({ path: step1Screenshot, fullPage: true })
    await testInfo.attach('stepper-step-1-desktop.png', {
      path: step1Screenshot,
      contentType: 'image/png',
    })

    await page.goto('/application/' + APPLICATION_ID + '?step=company', { waitUntil: 'domcontentloaded' })
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'current')
    const step2Screenshot = testInfo.outputPath('stepper-step-2-desktop.png')
    await page.screenshot({ path: step2Screenshot, fullPage: true })
    await testInfo.attach('stepper-step-2-desktop.png', {
      path: step2Screenshot,
      contentType: 'image/png',
    })

    await page.goto('/application/' + APPLICATION_ID + '?step=6', { waitUntil: 'domcontentloaded' })
    await expectStepState(page, 1, 'completed')
    await expectStepState(page, 2, 'completed')
    await expectStepState(page, 3, 'completed')
    await expectStepState(page, 4, 'completed')
    await expectStepState(page, 5, 'completed')
    await expectStepState(page, 6, 'current')
    await expectStepState(page, 7, 'upcoming')
    const step6Screenshot = testInfo.outputPath('stepper-step-6-desktop.png')
    await page.screenshot({ path: step6Screenshot, fullPage: true })
    await testInfo.attach('stepper-step-6-desktop.png', {
      path: step6Screenshot,
      contentType: 'image/png',
    })
    expect(api.unexpectedWrites).toEqual([])
  })
})
