import { readFileSync } from 'node:fs'
import { expect, test, type Browser, type BrowserContext, type Locator, type Page } from '@playwright/test'

type Role = 'admin' | 'dealer' | 'leasing' | 'distributor' | 'read_only' | 'outsider'
interface Company { id: string; name: string; inn: string | null }
interface DealListItem {
  id: string
  expense_participants: { company: Company | null }[]
  income_participants: { company: Company | null }[]
}
interface DealListPage { items: DealListItem[]; pagination: { page: number; total_pages: number } }
interface Fixture {
  marker: 'monetization-22268'
  base_url: string
  storage_states: Partial<Record<Role, string>>
  companies: { leasing_company: Company; dealer: Company; distributor: Company; second_distributor?: Company }
  support_program?: { id: string; name: string }
  multi_distributor_support?: { id: string; name: string }
  deal_id: string
  legacy_deal_id?: string
  confirmation_deal_id?: string
}
const dealerDisplayName = '«22268 Тестовый дилер»'
const enabled = process.env.MONETIZATION_E2E === '1'
const fixture: Fixture | null = enabled
  ? JSON.parse(readFileSync(process.env.MONETIZATION_E2E_FIXTURE ?? '/tmp/carcraft-22268-e2e/manifest.json', 'utf8')) : null
if (fixture && (fixture.marker !== 'monetization-22268' || !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(fixture.base_url))) {
  throw new Error('Use only the isolated local monetization-22268 fixture')
}
test.skip(!enabled, 'Requires the real isolated app and MONETIZATION_E2E_FIXTURE')

async function session(browser: Browser, role: Role, width = 1280) {
  const state = fixture!.storage_states[role]
  if (!state) throw new Error(`Missing storage state: ${role}`)
  const context = await browser.newContext({ baseURL: fixture!.base_url, storageState: state, viewport: { width, height: 1000 } })
  const page = await context.newPage()
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  return { context, page, errors }
}
async function editor(page: Page) {
  await page.goto('/workspace/monetization')
  await page.getByRole('button', { name: 'Создать условия монетизации', exact: true }).click()
  const form = page.locator('.program-editor')
  await expect(form).toBeVisible()
  return form
}
const rowValue = (row: Locator) => row.getByPlaceholder('0', { exact: true })
const expenseRow = (pair: Locator) => pair.locator('.condition-columns > .condition-row')
const incomeRow = (pair: Locator, index: number) => pair.locator('.pair-income').nth(index)
async function fillAmount(row: Locator, value: string, percent = false) {
  const choice = row.getByRole('button', { name: percent ? '%' : '₽', exact: true })
  if (await choice.isDisabled()) await chooseBase(row.page(), row, percent ? 'Стоимость имущества по договору' : 'Без базы (фиксированная сумма)')
  if (await choice.isEnabled()) await choice.click()
  await rowValue(row).fill(value)
}
async function chooseBase(page: Page, row: Locator, name: string) {
  await row.locator('.filter-label').filter({ hasText: 'База расчёта' }).locator('..').getByRole('button').click()
  const option = page.locator('.custom-scrollbar').getByRole('button', { name, exact: true })
  await expect(option).toHaveCount(1)
  await option.click()
  await expect(option).toHaveCount(0)
}
const expenseBase = (page: Page, row: Locator) => chooseBase(page, row, 'Сумма расхода')
async function company(page: Page, form: Locator, label: string, value: Company) {
  await form.locator('.filter-label').filter({ hasText: label }).locator('..').getByRole('button').click()
  const search = page.getByPlaceholder('Название или ИНН', { exact: true })
  await expect(search).toHaveCount(1)
  await search.fill(value.inn || value.name)
  await page.locator('.custom-scrollbar').getByRole('button', { name: `${value.name} · ИНН ${value.inn || 'не указан'}`, exact: true }).click()
  await expect(search).toHaveCount(0)
}
async function addIncome(pair: Locator) {
  await pair.getByRole('button', { name: '+ Добавить доход', exact: true }).click()
}
async function csrfHeaders(context: BrowserContext): Promise<Record<string, string>> {
  const token = (await context.cookies(fixture!.base_url)).find(cookie => cookie.name === 'csrfToken')
  if (!token) throw new Error('Authenticated fixture has no CSRF cookie')
  return { 'X-CSRF-Token': token.value }
}
async function finish(context: BrowserContext, errors: string[]) {
  await context.close()
  expect(errors).toEqual([])
}

