import { readFileSync } from 'node:fs'
import { expect, test, type Browser, type Locator, type Page } from '@playwright/test'

interface Company { id: string; name: string; inn: string | null }
interface Fixture {
  marker: string
  base_url: string
  storage_states: Partial<Record<'admin' | 'dealer' | 'read_only', string>>
  companies: { leasing_company: Company }
}
const enabled = process.env.MONETIZATION_E2E === '1'
const fixture: Fixture | null = enabled
  ? JSON.parse(readFileSync(process.env.MONETIZATION_E2E_FIXTURE ?? '/tmp/carcraft-22406-e2e/manifest.json', 'utf8')) : null
if (fixture && (!['monetization-22406', 'monetization-22268'].includes(fixture.marker) || !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(fixture.base_url))) {
  throw new Error('Use only the isolated local monetization fixture')
}
test.skip(!enabled, 'Requires the real isolated app and MONETIZATION_E2E_FIXTURE')

async function session(browser: Browser, role: 'admin' | 'dealer' | 'read_only' = 'admin') {
  const state = fixture!.storage_states[role]
  if (!state) throw new Error(`Missing storage state: ${role}`)
  const context = await browser.newContext({ baseURL: fixture!.base_url, storageState: state, viewport: { width: 1280, height: 1000 } })
  const page = await context.newPage()
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  return { context, page, errors }
}
async function openEditor(page: Page) {
  await page.goto('/workspace/monetization')
  await page.getByRole('button', { name: 'Создать условия монетизации', exact: true }).click()
  const form = page.locator('.program-editor')
  await expect(form).toBeVisible()
  return form
}
async function chooseBase(page: Page, row: Locator, name: string) {
  const menu = page.locator('div.custom-scrollbar')
  await expect(menu).toHaveCount(0)
  await row.locator('.filter-label').filter({ hasText: 'База расчёта' }).locator('..').getByRole('button').click()
  await menu.getByRole('button', { name, exact: true }).click()
  await expect(menu).toHaveCount(0)
}
async function selectLeasingCompany(page: Page, form: Locator) {
  const company = fixture!.companies.leasing_company
  await form.locator('.filter-label').filter({ hasText: 'Лизинговая компания *' }).locator('..').getByRole('button').click()
  await page.getByPlaceholder('Название или ИНН', { exact: true }).fill(company.inn || company.name)
  await page.locator('.custom-scrollbar').getByRole('button', { name: `${company.name} · ИНН ${company.inn || 'не указан'}`, exact: true }).click()
}

test('property value selects percent and disables money for expense and income', async ({ browser }) => {
  const { context, page, errors } = await session(browser)
  try {
    const form = await openEditor(page)
    for (const row of await form.locator('.condition-row').all()) {
      await expect(row.getByRole('button', { name: '₽', exact: true })).toBeDisabled()
      await expect(row.getByRole('button', { name: '%', exact: true })).toHaveAttribute('aria-pressed', 'true')
      await chooseBase(page, row, 'Без базы (фиксированная сумма)')
      await expect(row.getByRole('button', { name: '%', exact: true })).toBeDisabled()
      await expect(row.getByRole('button', { name: '₽', exact: true })).toHaveAttribute('aria-pressed', 'true')
      await chooseBase(page, row, 'Стоимость имущества по договору')
      await expect(row.getByRole('button', { name: '₽', exact: true })).toBeDisabled()
      await expect(row.getByRole('button', { name: '%', exact: true })).toBeEnabled()
      await expect(row.getByRole('button', { name: '%', exact: true })).toHaveAttribute('aria-pressed', 'true')
    }
    const income = form.locator('.pair-income .condition-row').first()
    await chooseBase(page, income, 'Сумма расхода')
    await expect(income.getByRole('button', { name: '%', exact: true })).toBeEnabled()
    await expect(income.getByRole('button', { name: '₽', exact: true })).toBeEnabled()
    await income.getByRole('button', { name: '₽', exact: true }).click()
    await chooseBase(page, income, 'Стоимость имущества по договору')
    await expect(income.getByRole('button', { name: '%', exact: true })).toHaveAttribute('aria-pressed', 'true')
  } finally {
    await context.close()
    expect(errors).toEqual([])
  }
})

