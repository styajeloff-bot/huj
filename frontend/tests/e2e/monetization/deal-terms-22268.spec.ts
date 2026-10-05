import { readFileSync } from 'node:fs'
import { expect, test, type Browser, type BrowserContext } from '@playwright/test'

type Role = 'admin' | 'dealer' | 'leasing' | 'distributor' | 'read_only' | 'outsider'
interface Amount { id: string; participant_type: string; amount: string; percent: string | null; expense_ref_amount_id: string | null }
interface Deal { id: string; revision: number; expenses: Amount[]; incomes: Amount[] }
interface Fixture { marker: string; base_url: string; storage_states: Record<Role, string>; deals: Record<string, string> }
const enabled = process.env.MONETIZATION_TERMS_E2E === '1'
const fixture: Fixture | null = enabled
  ? JSON.parse(readFileSync(process.env.MONETIZATION_TERMS_FIXTURE ?? '/tmp/carcraft-22268-e2e/terms.manifest.json', 'utf8')) : null
if (fixture && (fixture.marker !== 'monetization-22268' || !/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(fixture.base_url))) throw new Error('Use isolated task 22268 fixtures')
test.skip(!enabled, 'Requires real isolated app with saved-percentage fixtures')

async function session(browser: Browser, role: Role, width = 1280) {
  const context = await browser.newContext({ baseURL: fixture!.base_url, storageState: fixture!.storage_states[role], viewport: { width, height: 1000 } })
  const page = await context.newPage()
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  return { context, page, errors }
}
async function headers(context: BrowserContext) {
  const csrf = (await context.cookies(fixture!.base_url)).find(cookie => cookie.name === 'csrfToken')
  if (!csrf) throw new Error('Missing fixture CSRF cookie')
  return { 'X-CSRF-Token': csrf.value }
}
async function get(context: BrowserContext, id: string): Promise<Deal> {
  const result = await context.request.get('/api/v1/monetization/deals/' + id)
  expect(result.status()).toBe(200)
  return result.json()
}
const canonical = (value: string) => value.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
async function finish(context: BrowserContext, errors: string[]) { await context.close(); expect(errors).toEqual([]) }

for (const width of [768, 1280, 1920]) {
  test('real inline edit stores exact percentage and persists after reload at ' + width + 'px', async ({ browser }, testInfo) => {
    const { context, page, errors } = await session(browser, 'admin', width)
    try {
      const id = fixture!.deals['ui_' + width]!
      const deal = await get(context, id)
      const dealer = deal.incomes.find(item => item.participant_type === 'dealer')!
      await page.goto('/workspace/monetization?deal=' + id)
      const modal = page.getByRole('dialog')
      const row = modal.locator('[data-amount-id="' + dealer.id + '"]')
      await expect(row.locator('.deal-original-terms')).toContainText('0,8%')
      await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
      await expect(page.getByRole('dialog')).toHaveCount(1)
      await row.getByLabel('Сумма, ₽', { exact: true }).fill('1250')
      await expect(row.getByLabel('Процент', { exact: true })).toHaveValue('1.01')
      await modal.getByRole('button', { name: 'Отмена', exact: true }).click()
      expect((await get(context, id)).revision).toBe(deal.revision)
      await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
      await row.getByLabel('Процент', { exact: true }).fill('1')
      await expect(row.getByLabel('Сумма, ₽', { exact: true })).toHaveValue('1234.56')
      expect(await modal.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true)
      await modal.screenshot({ path: testInfo.outputPath('inline-' + width + '.png') })
      const response = page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/adjust-conditions'))
      await modal.getByRole('button', { name: 'Сохранить', exact: true }).click()
      expect((await response).status()).toBe(200)
      await expect(row.locator('.deal-new-terms .terms-percent')).toHaveText('1%')
      await expect(row.locator('.deal-new-terms strong')).toHaveText('1 234,56 ₽')
      await page.reload()
      await expect(row.locator('.deal-new-terms .terms-percent')).toHaveText('1%')
      await expect(modal.locator('.new-terms-badge')).toHaveText('Новые условия')
    } finally { await finish(context, errors) }
  })
}