for (const example of [
  { name: 'fixed money', expense: '10000', incomes: ['3000', '4000', '5000'], expected: '3000', percent: false, expenseBase: false },
  { name: 'property percentages', expense: '2', incomes: ['0.7', '0.8', '1'], expected: '0.5', percent: true, expenseBase: false },
  { name: 'percentages of expense', expense: '2', incomes: ['40', '40', '30'], expected: '20', percent: true, expenseBase: true },
  { name: 'kopeck allocation', expense: '10', incomes: ['5.50', '4.51'], expected: '4.5', percent: false, expenseBase: false },
]) {
  test(`real form limits ${example.name} without crossing another pair`, async ({ browser }) => {
    const { context, page, errors } = await session(browser, 'admin')
    try {
      const form = await editor(page)
      const pair = form.locator('.condition-pair').first()
      await fillAmount(expenseRow(pair), example.expense, example.percent)
      for (const [index, value] of example.incomes.entries()) {
        if (index) await addIncome(pair)
        const income = incomeRow(pair, index)
        if (example.expenseBase) await expenseBase(page, income)
        await fillAmount(income, value, example.percent)
      }
      await expect(rowValue(incomeRow(pair, example.incomes.length - 1))).toHaveValue(example.expected)
      await expect(pair.getByRole('status')).toContainText('ограничен доступным остатком')
      await form.getByRole('button', { name: '+ Добавить связку', exact: true }).click()
      await expect(form.locator('.condition-pair')).toHaveCount(2)
      await expect(form.locator('.source-field select')).toHaveCount(1)
      await expect(form.getByRole('button', { name: '+ Добавить источник', exact: true })).toBeVisible()
      await expect(rowValue(expenseRow(form.locator('.condition-pair').nth(1)))).toHaveValue('')
      await expect(rowValue(incomeRow(pair, example.incomes.length - 1))).toHaveValue(example.expected)
    } finally { await finish(context, errors) }
  })
}

test('real form reduces last income first, rejects conflicting minimum and explains mixed bases', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const form = await editor(page)
    const pair = form.locator('.condition-pair').first()
    await fillAmount(expenseRow(pair), '10000')
    await fillAmount(incomeRow(pair, 0), '3000')
    await addIncome(pair)
    await fillAmount(incomeRow(pair, 1), '4000')
    await addIncome(pair)
    await fillAmount(incomeRow(pair, 2), '3000')
    await rowValue(expenseRow(pair)).fill('9000')
    await expect(rowValue(incomeRow(pair, 0))).toHaveValue('3000')
    await expect(rowValue(incomeRow(pair, 1))).toHaveValue('4000')
    await expect(rowValue(incomeRow(pair, 2))).toHaveValue('2000')
    await expect(pair.getByRole('button', { name: '+ Добавить доход', exact: true })).toBeDisabled()
    await incomeRow(pair, 2).getByPlaceholder('Мин, ₽', { exact: true }).fill('2500')
    await expect(pair.getByRole('alert')).toContainText('Минимум дохода превышает остаток')
    await incomeRow(pair, 2).getByPlaceholder('Мин, ₽', { exact: true }).fill('')
    await fillAmount(expenseRow(pair), '2', true)
    await expect(pair.locator('.budget-deferred')).toContainText('по фактической стоимости имущества')
  } finally { await finish(context, errors) }
})

