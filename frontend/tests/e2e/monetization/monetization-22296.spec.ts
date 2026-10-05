import { readFileSync } from 'node:fs'
import { expect, test, type Browser, type BrowserContext, type Locator, type Page } from '@playwright/test'

interface Company { company_id: string; name: string; leasing_company_id?: string }
interface Case {
  kind: string; deal_id: string; expense: string; income: string
  expense_clip: string; expense_limit: string | null; income_clip: string; income_limit: string | null
}
interface Fixture {
  marker: string; base_url: string; storage_states: Record<string, string>
  companies: Record<string, Company>; cases: Case[]
  browser_vin: string; browser_bid: { bid_id: string; application_number: string }
}
const enabled = process.env.MONETIZATION_22296_E2E === '1'
const fixture: Fixture | null = enabled ? JSON.parse(readFileSync(
  process.env.MONETIZATION_22296_FIXTURE ?? '/tmp/carcraft-22296-monetization/monetization.manifest.json', 'utf8')) : null
if (fixture && (fixture.marker !== 'monetization-22296' || fixture.base_url !== 'http://localhost:18296')) {
  throw new Error('Task 22296 requires its isolated local fixture')
}
test.skip(!enabled, 'Requires isolated 22296 monetization Docker fixtures')
test.setTimeout(60_000)

async function session(browser: Browser, role = 'admin', width = 1440) {
  const context = await browser.newContext({
    baseURL: fixture!.base_url, storageState: fixture!.storage_states[role],
    viewport: { width, height: 1000 },
  })
  const page = await context.newPage()
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  return { context, page, errors }
}
async function finish(context: BrowserContext, errors: string[]) {
  await context.close()
  expect(errors).toEqual([])
}
const companyField = (editor: Locator, label: string) =>
  editor.locator('.filter-label').filter({ hasText: label }).locator('..')
const dealerField = (editor: Locator) => companyField(editor, 'Дилер (опционально)')
const distributorField = (editor: Locator) => companyField(editor, 'Дистрибьютор (опционально)')
const option = (page: Page, name: string) =>
  page.locator('.custom-scrollbar').getByRole('button', { name: new RegExp('^' + name + ' ·') })
async function openField(page: Page, field: Locator, query = '22296') {
  await field.getByRole('button').first().click()
  await page.getByPlaceholder('Название или ИНН', { exact: true }).last().fill(query)
}
async function choose(page: Page, field: Locator, alias: string) {
  await openField(page, field, fixture!.companies[alias]!.name)
  await option(page, fixture!.companies[alias]!.name).click()
}
async function clear(page: Page, field: Locator, name: string) {
  await field.getByRole('button').first().click()
  await page.locator('.custom-scrollbar').getByRole('button', { name, exact: true }).last().click()
}
async function editorPage(page: Page) {
  await page.goto('/workspace/monetization')
  await page.getByRole('button', { name: 'Создать условия монетизации', exact: true }).click()
  const editor = page.locator('.program-editor')
  await expect(editor).toBeVisible()
  return editor
}
async function csrf(context: BrowserContext) {
  const cookie = (await context.cookies(fixture!.base_url)).find(item => item.name === 'csrfToken')
  if (!cookie) throw new Error('Missing isolated CSRF cookie')
  return { 'X-CSRF-Token': cookie.value }
}
const money = (value: string) => new Intl.NumberFormat('ru-RU', {
  minimumFractionDigits: 0, maximumFractionDigits: 2,
}).format(Number(value)) + ' ₽'

for (const width of [768, 1440]) {
  test('dependent companies, optional selection and clearing at ' + width + 'px', async ({ browser }) => {
    const { context, page, errors } = await session(browser, 'admin', width)
    try {
      const editor = await editorPage(page)
      const labels = await editor.locator('.program-grid-three').first().locator('.filter-label').allTextContents()
      expect(labels).toEqual(['Лизинговая компания *', 'Дистрибьютор (опционально)', 'Дилер (опционально)'])
      await choose(page, distributorField(editor), 'distributor')
      await openField(page, dealerField(editor))
      await expect(option(page, fixture!.companies.dealer!.name)).toBeVisible()
      await expect(option(page, fixture!.companies.group_dealer!.name)).toBeVisible()
      await expect(option(page, fixture!.companies.dealer2!.name)).toHaveCount(0)
      await expect(option(page, fixture!.companies.inactive_group_dealer!.name)).toHaveCount(0)
      await option(page, fixture!.companies.dealer!.name).click()
      await clear(page, distributorField(editor), 'Любой дистрибьютор')
      await expect(dealerField(editor)).toContainText(fixture!.companies.dealer!.name)
      await openField(page, distributorField(editor))
      await expect(option(page, fixture!.companies.distributor!.name)).toBeVisible()
      await expect(option(page, fixture!.companies.distributor2!.name)).toHaveCount(0)
      await option(page, fixture!.companies.distributor!.name).click()
      await clear(page, dealerField(editor), 'Любой дилер')
      await expect(distributorField(editor)).toContainText(fixture!.companies.distributor!.name)
      await clear(page, distributorField(editor), 'Любой дистрибьютор')
      await choose(page, dealerField(editor), 'dealer2')
      await openField(page, distributorField(editor))
      await expect(option(page, fixture!.companies.distributor!.name)).toHaveCount(0)
      await expect(option(page, fixture!.companies.distributor2!.name)).toHaveCount(0)
      await page.keyboard.press('Escape')
      await expect(dealerField(editor)).toContainText(fixture!.companies.dealer2!.name)
      await editor.screenshot({ path: test.info().outputPath('dependent-companies-' + width + '.png') })
    } finally { await finish(context, errors) }
  })
}