test('real form rejects invalid income budget without a request', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const id = fixture!.deals.ui_main!
    const deal = await get(context, id)
    const dealer = deal.incomes.find(item => item.participant_type === 'dealer')!
    await page.goto('/workspace/monetization?deal=' + id)
    const modal = page.getByRole('dialog')
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    await modal.locator('[data-amount-id="' + dealer.id + '"]').getByLabel('Процент', { exact: true }).fill('99')
    await expect(modal.locator('.deal-budget-error')).toContainText('превышает расход')
    await expect(modal.getByRole('button', { name: 'Сохранить', exact: true })).toBeDisabled()
    await modal.getByRole('button', { name: 'Отмена', exact: true }).click()
    expect((await get(context, id)).revision).toBe(deal.revision)
  } finally { await finish(context, errors) }
})

test('real rounded percent resets all confirmations and each party reconfirms from the persisted card', async ({ browser }) => {
  const admin = await session(browser, 'admin')
  try {
    const id = fixture!.deals.ui_main!
    const initial = await get(admin.context, id)
    for (const role of ['leasing', 'dealer', 'distributor'] as const) {
      const actor = await session(browser, role)
      try {
        const response = await actor.context.request.post('/api/v1/monetization/deals/' + id + '/confirm', {
          headers: await headers(actor.context), data: { revision: initial.revision },
        })
        expect(response.status()).toBe(200)
      } finally { await finish(actor.context, actor.errors) }
    }
    await admin.page.goto('/workspace/monetization?deal=' + id)
    const modal = admin.page.getByRole('dialog')
    const dealer = initial.incomes.find(item => item.participant_type === 'dealer')!
    const row = modal.locator('[data-amount-id="' + dealer.id + '"]')
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    await row.getByLabel('Процент', { exact: true }).fill('0.805')
    await expect(row.getByLabel('Сумма, ₽', { exact: true })).toHaveValue('999.99')
    const saved = admin.page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/adjust-conditions'))
    await modal.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect((await saved).status()).toBe(200)
    for (const role of ['leasing', 'dealer', 'distributor', 'read_only'] as const) {
      const actor = await session(browser, role)
      try {
        await actor.page.goto('/workspace/monetization?deal=' + id)
        const card = actor.page.getByRole('dialog')
        await expect(card.locator('.new-terms-badge')).toBeVisible()
        await expect(card.getByRole('button', { name: 'Изменить суммы', exact: true })).toHaveCount(0)
        if (role === 'dealer') await expect(card.locator('.deal-new-terms .terms-percent')).toHaveText('0,81%')
        const confirm = card.getByRole('button', { name: 'Подтвердить', exact: true })
        if (role === 'read_only') await expect(confirm).toHaveCount(0)
        else {
          await expect(confirm).toBeEnabled()
          const response = actor.page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/confirm'))
          await confirm.click()
          expect((await response).status()).toBe(200)
          await expect(confirm).toHaveCount(0)
        }
      } finally { await finish(actor.context, actor.errors) }
    }
    await admin.page.reload()
    await expect(modal.getByRole('button', { name: 'Подтвердить оплату', exact: true })).toBeEnabled()
    await modal.getByRole('button', { name: 'Подтвердить оплату', exact: true }).click()
    await expect(modal.locator('.deal-state-actions')).toContainText('Оплачена')
    await expect(modal.locator('.new-terms-badge')).toBeVisible()
    await expect(modal.getByRole('button', { name: 'Изменить суммы', exact: true })).toHaveCount(0)
  } finally { await finish(admin.context, admin.errors) }
})

test('real stale revision preserves the draft and requires refresh', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const id = fixture!.deals.ui_stale!
    const initial = await get(context, id)
    const dealer = initial.incomes.find(item => item.participant_type === 'dealer')!
    await page.goto('/workspace/monetization?deal=' + id)
    const modal = page.getByRole('dialog')
    const row = modal.locator('[data-amount-id="' + dealer.id + '"]')
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    await row.getByLabel('Процент', { exact: true }).fill('1')
    const competing = await context.request.post('/api/v1/admin/monetization/deals/' + id + '/adjust-conditions', {
      headers: await headers(context), data: { revision: initial.revision, items: [{ deal_participant_amount_id: dealer.id, input_mode: 'percent', new_percent: '1.1' }] },
    })
    expect(competing.status()).toBe(200)
    const rejected = page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/adjust-conditions'))
    await modal.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect((await rejected).status()).toBe(409)
    await expect(row.getByLabel('Процент', { exact: true })).toHaveValue('1')
    await expect(modal.getByRole('alert').first()).toContainText('обновите')
    await modal.getByRole('button', { name: 'Отмена', exact: true }).click()
    await modal.getByRole('button', { name: 'Обновить', exact: true }).click()
    await expect(row.locator('.deal-new-terms .terms-percent')).toHaveText('1,1%')
  } finally { await finish(context, errors) }
})