test('creates one source with two pairs and persists three linked income bases through the real API', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const form = await editor(page)
    const name = `22268 browser ${Date.now()}`
    await form.getByPlaceholder('Например, «Базовые условия по легковым»').fill(name)
    await company(page, form, 'Лизинговая компания *', fixture!.companies.leasing_company)
    await company(page, form, 'Дилер (опционально)', fixture!.companies.dealer)
    await company(page, form, 'Дистрибьютор (опционально)', fixture!.companies.distributor)
    await form.locator('input[type=date]').first().fill('2026-09-20')
    await form.getByRole('radio', { name: 'Неактивна', exact: true }).check()
    const pair = form.locator('.condition-pair').first()
    await fillAmount(expenseRow(pair), '10000')
    await fillAmount(incomeRow(pair, 0), '3000')
    await addIncome(pair)
    await incomeRow(pair, 1).locator('select').selectOption('distributor')
    await expenseBase(page, incomeRow(pair, 1))
    await fillAmount(incomeRow(pair, 1), '40', true)
    await addIncome(pair)
    await incomeRow(pair, 2).locator('select').selectOption('platform')
    await fillAmount(incomeRow(pair, 2), '3000')
    await form.getByRole('button', { name: '+ Добавить связку', exact: true }).click()
    const second = form.locator('.condition-pair').nth(1)
    await expenseRow(second).locator('select').selectOption('distributor')
    await fillAmount(expenseRow(second), '1000')
    await second.getByRole('button', { name: /Удалить доход 1/ }).click()
    const savedResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/admin/monetization/programs')
    await form.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
    const response = await savedResponse
    expect(response.status(), await response.text()).toBe(201)
    const saved = await response.json()
    expect(saved.sources).toHaveLength(1)
    expect(saved.sources[0].expenses).toHaveLength(2)
    expect(saved.sources[0].incomes).toHaveLength(3)
    expect(saved.sources[0].incomes.every((income: { expense_ref: string }) => income.expense_ref === saved.sources[0].expenses[0].local_id)).toBe(true)
    await expect(page.locator('.program-detail')).toContainText(name)
    await page.getByRole('button', { name: 'Условия монетизации', exact: true }).click()
    const listRow = page.locator('.programs-table tbody tr').filter({ hasText: name })
    await expect(listRow).toContainText(fixture!.companies.leasing_company.name)
    await expect(listRow).toContainText(fixture!.companies.dealer.name)
    await expect(listRow).toContainText(fixture!.companies.distributor.name)
    await listRow.getByRole('button', { name: 'Карточка', exact: true }).click()
    const reloaded = await page.request.get(`/api/v1/admin/monetization/programs/${saved.id}`)
    expect(reloaded.status()).toBe(200)
    expect((await reloaded.json()).sources[0].incomes).toHaveLength(3)
    await expect(page.locator('.program-detail .calculation-group').first().locator('.income-summary')).toHaveCount(3)
  } finally { await finish(context, errors) }
})

test('zero min and max are rejected before sending the real create request', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const form = await editor(page)
    await form.getByPlaceholder('Например, «Базовые условия по легковым»').fill(`22268 invalid bounds ${Date.now()}`)
    await company(page, form, 'Лизинговая компания *', fixture!.companies.leasing_company)
    await form.locator('input[type=date]').first().fill('2026-09-20')
    await form.getByRole('radio', { name: 'Неактивна', exact: true }).check()
    const pair = form.locator('.condition-pair').first()
    await fillAmount(expenseRow(pair), '10000')
    await fillAmount(incomeRow(pair, 0), '3000')
    const writes: string[] = []
    page.on('request', request => {
      if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/admin/monetization/programs') writes.push(request.url())
    })
    for (const placeholder of ['Мин, ₽', 'Макс, ₽']) {
      const bound = incomeRow(pair, 0).getByPlaceholder(placeholder, { exact: true })
      await bound.fill('0')
      await form.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
      await expect(form.locator(':scope > .program-editor-body > [role=alert]')).toContainText('Заполненные ограничения суммы должны быть положительными')
      expect(writes).toEqual([])
      await bound.fill('')
    }
  } finally { await finish(context, errors) }
})