test('a delayed real lookup cannot overwrite options after its distributor was cleared', async ({ browser }) => {
  const { context, page, errors } = await session(browser)
  let release: () => void = () => {}
  const gate = new Promise<void>(resolve => { release = resolve })
  let arrived: () => void = () => {}
  const started = new Promise<void>(resolve => { arrived = resolve })
  let held = false
  try {
    const editor = await editorPage(page)
    await choose(page, distributorField(editor), 'distributor')
    await page.route('**/api/v1/monetization/lookups/companies?**', async route => {
      const url = new URL(route.request().url())
      if (!held && url.searchParams.get('kind') === 'dealer' && url.searchParams.has('distributor_company_id')) {
        held = true
        const response = await route.fetch()
        arrived()
        await gate
        await route.fulfill({ response })
      } else await route.continue()
    })
    await dealerField(editor).getByRole('button').first().click()
    await started
    await clear(page, distributorField(editor), 'Любой дистрибьютор')
    await openField(page, dealerField(editor))
    await expect(option(page, fixture!.companies.dealer2!.name)).toBeVisible()
    release()
    await expect(option(page, fixture!.companies.dealer2!.name)).toBeVisible()
    await option(page, fixture!.companies.dealer2!.name).click()
    await expect(dealerField(editor)).toContainText(fixture!.companies.dealer2!.name)
  } finally { release(); await finish(context, errors) }
})

test('real creation form preserves the limit through approval and shows the exact threshold', async ({ browser }) => {
  const { context, page, errors } = await session(browser)
  try {
    const editor = await editorPage(page)
    await editor.getByLabel('Название *', { exact: true }).fill('22296 UI maximum ' + fixture!.browser_vin)
    await choose(page, companyField(editor, 'Лизинговая компания *'), 'leasing')
    await choose(page, distributorField(editor), 'distributor')
    await choose(page, dealerField(editor), 'dealer')
    await editor.getByLabel('Дата начала *', { exact: true }).fill('2026-01-01')
    await editor.getByPlaceholder('VIN (разовые условия)').fill(fixture!.browser_vin)
    await editor.locator('.source-field select').selectOption('exchange')
    const expense = editor.locator('.condition-row').first()
    const income = editor.locator('.condition-row').nth(1)
    await expense.getByLabel('Значение (%)', { exact: true }).fill('5')
    await expense.getByLabel('Максимум, ₽', { exact: true }).fill('100000')
    await income.getByRole('button', { name: 'Стоимость имущества по договору', exact: true }).click()
    await page.getByRole('button', { name: 'Сумма расхода', exact: true }).click()
    await income.getByLabel('Значение (%)', { exact: true }).fill('30')
    const posted = page.waitForResponse(response => response.request().method() === 'POST'
      && response.url().endsWith('/admin/monetization/programs'))
    await editor.getByRole('button', { name: 'Сохранить условия', exact: true }).click()
    const saved = await posted
    expect(saved.status(), await saved.text()).toBe(201)
    expect(saved.request().postDataJSON().sources[0].expenses[0].max).toBe('100000')
    const program = await saved.json()
    expect(Number(program.sources[0].expenses[0].max)).toBe(100000)
    const leasing = await session(browser, 'leasing')
    try {
      const approved = await leasing.context.request.put('/api/v1/exchange/bids/' + fixture!.browser_bid.bid_id + '/approve', { headers: await csrf(leasing.context) })
      expect(approved.status(), await approved.text()).toBe(200)
    } finally { await finish(leasing.context, leasing.errors) }
    const listed = await context.request.get('/api/v1/monetization/deals', { params: { page_size: 100 } })
    expect(listed.status()).toBe(200)
    const items: { id: string; application_number: string }[] = (await listed.json()).items
    const deal = items.find(item => item.application_number === fixture!.browser_bid.application_number)
    expect(deal).toBeDefined()
    await page.goto('/workspace/monetization?deal=' + deal!.id)
    const modal = page.getByRole('dialog')
    await expect(modal.locator('.expense-amount .deal-original-terms strong')).toHaveText(money('100000'))
    await expect(modal.locator('.expense-amount .clip-note')).toContainText('выше максимума')
    await expect(modal.locator('.expense-amount .clip-note')).toContainText(money('100000'))
    await expect(modal.locator('.deal-amount').filter({ hasText: 'Дилер (Доход)' }).locator('.deal-original-terms strong')).toHaveText(money('30000'))
    await page.reload()
    await expect(modal.locator('.expense-amount .deal-original-terms strong')).toHaveText(money('100000'))
  } finally { await finish(context, errors) }
})