test('one condition saves platform and exchange with independent calculation through the real API', async ({ browser }) => {
  const { context, page, errors } = await session(browser)
  try {
    const form = await openEditor(page)
    await form.getByRole('button', { name: '+ Добавить источник', exact: true }).click()
    await expect(form.locator('.source-card')).toHaveCount(2)
    const sources = form.locator('.source-card')
    await sources.nth(0).locator('.source-field select').selectOption('platform')
    await sources.nth(1).locator('.source-field select').selectOption('exchange')
    const name = `22406 sources ${Date.now()}`
    await form.getByPlaceholder('Например, «Базовые условия по легковым»').fill(name)
    await selectLeasingCompany(page, form)
    await form.locator('input[type=date]').first().fill('2026-09-20')
    await form.getByRole('radio', { name: 'Неактивна', exact: true }).check()
    for (const [index, value] of ['2', '3'].entries()) {
      const source = sources.nth(index)
      await source.locator('.condition-columns > .condition-row').getByPlaceholder('0', { exact: true }).fill(value)
      await source.locator('.pair-income').getByPlaceholder('0', { exact: true }).fill('1')
    }
    const pending = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/v1/admin/monetization/programs')
    await form.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
    const response = await pending
    expect(response.status(), await response.text()).toBe(201)
    const saved = await response.json()
    expect(saved.sources.map((source: { source_type: string }) => source.source_type)).toEqual(['platform', 'exchange'])
    expect(saved.sources.map((source: { expenses: { value: string }[] }) => Number(source.expenses[0].value))).toEqual([2, 3])
    for (const source of saved.sources) expect(source.incomes[0].expense_ref).toBe(source.expenses[0].local_id)
    const reloaded = await context.request.get(`/api/v1/admin/monetization/programs/${saved.id}`)
    expect(reloaded.status()).toBe(200)
    expect((await reloaded.json()).sources).toEqual(saved.sources)
    await expect(page.locator('.program-detail')).toContainText(name)
    await expect(page.locator('.program-detail')).toContainText('Биржа ТС')
    await expect(page.locator('.program-detail')).toContainText('Заявка с сайта платформы МЛ')
  } finally {
    await context.close()
    expect(errors).toEqual([])
  }
})

test('non-admin cannot create multi-source conditions and invalid source is rejected', async ({ browser }) => {
  const admin = await session(browser)
  const dealer = await session(browser, 'dealer')
  try {
    const payload = {
      name: `22406 access ${Date.now()}`, leasing_company_id: fixture!.companies.leasing_company.id,
      status: 'inactive', period_start: '2026-09-20',
      sources: ['platform', 'exchange'].map(source_type => ({ source_type, expenses: [{ local_id: 'expense', participant_type: 'leasing', base_type: 'property_value', calc_type: 'percent', value: '2' }], incomes: [] })),
    }
    for (const [actor, expected] of [[dealer, 403], [admin, 400]] as const) {
      const csrf = (await actor.context.cookies(fixture!.base_url)).find(cookie => cookie.name === 'csrfToken')
      if (!csrf) throw new Error('Fixture is missing CSRF cookie')
      const data = actor === admin ? { ...payload, sources: [{ ...payload.sources[0], source_type: 'leasing_to_dealer' }] } : payload
      const result = await actor.context.request.post('/api/v1/admin/monetization/programs', { headers: { 'X-CSRF-Token': csrf.value }, data })
      expect(result.status(), await result.text()).toBe(expected)
    }
  } finally {
    await admin.context.close()
    await dealer.context.close()
  }
})