test('base, type and bound changes recalculate only their own pair', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const form = await editor(page)
    const first = form.locator('.condition-pair').first()
    await fillAmount(expenseRow(first), '10000')
    for (const [index, value] of ['3000', '4000', '2000'].entries()) {
      if (index) await addIncome(first)
      await fillAmount(incomeRow(first, index), value)
    }
    await form.getByRole('button', { name: '+ Добавить связку', exact: true }).click()
    const second = form.locator('.condition-pair').nth(1)
    await fillAmount(expenseRow(second), '2000')
    await fillAmount(incomeRow(second, 0), '500')
    await expenseRow(first).getByPlaceholder('Макс, ₽', { exact: true }).fill('8000')
    await expect(rowValue(incomeRow(first, 0))).toHaveValue('3000')
    await expect(rowValue(incomeRow(first, 1))).toHaveValue('4000')
    await expect(rowValue(incomeRow(first, 2))).toHaveValue('1000')
    await expenseRow(first).getByPlaceholder('Макс, ₽', { exact: true }).fill('')
    await incomeRow(first, 0).getByPlaceholder('Мин, ₽', { exact: true }).fill('4500')
    await expenseRow(first).getByPlaceholder('Макс, ₽', { exact: true }).fill('9000')
    await expect(rowValue(incomeRow(first, 2))).toHaveValue('500')
    await expenseBase(page, incomeRow(first, 0))
    await incomeRow(first, 0).getByRole('button', { name: '%', exact: true }).click()
    await expect(rowValue(incomeRow(first, 0))).toHaveValue('50')
    await chooseBase(page, incomeRow(first, 0), 'Стоимость имущества по договору')
    await expect(first.locator('.budget-deferred')).toBeVisible()
    await expect(rowValue(incomeRow(first, 0))).toHaveValue('50')
    await expenseBase(page, incomeRow(first, 0))
    await expect(first.locator('.budget-deferred')).toHaveCount(0)
    const max = incomeRow(first, 1).getByPlaceholder('Макс, ₽', { exact: true })
    await max.fill('2000')
    await rowValue(incomeRow(first, 1)).fill('5000')
    await expect(rowValue(incomeRow(first, 1))).toHaveValue('5000')
    await max.fill('')
    await expect(rowValue(incomeRow(first, 1))).toHaveValue('4000')
    await expect(rowValue(expenseRow(second))).toHaveValue('2000')
    await expect(rowValue(incomeRow(second, 0))).toHaveValue('500')
    await expect(second.getByRole('alert')).toHaveCount(0)
  } finally { await finish(context, errors) }
})

test('equal bounds make percentage formulas constant without a future property price', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const form = await editor(page)
    const pair = form.locator('.condition-pair').first()
    await fillAmount(expenseRow(pair), '2', true)
    await expenseRow(pair).getByPlaceholder('Мин, ₽', { exact: true }).fill('10000.00')
    await expenseRow(pair).getByPlaceholder('Макс, ₽', { exact: true }).fill('10000')
    await fillAmount(incomeRow(pair, 0), '15000')
    await expect(rowValue(incomeRow(pair, 0))).toHaveValue('10000')
    await expect(pair.locator('.budget-deferred')).toHaveCount(0)
    await incomeRow(pair, 0).getByPlaceholder('Мин, ₽', { exact: true }).fill('3000')
    await incomeRow(pair, 0).getByPlaceholder('Макс, ₽', { exact: true }).fill('3000')
    await fillAmount(incomeRow(pair, 0), '20', true)
    await expect(pair.locator('.budget-deferred')).toHaveCount(0)
    await addIncome(pair)
    await fillAmount(incomeRow(pair, 1), '9000')
    await expect(rowValue(incomeRow(pair, 1))).toHaveValue('7000')
    await expect(rowValue(incomeRow(pair, 0))).toHaveValue('20')
  } finally { await finish(context, errors) }
})

test('supports use the selected distributor and clear a previous selection', async ({ browser }) => {
  test.skip(!fixture?.support_program || !fixture.companies.second_distributor, 'Requires support and second distributor fixtures')
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const form = await editor(page)
    const support = form.locator('.filter-label').filter({ hasText: 'Программа стимулирования (опционально)' }).locator('..').getByRole('button')
    await expect(support).toBeEnabled()
    const allResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/monetization/lookups/supports')
    await support.click()
    const all = await allResponse
    expect(new URL(all.url()).searchParams.has('distributor_company_id')).toBe(false)
    expect((await all.json()).items.map((item: { id: string }) => item.id)).toContain(fixture!.support_program!.id)
    await page.locator('.custom-scrollbar').getByRole('button', { name: fixture!.support_program!.name, exact: true }).click()
    await company(page, form, 'Дистрибьютор (опционально)', fixture!.companies.distributor)
    await expect(support).toContainText('Не выбрана')
    const loaded = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/monetization/lookups/supports')
    await support.click()
    const response = await loaded
    expect(new URL(response.url()).searchParams.get('distributor_company_id')).toBe(fixture!.companies.distributor.id)
    const supports = (await response.json()).items as { id: string }[]
    expect(supports.map(item => item.id)).toContain(fixture!.support_program!.id)
    if (fixture!.multi_distributor_support) expect(supports.map(item => item.id)).toContain(fixture!.multi_distributor_support.id)
    await page.locator('.custom-scrollbar').getByRole('button', { name: fixture!.support_program!.name, exact: true }).click()
    await expect(support).toContainText(fixture!.support_program!.name)
    await company(page, form, 'Дистрибьютор (опционально)', fixture!.companies.second_distributor!)
    await expect(support).toContainText('Не выбрана')
    const secondResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/monetization/lookups/supports')
    await support.click()
    const second = await secondResponse
    expect(new URL(second.url()).searchParams.get('distributor_company_id')).toBe(fixture!.companies.second_distributor!.id)
    expect((await second.json()).items.map((item: { id: string }) => item.id)).not.toContain(fixture!.support_program!.id)
  } finally { await finish(context, errors) }
})