for (const kind of ['fixed', 'clip', 'zero'] as const) {
  test('real ' + kind + ' source terms display correctly in inline editor', async ({ browser }) => {
    const { context, page, errors } = await session(browser, 'admin')
    try {
      const id = fixture!.deals['ui_' + kind]!
      const deal = await get(context, id)
      const dealer = deal.incomes.find(item => item.participant_type === 'dealer')!
      await page.goto('/workspace/monetization?deal=' + id)
      const modal = page.getByRole('dialog')
      const row = modal.locator('[data-amount-id="' + dealer.id + '"]')
      if (kind === 'fixed') await expect(row.locator('.deal-original-terms')).toContainText('Фиксированная сумма')
      if (kind === 'clip') {
        await expect(row.locator('.deal-original-terms .terms-percent')).toHaveText('1%')
        await expect(row.locator('.deal-original-terms .clip-note')).toContainText('максимум')
      }
      await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
      if (kind === 'zero') await expect(row.getByLabel('Процент', { exact: true })).toBeDisabled()
      else await expect(row.getByLabel('Процент', { exact: true })).toBeEnabled()
      await expect(row.getByLabel('Сумма, ₽', { exact: true })).toBeEnabled()
      await modal.getByRole('button', { name: 'Отмена', exact: true }).click()
    } finally { await finish(context, errors) }
  })
}

test('real dealer notification opens persisted new conditions in its company context', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'dealer')
  try {
    const id = fixture!.deals.ui_768!
    const deal = await get(context, id)
    const dealer = deal.incomes.find(item => item.participant_type === 'dealer')!
    interface Notice {
      id: string; title: string; message: string; action_url: string; type: string
      data: { event_type?: string; entity_id?: string; revision?: number }
    }
    interface Inbox { notifications: Notice[]; pagination: { pages: number } }
    let notice: Notice | undefined
    let noticePage = 1
    for (;;) {
      const response = await context.request.get('/api/v1/notifications', { params: { page: noticePage, limit: 20 } })
      expect(response.status()).toBe(200)
      const inbox: Inbox = await response.json()
      notice = inbox.notifications.find(item => item.data.event_type === 'monetization.deal_terms_changed'
        && item.data.entity_id === id && item.data.revision === deal.revision)
      if (notice || noticePage >= inbox.pagination.pages) break
      noticePage++
    }
    if (!notice) throw new Error('Missing delivered terms notification for ui_768 revision ' + deal.revision)
    expect(notice.type).toBe('system')
    expect(notice.message).toContain('Требуется повторное подтверждение')
    const target = new URL(notice.action_url, fixture!.base_url)
    expect(target.pathname).toBe('/workspace/monetization')
    expect(target.searchParams.get('deal')).toBe(id)
    expect(target.searchParams.get('notification_company_id')).toBeTruthy()

    for (let inboxPage = 1; inboxPage <= noticePage; inboxPage++) {
      const loaded = page.waitForResponse(response => {
        const url = new URL(response.url())
        return response.request().method() === 'GET' && url.pathname === '/api/v1/notifications'
          && url.searchParams.get('page') === String(inboxPage) && url.searchParams.get('limit') === '20'
      })
      if (inboxPage === 1) await page.goto('/notifications')
      else await page.getByRole('button', { name: 'Следующая', exact: true }).click()
      const response = await loaded
      expect(response.status()).toBe(200)
      const inbox: Inbox = await response.json()
      await expect(page.locator('[data-notification-id="' + inbox.notifications[0]!.id + '"]')).toBeVisible()
    }
    const notification = page.locator('[data-notification-id="' + notice.id + '"]')
    await expect(notification).toContainText(notice.title)
    await expect(notification).toContainText(notice.message)
    await notification.click()
    await expect(page).toHaveURL(url => url.pathname === target.pathname
      && url.searchParams.get('deal') === id
      && url.searchParams.get('notification_company_id') === target.searchParams.get('notification_company_id'))
    const modal = page.getByRole('dialog')
    const row = modal.locator('[data-amount-id="' + dealer.id + '"]')
    await expect(modal.locator('.new-terms-badge')).toHaveText('Новые условия')
    await expect(row.locator('.deal-new-terms .terms-percent')).toHaveText('1%')
    await expect(row.locator('.deal-new-terms strong')).toHaveText('1 234,56 ₽')
    await expect(modal.getByRole('button', { name: 'Изменить суммы', exact: true })).toHaveCount(0)
    expect((await get(context, id)).revision).toBe(deal.revision)
  } finally { await finish(context, errors) }
})

