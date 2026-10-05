import { test, expect, type Browser, type BrowserContext, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const runtime = process.env.QUESTIONNAIRE_E2E_RUNTIME || '/runtime'
const manifestPath = path.join(runtime, 'manifest.json')
interface BankFixture { application_id: string; request_id: string; provided_request_id: string; provided_form: { accounts: Array<Record<string, unknown>> } }
interface Manifest { bank_accounts: { v1: BankFixture; v2: BankFixture } }
const manifest: Manifest | null = fs.existsSync(manifestPath) ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : null
const baseURL = process.env.E2E_BASE_URL || 'http://localhost:18286'
const sessions: BrowserContext[] = []
const serverErrors: string[] = []

async function client(browser: Browser): Promise<Page> {
  const context = await browser.newContext({ storageState: path.join(runtime, 'client.storage.json'), baseURL, viewport: { width: 768, height: 1000 } })
  sessions.push(context)
  const page = await context.newPage()
  page.on('response', response => {
    if (new URL(response.url()).pathname.startsWith('/api/v1/') && response.status() >= 500) serverErrors.push(`${response.status()} ${new URL(response.url()).pathname}`)
  })
  return page
}

async function accounts(page: Page, applicationId: string) {
  const response = await page.request.get(`/api/v1/questionnaire/${applicationId}`)
  expect(response.ok()).toBeTruthy()
  return (await response.json()).questionnaire.open_bank_accounts
}

async function requestHistory(page: Page, fixture: BankFixture) {
  const response = await page.request.get(`/api/v1/applications/${fixture.application_id}/document-requests`)
  expect(response.ok()).toBeTruthy()
  const history = await response.json() as { batches: Array<{ items: Array<{ id: string; form_schema: { schema_version: number }; form_data: unknown; attachments?: unknown[] }> }> }
  return history.batches.flatMap(batch => batch.items)
}

test.describe('22286 saved bank-account form versions — real API', () => {
  test.setTimeout(90_000)
  test.skip(!manifest, 'Run the isolated 22286 API fixtures first')
  test.afterEach(async () => {
    await Promise.all(sessions.splice(0).map(context => context.close()))
    expect(serverErrors.splice(0)).toEqual([])
  })

  test('a pending v1 request keeps its three fields and historical response after the catalog upgrade', async ({ browser }) => {
    expect(manifest?.bank_accounts?.v1).toBeDefined()
    const fixture = manifest!.bank_accounts.v1
    const page = await client(browser)
    await page.goto(`/application/${fixture.application_id}`)
    await expect(page.getByText('Банк исторического ответа', { exact: false }).first()).toBeVisible({ timeout: 30_000 })
    await page.getByRole('button', { name: 'Ответить на запрос', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByLabel(/Название банка/)).toBeVisible()
    await expect(dialog.getByLabel(/Корр\./)).toHaveCount(0)
    await expect(dialog.getByText('(необязательно)', { exact: true })).toBeVisible()
    await dialog.getByLabel(/Название банка/).fill('Браузер банк v1')
    await dialog.getByLabel(/^БИК/).fill('044525225')
    await dialog.getByLabel(/^Расчётный счёт/).fill('40702810000000000041')
    await dialog.getByRole('button', { name: 'Отправить', exact: true }).click()
    await expect(dialog).toHaveCount(0)
    const expected = [{ bank: { name: 'Браузер банк v1', bik: '044525225' }, acc_number: '40702810000000000041' }]
    await expect.poll(() => accounts(page, fixture.application_id)).toEqual(expected)
    const history = await requestHistory(page, fixture)
    expect(history.find(item => item.id === fixture.request_id)).toMatchObject({ form_schema: { schema_version: 1 }, form_data: { accounts: expected } })
    expect(history.find(item => item.id === fixture.provided_request_id)).toMatchObject({ form_schema: { schema_version: 1 }, form_data: fixture.provided_form })
    await page.reload()
    await expect(page.getByText('Браузер банк v1', { exact: false }).first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('Банк исторического ответа', { exact: false }).first()).toBeVisible()
    await page.screenshot({ path: path.join(runtime, 'bank-accounts-v1-history-768.png'), fullPage: true })
  })

  test('a new v2 request saves four required fields for each row without files and shows them in history', async ({ browser }) => {
    expect(manifest?.bank_accounts?.v2).toBeDefined()
    const fixture = manifest!.bank_accounts.v2
    const page = await client(browser)
    await page.goto(`/application/${fixture.application_id}`)
    await page.getByRole('button', { name: 'Ответить на запрос', exact: true }).click({ timeout: 30_000 })
    const dialog = page.getByRole('dialog')
    await expect(dialog.getByLabel(/Наименование банка/)).toBeVisible()
    await expect(dialog.getByLabel(/^Корр\. счёт/)).toBeVisible()
    await expect(dialog.getByText('(необязательно)', { exact: true })).toBeVisible()
    await dialog.getByLabel(/Наименование банка/).fill('Браузер банк v2 первый')
    await dialog.getByLabel(/^БИК/).fill('044525225')
    await dialog.getByLabel(/^Расчётный счёт/).fill('40702810000000000051')
    await dialog.getByRole('button', { name: 'Отправить', exact: true }).click()
    await expect(dialog.getByRole('alert')).toHaveText('Корреспондентский счёт должен содержать 20 цифр')
    await dialog.getByLabel(/^Корр\. счёт/).fill('30101810400000000225')
    await dialog.getByRole('button', { name: 'Добавить ещё счёт', exact: true }).click()
    await dialog.getByLabel(/Наименование банка/).nth(1).fill('Браузер банк v2 второй')
    await dialog.getByLabel(/^БИК/).nth(1).fill('044525974')
    await dialog.getByLabel(/^Расчётный счёт/).nth(1).fill('40702810000000000052')
    await dialog.getByLabel(/^Корр\. счёт/).nth(1).fill('30101810145250000974')
    await dialog.getByRole('button', { name: 'Добавить ещё счёт', exact: true }).click()
    await expect(dialog.getByLabel(/Наименование банка/)).toHaveCount(3)
    await dialog.getByRole('button', { name: 'Удалить счёт', exact: true }).last().click()
    await expect(dialog.getByLabel(/Наименование банка/)).toHaveCount(2)
    expect(await dialog.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBeTruthy()
    await page.screenshot({ path: path.join(runtime, 'bank-accounts-v2-form-768.png'), fullPage: true })
    await dialog.getByRole('button', { name: 'Отправить', exact: true }).click()
    await expect(dialog).toHaveCount(0)
    const expected = [
      { bank: 'Браузер банк v2 первый', bik: '044525225', acc_number: '40702810000000000051', correspondent_account: '30101810400000000225' },
      { bank: 'Браузер банк v2 второй', bik: '044525974', acc_number: '40702810000000000052', correspondent_account: '30101810145250000974' },
    ]
    await expect.poll(() => accounts(page, fixture.application_id)).toEqual(expected)
    const history = await requestHistory(page, fixture)
    expect(history.find(item => item.id === fixture.request_id)).toMatchObject({ form_schema: { schema_version: 2 }, form_data: { accounts: expected }, attachments: [] })
    expect(history.find(item => item.id === fixture.provided_request_id)).toMatchObject({ form_schema: { schema_version: 2 }, form_data: fixture.provided_form })
    await page.reload()
    await expect(page.getByText('Браузер банк v2 первый', { exact: false }).first()).toContainText('корр. счёт 30101810400000000225', { timeout: 30_000 })
    await expect(page.getByText('Браузер банк v2 второй', { exact: false }).first()).toContainText('корр. счёт 30101810145250000974')
    await page.screenshot({ path: path.join(runtime, 'bank-accounts-v2-history-768.png'), fullPage: true })
  })
})