test('support remains selectable and can be saved after clearing the optional distributor', async ({ browser }) => {
  test.skip(!fixture?.support_program, 'Requires support fixture')
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const form = await editor(page)
    const name = `22268 support without distributor ${Date.now()}`
    await form.getByPlaceholder('Например, «Базовые условия по легковым»').fill(name)
    await company(page, form, 'Лизинговая компания *', fixture!.companies.leasing_company)
    await form.locator('input[type=date]').first().fill('2026-09-20')
    await form.getByRole('radio', { name: 'Неактивна', exact: true }).check()
    await company(page, form, 'Дистрибьютор (опционально)', fixture!.companies.distributor)
    const support = form.locator('.filter-label').filter({ hasText: 'Программа стимулирования (опционально)' }).locator('..').getByRole('button')
    await support.click()
    await page.locator('.custom-scrollbar').getByRole('button', { name: fixture!.support_program!.name, exact: true }).click()
    await form.locator('.filter-label').filter({ hasText: 'Дистрибьютор (опционально)' }).locator('..').getByRole('button').click()
    await page.locator('.custom-scrollbar').getByRole('button', { name: 'Любой дистрибьютор', exact: true }).click()
    await expect(support).toBeEnabled()
    await expect(support).toContainText(fixture!.support_program!.name)
    const allResponse = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/monetization/lookups/supports')
    await support.click()
    const all = await allResponse
    expect(new URL(all.url()).searchParams.has('distributor_company_id')).toBe(false)
    expect((await all.json()).items.map((item: { id: string }) => item.id)).toContain(fixture!.support_program!.id)
    await page.locator('.custom-scrollbar').getByRole('button', { name: fixture!.support_program!.name, exact: true }).click()
    const pair = form.locator('.condition-pair').first()
    await fillAmount(expenseRow(pair), '10000')
    await fillAmount(incomeRow(pair, 0), '3000')
    const savedResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/admin/monetization/programs')
    await form.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
    const response = await savedResponse
    expect(response.status(), await response.text()).toBe(201)
    const saved = await response.json()
    expect(saved.distributor_company_id).toBeNull()
    expect(saved.support_program_id).toBe(fixture!.support_program!.id)
    await expect(page.locator('.program-detail')).toContainText(name)
    const reloaded = await page.request.get(`/api/v1/admin/monetization/programs/${saved.id}`)
    expect(reloaded.status()).toBe(200)
    expect((await reloaded.json()).support_program_id).toBe(fixture!.support_program!.id)
  } finally { await finish(context, errors) }
})