test('real cent remainder follows each group and permits saving an undistributed balance', async ({ browser }, testInfo) => {
  const { context, page, errors } = await session(browser, 'admin', 768)
  try {
    const id = fixture!.deals.ui_cent_groups!
    const deal = await get(context, id)
    const expense = deal.expenses.find(row => canonical(row.amount) === '100.01')!
    const otherExpense = deal.expenses.find(row => canonical(row.amount) === '200.02')!
    const emptyExpense = deal.expenses.find(row => canonical(row.amount) === '50.05')!
    const income = deal.incomes.find(row => row.expense_ref_amount_id === expense.id && canonical(row.amount) === '33.33')!
    await page.goto('/workspace/monetization?deal=' + id, { waitUntil: 'domcontentloaded' })
    const modal = page.getByRole('dialog')
    const group = modal.locator('.calculation-group').filter({ has: page.locator('[data-amount-id="' + expense.id + '"]') })
    const other = modal.locator('.calculation-group').filter({ has: page.locator('[data-amount-id="' + otherExpense.id + '"]') })
    const empty = modal.locator('.calculation-group').filter({ has: page.locator('[data-amount-id="' + emptyExpense.id + '"]') })
    const row = modal.locator('[data-amount-id="' + income.id + '"]')
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    await expect(group.locator('.deal-budget-remaining')).toContainText('36,67 ₽')
    await expect(other.locator('.deal-budget-remaining')).toContainText('129,99 ₽')
    await expect(empty.locator('.deal-budget-remaining')).toContainText('50,05 ₽')
    await row.getByLabel('Сумма, ₽', { exact: true }).fill('33.34')
    await expect(group.locator('.deal-budget-remaining')).toHaveText('Осталась не распределенная сумма 36,66 ₽')
    await expect(other.locator('.deal-budget-remaining')).toContainText('129,99 ₽')
    await expect(modal.locator('.deal-budget-error')).toHaveCount(0)
    const save = modal.getByRole('button', { name: 'Сохранить', exact: true })
    await expect(save).toBeEnabled()
    await row.getByLabel('Сумма, ₽', { exact: true }).fill('')
    await expect(group.locator('.deal-budget-remaining')).toHaveCount(0)
    await expect(save).toBeDisabled()
    await row.getByLabel('Сумма, ₽', { exact: true }).fill('33.34')
    const expenseInput = modal.locator('[data-amount-id="' + expense.id + '"]').getByLabel('Сумма, ₽', { exact: true })
    await expenseInput.fill('63.35')
    await expect(group.locator('.deal-budget-remaining')).toHaveCount(0)
    await expect(group.locator('.deal-budget-error')).toHaveCount(0)
    await expect(save).toBeEnabled()
    await expenseInput.fill('63.34')
    await expect(group.locator('.deal-budget-error')).toBeVisible()
    await expect(group.locator('.deal-budget-remaining')).toHaveCount(0)
    await expect(other.locator('.deal-budget-remaining')).toContainText('129,99 ₽')
    await expect(save).toBeDisabled()
    await expenseInput.fill('100.01')
    await expect(save).toBeEnabled()
    await modal.screenshot({ path: testInfo.outputPath('cent-remainder-768.png') })
    const response = page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/adjust-conditions'))
    await save.click()
    expect((await response).status()).toBe(200)
    expect(canonical((await get(context, id)).incomes.find(item => item.id === income.id)!.amount)).toBe('33.34')
    await page.reload({ waitUntil: 'domcontentloaded' })
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    await expect(group.locator('.deal-budget-remaining')).toContainText('36,66 ₽')
    await expect(save).toBeDisabled()
    await modal.getByRole('button', { name: 'Отмена', exact: true }).click()
    const dealer = await session(browser, 'dealer')
    try {
      await dealer.page.goto('/workspace/monetization?deal=' + id, { waitUntil: 'domcontentloaded' })
      await expect(dealer.page.getByRole('dialog')).toBeVisible()
      await expect(dealer.page.locator('.deal-budget-remaining')).toHaveCount(0)
    } finally { await finish(dealer.context, dealer.errors) }
  } finally { await finish(context, errors) }
})