for (const width of [768, 1440]) {
  test('saved expense and income boundaries remain visible after reload at ' + width + 'px', async ({ browser }) => {
    const { context, page, errors } = await session(browser, 'admin', width)
    try {
      for (const item of fixture!.cases) {
        await page.goto('/workspace/monetization?deal=' + item.deal_id)
        const modal = page.getByRole('dialog')
        for (const [side, amount, clip, limit] of [
          ['expense', item.expense, item.expense_clip, item.expense_limit],
          ['income', item.income, item.income_clip, item.income_limit],
        ] as const) {
          const row = side === 'expense' ? modal.locator('.expense-amount')
            : modal.locator('.deal-amount').filter({ hasText: 'Дилер (Доход)' })
          await expect(row.locator('.deal-original-terms strong')).toHaveText(money(amount))
          if (clip === 'none') await expect(row.locator('.clip-note')).toHaveCount(0)
          else {
            await expect(row.locator('.clip-note')).toContainText(clip === 'max' ? 'выше максимума' : 'ниже минимума')
            await expect(row.locator('.clip-note')).toContainText(money(limit!))
          }
        }
        expect(await modal.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
      }
      await page.getByRole('dialog').screenshot({ path: test.info().outputPath('limits-' + width + '.png') })
    } finally { await finish(context, errors) }
  })
}

test('participant reads its own bounded income and cannot create conditions', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'dealer')
  try {
    const item = fixture!.cases.find(candidate => candidate.kind === 'income_maximum')!
    await page.goto('/workspace/monetization?deal=' + item.deal_id)
    const modal = page.getByRole('dialog')
    await expect(modal.locator('.deal-original-terms strong')).toHaveText(money('25000'))
    await expect(modal.locator('.clip-note')).toContainText('выше максимума')
    await expect(modal.getByRole('button', { name: 'Изменить суммы', exact: true })).toHaveCount(0)
    await modal.locator('button[aria-label="Закрыть"]').click()
    await page.getByRole('tab', { name: 'Условия монетизации', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Создать условия монетизации', exact: true })).toHaveCount(0)
  } finally { await finish(context, errors) }
})

test('manual new conditions may exceed the original maximum while its capped snapshot stays intact', async ({ browser }) => {
  const financial = JSON.parse(readFileSync('/tmp/carcraft-22296-monetization/financial.manifest.json', 'utf8')) as {
    marker: string; deals: Record<string, string>
  }
  expect(financial.marker).toBe('monetization-22296-financial')
  const { context, page, errors } = await session(browser)
  try {
    await page.goto('/workspace/monetization?deal=' + financial.deals.manual_override)
    const modal = page.getByRole('dialog')
    const expense = modal.locator('.expense-amount')
    await expect(expense.locator('.deal-original-terms strong')).toHaveText(money('100000'))
    await expect(expense.locator('.deal-new-terms strong')).toHaveText(money('144180'))
    await expect(expense.locator('.deal-original-terms .clip-note')).toContainText(money('100000'))
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    await expense.getByLabel('Сумма, ₽', { exact: true }).fill('125000')
    await expect(expense.locator('.terms-hint').first()).toContainText(money('125000'))
    const saved = page.waitForResponse(response => response.request().method() === 'POST'
      && response.url().endsWith('/adjust-conditions'))
    await modal.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect((await saved).status()).toBe(200)
    await expect(expense.locator('.deal-new-terms strong')).toHaveText(money('125000'))
    await page.reload()
    await expect(expense.locator('.deal-original-terms strong')).toHaveText(money('100000'))
    await expect(expense.locator('.deal-new-terms strong')).toHaveText(money('125000'))
    await expect(expense.locator('.deal-original-terms .clip-note')).toContainText(money('100000'))
    await expect(expense.locator('.deal-new-terms .clip-note')).toHaveCount(0)
  } finally { await finish(context, errors) }
})