test('a delayed real support response cannot replace the new distributor options', async ({ browser }) => {
  test.skip(!fixture?.support_program || !fixture.companies.second_distributor, 'Requires support and second distributor fixtures')
  const { context, page, errors } = await session(browser, 'admin')
  let release = () => {}
  const held = new Promise<void>(resolve => { release = resolve })
  let intercepted = () => {}
  const captured = new Promise<void>(resolve => { intercepted = resolve })
  try {
    const form = await editor(page)
    await company(page, form, 'Дистрибьютор (опционально)', fixture!.companies.distributor)
    await page.route(url => url.pathname === '/api/v1/monetization/lookups/supports', async route => {
      const url = new URL(route.request().url())
      if (url.searchParams.get('distributor_company_id') !== fixture!.companies.distributor.id) return route.continue()
      // Fault injection delays the actual HTTP response, retaining the real
      // authenticated backend result unchanged; no catalogue values are mocked.
      const response = await route.fetch()
      intercepted()
      await held
      await route.fulfill({ response })
    })
    const support = form.locator('.filter-label').filter({ hasText: 'Программа стимулирования (опционально)' }).locator('..').getByRole('button')
    await support.click()
    await captured
    await company(page, form, 'Дистрибьютор (опционально)', fixture!.companies.second_distributor!)
    const fresh = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === '/api/v1/monetization/lookups/supports' && url.searchParams.get('distributor_company_id') === fixture!.companies.second_distributor!.id
    })
    await support.click()
    expect((await fresh).status()).toBe(200)
    const stale = page.waitForResponse(response => {
      const url = new URL(response.url())
      return url.pathname === '/api/v1/monetization/lookups/supports' && url.searchParams.get('distributor_company_id') === fixture!.companies.distributor.id
    })
    release()
    expect((await stale).status()).toBe(200)
    await expect(page.locator('.custom-scrollbar').getByRole('button', { name: fixture!.support_program!.name, exact: true })).toHaveCount(0)
    if (fixture!.multi_distributor_support) {
      await expect(page.locator('.custom-scrollbar').getByRole('button', { name: fixture!.multi_distributor_support.name, exact: true })).toBeVisible()
    }
    await expect(support).toContainText('Не выбрана')
  } finally { release(); await finish(context, errors) }
})

test('dealer heading removes only the leading role and keeps the company name unchanged in the API', async ({ browser }, testInfo) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const endpoint = `/api/v1/monetization/deals/${fixture!.deal_id}`
    const before = await page.request.get(endpoint)
    expect(before.status()).toBe(200)
    const rawName = (await before.json()).dealer_company.name
    expect(rawName).toBe('Дилер «22268 Тестовый дилер»')
    expect(rawName).toBe(fixture!.companies.dealer.name)
    await page.goto(`/workspace/monetization?deal=${fixture!.deal_id}`)
    await expect(page.locator('.deal-participants dt').first()).toHaveText('Дилер')
    // The role before the quotes disappears; «дилер» inside the name remains.
    await expect(page.locator('.deal-participants dd').first()).toHaveText(dealerDisplayName)
    const after = await page.request.get(endpoint)
    expect(after.status()).toBe(200)
    expect((await after.json()).dealer_company.name).toBe(rawName)
    await page.getByRole('dialog').screenshot({ path: testInfo.outputPath('dealer-company-name.png') })
  } finally { await finish(context, errors) }
})