test('real raw amount and percent round to hundredths on blur and Enter', async ({ browser }, testInfo) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const id = fixture!.deals.ui_cent_rounding!
    const deal = await get(context, id)
    const dealer = deal.incomes.find(item => item.participant_type === 'dealer')!
    expect(canonical(dealer.amount)).toBe('10.01')
    await page.goto('/workspace/monetization?deal=' + id, { waitUntil: 'domcontentloaded' })
    const modal = page.getByRole('dialog')
    const row = modal.locator('[data-amount-id="' + dealer.id + '"]')
    await expect(row.locator('.deal-original-terms strong')).toHaveText('10,01 ₽')
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    const amount = row.getByLabel('Сумма, ₽', { exact: true })
    const percent = row.getByLabel('Процент', { exact: true })
    await amount.fill('16.865')
    await expect(amount).toHaveValue('16.865')
    await amount.press('Tab')
    await expect(amount).toHaveValue('16.87')
    await expect(percent).toHaveValue('16.86')
    const savedAmount = page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/adjust-conditions'))
    await modal.getByRole('button', { name: 'Сохранить', exact: true }).click()
    expect((await savedAmount).status()).toBe(200)
    expect(canonical((await get(context, id)).incomes.find(item => item.id === dealer.id)!.amount)).toBe('16.87')
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    await percent.fill('23.38743238')
    await expect(percent).toHaveValue('23.38743238')
    await expect(amount).toHaveValue(/^23\.40?$/)
    const savedPercent = page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/adjust-conditions'))
    await percent.press('Enter')
    expect((await savedPercent).status()).toBe(200)
    const persisted = (await get(context, id)).incomes.find(item => item.id === dealer.id)!
    expect(canonical(persisted.percent!)).toBe('23.39')
    expect(canonical(persisted.amount)).toBe('23.4')
    await page.reload({ waitUntil: 'domcontentloaded' })
    await expect(row.locator('.deal-new-terms .terms-percent')).toHaveText('23,39%')
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    await expect(percent).toHaveValue('23.39')
    await expect(amount).toHaveValue(/^23\.40?$/)
    await modal.screenshot({ path: testInfo.outputPath('rounded-percent-1280.png') })
    await modal.getByRole('button', { name: 'Отмена', exact: true }).click()
  } finally { await finish(context, errors) }
})

test('real historical exact rate and ruble amount survive opening and changing another row', async ({ browser }) => {
  const { context, page, errors } = await session(browser, 'admin')
  try {
    const id = fixture!.deals.ui_cent_history!
    const initial = await get(context, id)
    const history = initial.incomes.find(item => canonical(item.percent ?? '') === '23.38743238')!
    expect(history).toBeDefined()
    await page.goto('/workspace/monetization?deal=' + id, { waitUntil: 'domcontentloaded' })
    const modal = page.getByRole('dialog')
    const row = modal.locator('[data-amount-id="' + history.id + '"]')
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    const percent = row.getByLabel('Процент', { exact: true })
    const amount = row.getByLabel('Сумма, ₽', { exact: true })
    await expect(percent).toHaveValue('23.39')
    await expect(amount).toHaveValue(canonical(history.amount))
    await percent.focus()
    await percent.press('Tab')
    const save = modal.getByRole('button', { name: 'Сохранить', exact: true })
    await expect(save).toBeDisabled()
    await modal.getByRole('button', { name: 'Отмена', exact: true }).click()
    expect((await get(context, id)).revision).toBe(initial.revision)
    await modal.getByRole('button', { name: 'Изменить суммы', exact: true }).click()
    const expense = initial.expenses[0]!
    const next = String(BigInt(expense.amount.split('.')[0]!) + BigInt(1))
    await modal.locator('[data-amount-id="' + expense.id + '"]').getByLabel('Сумма, ₽', { exact: true }).fill(next)
    await expect(percent).toHaveValue('23.39')
    await expect(amount).toHaveValue(canonical(history.amount))
    await expect(save).toBeEnabled()
    const response = page.waitForResponse(item => item.request().method() === 'POST' && item.url().endsWith('/adjust-conditions'))
    await save.click()
    expect((await response).status()).toBe(200)
    const preserved = (await get(context, id)).incomes.find(item => item.id === history.id)!
    expect(preserved.percent).toBe(history.percent)
    expect(preserved.amount).toBe(history.amount)
  } finally { await finish(context, errors) }
})