for (const role of ['admin', 'dealer', 'leasing', 'distributor'] as const) {
  test(`real ${role} list shows participant companies without income or expense amounts`, async ({ browser }) => {
    test.skip(!fixture?.storage_states[role], `Missing ${role} fixture`)
    const { context, page, errors } = await session(browser, role)
    try {
      const detail = await page.request.get(`/api/v1/monetization/deals/${fixture!.deal_id}`)
      expect(detail.status()).toBe(200)
      const deal = await detail.json()
      await page.goto('/workspace/monetization', { waitUntil: 'domcontentloaded' })
      const waitForListPage = (number: number) => page.waitForResponse(response => {
        const url = new URL(response.url())
        return response.request().method() === 'GET' && url.pathname === '/api/v1/monetization/deals'
          && url.searchParams.get('page') === String(number)
      })
      const initialList = waitForListPage(1)
      await page.getByRole('tab', { name: 'Сделки', exact: true }).click()
      let response = await initialList
      expect(response.status()).toBe(200)
      let list = await response.json() as DealListPage
      await expect(page.getByRole('columnheader', { name: 'Участники расхода', exact: true })).toBeVisible()
      await expect(page.getByRole('columnheader', { name: 'Участники дохода', exact: true })).toBeVisible()
      // New fixture batches can push this older deal onto a later page.
      // Navigate the real list and validate its own response, without a second
      // API-only search or an assumption about the fixture's creation order.
      while (!list.items.some(item => item.id === deal.id) && list.pagination.page < list.pagination.total_pages) {
        const nextList = waitForListPage(list.pagination.page + 1)
        await page.getByRole('button', { name: 'Следующая', exact: true }).click()
        response = await nextList
        expect(response.status()).toBe(200)
        list = await response.json() as DealListPage
        await expect(page.locator('.registry-results')).toHaveAttribute('aria-busy', 'false')
      }
      const summary = list.items.find(item => item.id === deal.id)
      expect(summary, 'Fixture deal must be reachable through the real list pagination').toBeDefined()
      if (!summary) throw new Error('Fixture deal is absent from all available pages')
      const row = page.locator('.deals-table tbody tr').filter({ has: page.getByText(deal.application_number, { exact: true }) })
      await expect(row).toBeVisible()
      const participants = row.locator('.participant-list')
      await expect(participants).toHaveCount(2)
      for (const cell of await participants.all()) await expect(cell).not.toContainText(/₽|НДС/)
      for (const [index, key] of (['expense_participants', 'income_participants'] as const).entries()) {
        for (const participant of summary[key]) {
          if (participant.company) await expect(participants.nth(index)).toContainText(participant.company.name)
        }
      }
      await row.getByRole('button', { name: 'Просмотр', exact: true }).click()
      await expect(page.locator('.deal-participants dt').first()).toHaveText('Дилер')
      await expect(page.locator('.deal-participants dd').first()).toHaveText(dealerDisplayName)
    } finally { await finish(context, errors) }
  })
}

for (const width of [768, 1280, 1920]) {
  test(`real deal keeps expense left and its incomes right at ${width}px`, async ({ browser }, testInfo) => {
    const { context, page, errors } = await session(browser, 'admin', width)
    try {
      await page.goto(`/workspace/monetization?deal=${fixture!.deal_id}`)
      const modal = page.getByRole('dialog')
      await expect(modal).toBeVisible()
      const group = modal.locator('.calculation-group').filter({ has: page.locator('.expense-amount') }).first()
      const expense = await group.locator('.expense-amount').boundingBox()
      const incomes = await group.locator('.deal-incomes').boundingBox()
      expect(expense).not.toBeNull()
      expect(incomes).not.toBeNull()
      expect(incomes!.x).toBeGreaterThanOrEqual(expense!.x + expense!.width)
      expect(Math.abs(incomes!.y - expense!.y)).toBeLessThanOrEqual(1)
      const box = await modal.boundingBox()
      expect(box!.x).toBeGreaterThanOrEqual(24)
      expect(box!.width).toBeLessThanOrEqual(Math.min(1120, width - 48))
      expect(await modal.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
      await modal.screenshot({ path: testInfo.outputPath(`deal-${width}.png`) })
    } finally { await finish(context, errors) }
  })
}

test('participant confirms once from the action immediately before attaching optional documents', async ({ browser }) => {
  test.skip(!fixture?.confirmation_deal_id, 'Requires a separate confirmation deal')
  // Repeated runs prepare the synthetic deal through the real admin adjustment
  // operation, which invalidates its previous participant confirmations.
  const admin = await session(browser, 'admin')
  try {
    const response = await admin.page.request.get(`/api/v1/monetization/deals/${fixture!.confirmation_deal_id}`)
    expect(response.status()).toBe(200)
    const current = await response.json()
    if (current.confirmations.distributor.confirmed_at) {
      const income = current.incomes.find((row: { amount: string }) => BigInt(row.amount.split('.')[0]) > BigInt(1))
      expect(income).toBeDefined()
      const reset = await admin.page.request.post(`/api/v1/admin/monetization/deals/${current.id}/adjust-conditions`, {
        headers: await csrfHeaders(admin.context),
        data: { revision: current.revision, items: [{ deal_participant_amount_id: income.id, new_value: String(BigInt(income.amount.split('.')[0]) - BigInt(1)) }] },
      })
      expect(reset.status()).toBe(200)
    }
  } finally { await finish(admin.context, admin.errors) }
  const { context, page, errors } = await session(browser, 'distributor')
  try {
    await page.goto(`/workspace/monetization?deal=${fixture!.confirmation_deal_id}`)
    const modal = page.getByRole('dialog')
    const confirm = modal.getByRole('button', { name: 'Подтвердить', exact: true })
    const upload = modal.getByRole('button', { name: 'Приложить документы', exact: true })
    await expect(confirm).toHaveCount(1)
    await expect(upload).toBeEnabled()
    expect(await confirm.evaluate((button, uploadText) => button.nextElementSibling?.textContent === uploadText, 'Приложить документы')).toBe(true)
    const saved = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/confirm'))
    await confirm.click()
    expect((await saved).status()).toBe(200)
    await expect(confirm).toHaveCount(0)
    await expect(modal.locator('.confirmation-line').filter({ hasText: 'Дистрибьютор' })).toContainText('Подтверждено')
    await expect(upload).toBeEnabled()
  } finally { await finish(context, errors) }
})

test('read-only participant cannot confirm and an unrelated company cannot open the deal', async ({ browser }) => {
  test.skip(!fixture?.storage_states.read_only || !fixture.storage_states.outsider, 'Requires access fixtures')
  const readOnly = await session(browser, 'read_only')
  try {
    const response = await readOnly.page.request.get(`/api/v1/monetization/deals/${fixture!.deal_id}`)
    expect(response.status()).toBe(200)
    const deal = await response.json()
    expect(deal.can_confirm).toBe(false)
    await readOnly.page.goto(`/workspace/monetization?deal=${fixture!.deal_id}`)
    await expect(readOnly.page.getByRole('dialog')).toBeVisible()
    await expect(readOnly.page.getByRole('button', { name: 'Подтвердить', exact: true })).toHaveCount(0)
    const forbidden = await readOnly.page.request.post(`/api/v1/monetization/deals/${fixture!.deal_id}/confirm`, { headers: await csrfHeaders(readOnly.context), data: { revision: deal.revision } })
    expect(forbidden.status()).toBe(403)
    expect(await forbidden.json()).not.toMatchObject({ code: 'CSRF_INVALID' })
  } finally { await finish(readOnly.context, readOnly.errors) }
  const outsider = await session(browser, 'outsider')
  try {
    const response = await outsider.page.request.get(`/api/v1/monetization/deals/${fixture!.deal_id}`)
    expect([403, 404]).toContain(response.status())
    await outsider.page.goto(`/workspace/monetization?deal=${fixture!.deal_id}`)
    await expect(outsider.page.getByRole('dialog')).toHaveCount(0)
    await expect(outsider.page.locator('.registry-deal-error')).toBeVisible()
  } finally { await finish(outsider.context, outsider.errors) }
})

test('a legacy deal retains its independent income group', async ({ browser }) => {
  test.skip(!fixture?.legacy_deal_id, 'Requires a legacy independent-income deal')
  const { context, page, errors } = await session(browser, 'admin')
  try {
    await page.goto(`/workspace/monetization?deal=${fixture!.legacy_deal_id}`)
    await expect(page.getByRole('dialog')).toBeVisible()
    await expect(page.getByRole('region', { name: 'Самостоятельные доходы', exact: true })).toBeVisible()
  } finally { await finish(context, errors) }
})


test('real condition form keeps valid cents and caps independent half-cent rounding', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const form = await editor(page)
    const pair = form.locator('.condition-pair').first()
    await fillAmount(expenseRow(pair), '10')
    await fillAmount(incomeRow(pair, 0), '5.50')
    await addIncome(pair)
    await fillAmount(incomeRow(pair, 1), '4.50')
    await expect(rowValue(incomeRow(pair, 0))).toHaveValue('5.50')
    await expect(rowValue(incomeRow(pair, 1))).toHaveValue('4.50')
    await expect(pair.getByRole('alert')).toHaveCount(0)
    await fillAmount(expenseRow(pair), '0.10')
    await expenseBase(page, incomeRow(pair, 0))
    await fillAmount(incomeRow(pair, 0), '55', true)
    await expenseBase(page, incomeRow(pair, 1))
    await fillAmount(incomeRow(pair, 1), '45', true)
    await expect(rowValue(incomeRow(pair, 1))).toHaveValue('44.99')
    await expect(pair.getByRole('status')).toContainText('ограничен доступным остатком')
    await expect(pair.getByRole('alert')).toHaveCount(0)
  } finally { await finish(context, errors) }
})
