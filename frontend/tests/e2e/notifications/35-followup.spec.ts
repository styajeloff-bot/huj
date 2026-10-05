import { readFileSync } from 'node:fs'
import { expect, test, type Browser, type Locator, type Page } from '@playwright/test'

const runtimeDir = '/tmp/carcraft-notifications35-followup-v2-runtime'
const baseURL = 'http://localhost:18048'
type Role = 'client' | 'dealer' | 'leasing_company'
interface Manifest {
  marker: string
  leasing_company_id: string
  exchange_request_id: string
  companies: Record<string, string>
  users: Record<Role, { id: string; email: string }>
  followup: { navigation_application_id: string; navigation_application_number: string; other_lca_id: string; other_final_event_id: string }
}
interface Notice {
  id: string; action_url: string; title: string; message: string; is_read: boolean
  application_id: string | null
  data: { event_id: string; event_type: string; new_values?: { lca_status?: string } }
}
test.skip(process.env.NOTIFICATIONS35_E2E !== '1', 'Explicit isolated notifications35 runtime required')
test.use({ baseURL, viewport: { width: 1280, height: 900 }, trace: 'off' })
test.describe.configure({ mode: 'serial' })

function manifest(): Manifest {
  if (process.env.NOTIFICATIONS35_E2E !== '1') throw new Error('Local fixture opt-in required')
  const value: Manifest = JSON.parse(readFileSync(`${runtimeDir}/fixtures.secret.json`, 'utf8'))
  if (value.marker !== 'tz35-runtime' || !value.followup?.navigation_application_id) throw new Error('Missing follow-up fixture')
  for (const role of ['client', 'dealer', 'leasing_company'] as const) {
    if (value.users[role]?.email !== `${role}@notifications35.test`) throw new Error('Non-fixture user')
  }
  return value
}

async function rolePage(browser: Browser, role: Role) {
  const context = await browser.newContext({ baseURL, storageState: `${runtimeDir}/browser-${role}.secret.json`, viewport: { width: 1280, height: 900 } })
  return { context, page: await context.newPage() }
}

async function notices(page: Page): Promise<Notice[]> {
  const response = await page.request.get('/api/v1/notifications?limit=100')
  expect(response.status()).toBe(200)
  return (await response.json()).notifications
}

async function awaitNotice(page: Page, applicationId: string, event: string, status?: string) {
  let result: Notice | undefined
  await expect.poll(async () => {
    result = (await notices(page)).find(item => item.application_id === applicationId && item.data?.event_type === event
      && (!status || item.data.new_values?.lca_status === status))
    return Boolean(result)
  }, { timeout: 45000, intervals: [500, 1000] }).toBe(true)
  return result!
}

async function openCenter(page: Page) {
  await page.getByRole('button', { name: /^Уведомления(?:,|$)/ }).first().click()
  const center = page.locator('[data-storefront-block="client.notifications"].fixed')
  await expect(center).toBeVisible()
  return center
}

async function clickNotice(page: Page, notice: Notice, surface: 'center' | 'page') {
  if (surface === 'page') await page.goto('/notifications')
  const container = surface === 'center' ? await openCenter(page) : page
  const link = container.locator(`[data-notification-id="${notice.id}"]`)
  await expect(link).toBeVisible({ timeout: 15000 })
  await link.focus()
  await expect(link).toBeFocused()
  await link.press('Enter')
}

async function expectNotificationSection(notice: Notice, section: 'preliminary' | 'documents' | 'final') {
  const target = new URL(notice.action_url, baseURL)
  expect(target.searchParams.get('section')).toBe(section)
  expect(target.searchParams.has('step')).toBe(false)
}

async function expectSection(page: Page, section: 'preliminary' | 'documents' | 'final', title: string, kind?: 'preliminary' | 'final') {
  const [queryKey, queryValue] = section === 'documents'
    ? ['section', 'documents']
    : ['step', section === 'preliminary' ? '4' : '5']
  await expect(page).toHaveURL(new RegExp(`[?&]${queryKey}=${queryValue}(?:&|$)`))
  await expect(page.getByRole('heading', { name: `Офферы: ${title}`, exact: true })).toBeVisible({ timeout: 15000 })
  if (kind) await expect(page.getByRole('button', { name: kind === 'final' ? 'Итоговое КП' : 'Предварительное КП', exact: true }))
    .toHaveAttribute('aria-pressed', 'true')
}

test('client notification clicks follow real preliminary, document and final decisions', async ({ browser }) => {
  test.setTimeout(180000)
  const state = manifest()
  const applicationId = state.followup.navigation_application_id
  const client = await rolePage(browser, 'client')
  const lc = await rolePage(browser, 'leasing_company')
  const errors: string[] = []
  const writes: string[] = []
  client.page.on('pageerror', error => errors.push(error.message))
  client.page.on('request', request => {
    if (request.method() === 'PUT' && request.url().includes('/questionnaire')) writes.push(request.url())
  })
  const lcPath = (suffix: string) => `/api/v1/leasing/applications/${applicationId}/${suffix}?leasing_company_id=${state.leasing_company_id}`
  const publish = async (kind: 'preliminary' | 'final') => {
    const proposal = await lc.page.request.put(lcPath(`proposals/${kind}`), { data: {
      total_amount: '1000000', down_payment: '200000', down_payment_percent: '20', lease_term_months: 36,
      monthly_payment: kind === 'preliminary' ? '30000' : '31000', buyout_amount: '0',
    } })
    expect(proposal.status(), await proposal.text()).toBe(200)
    const decision = await lc.page.request.put(lcPath('decision'), { data: { action: 'approve', kind } })
    expect(decision.status(), await decision.text()).toBe(200)
  }
  try {
    await publish('preliminary')
    const preliminary = await awaitNotice(client.page, applicationId, 'leasing.company_decision_received', 'approved_scoring')
    await expectNotificationSection(preliminary, 'preliminary')
    await client.page.goto('/')
    await clickNotice(client.page, preliminary, 'center')
    await expectSection(client.page, 'preliminary', 'Предварительные', 'preliminary')
    await client.page.reload()
    await expectSection(client.page, 'preliminary', 'Предварительные', 'preliminary')

    const requested = await lc.page.request.put(lcPath('request-documents'), { data: {
      requestedDocuments: [{ source: 'custom', display_name: 'ТЗ35 проверка навигации' }],
    } })
    expect(requested.status(), await requested.text()).toBe(200)
    const documents = await awaitNotice(client.page, applicationId, 'leasing.documents_requested')
    await expectNotificationSection(documents, 'documents')
    // Query-only navigation within the same mounted application must see new LCA state.
    await clickNotice(client.page, documents, 'center')
    await expectSection(client.page, 'documents', 'Доп. документы')
    await expect(client.page.getByText('ТЗ35 проверка навигации', { exact: true }).first()).toBeVisible()

    await publish('final')
    let finalNotices: Notice[] = []
    await expect.poll(async () => {
      finalNotices = (await notices(client.page)).filter(item => item.application_id === applicationId
        && item.data?.event_type === 'leasing.company_decision_received' && item.data.new_values?.lca_status === 'approved_final')
      return finalNotices.length
    }, { timeout: 45000, intervals: [500, 1000] }).toBeGreaterThanOrEqual(2)
    // The second LC's initial approved-final fact is a synthetic fixture; both
    // inboxes are delivered through the real outbox/Kafka consumer, without API mocks.
    const otherFinal = finalNotices.find(item => item.data.event_id === state.followup.other_final_event_id)!
    const final = finalNotices.find(item => item.data.event_id !== state.followup.other_final_event_id)!
    expect(otherFinal).toBeDefined()
    expect(final).toBeDefined()
    expect(otherFinal.id).not.toBe(final.id)
    expect(otherFinal.action_url).toBe(final.action_url)
    await expectNotificationSection(final, 'final')
    await clickNotice(client.page, final, 'page')
    await expectSection(client.page, 'final', 'Итоговое', 'final')
    await client.page.reload()
    await expectSection(client.page, 'final', 'Итоговое', 'final')
    await client.page.goBack()
    await expect(client.page).toHaveURL(`${baseURL}/notifications`)
    await client.page.goForward()
    await expectSection(client.page, 'final', 'Итоговое', 'final')
    const newTab = await client.context.newPage()
    try {
      await newTab.goto(final.action_url)
      await expectSection(newTab, 'final', 'Итоговое', 'final')
    } finally { await newTab.close() }
    await client.page.getByRole('button', { name: 'Предварительное КП', exact: true }).click()
    await expect(client.page.getByRole('button', { name: 'Итоговое КП', exact: true })).toHaveAttribute('aria-pressed', 'false')
    await clickNotice(client.page, otherFinal, 'center')
    await expectSection(client.page, 'final', 'Итоговое', 'final')
    await expect(client.page).toHaveURL(new RegExp(`[?&]notification_id=${otherFinal.id}(?:&|$)`))
    await clickNotice(client.page, preliminary, 'center')
    await expectSection(client.page, 'final', 'Итоговое', 'final')
    await expect(client.page.getByRole('status').filter({ hasText: 'Состояние заявки изменилось' })).toBeVisible()
    expect(writes).toEqual([])
    expect(errors).toEqual([])
  } finally { await client.context.close(); await lc.context.close() }
})

test('exchange notices remain visible in their real filters on both notification surfaces', async ({ browser }) => {
  const state = manifest()
  const { context, page } = await rolePage(browser, 'dealer')
  try {
    const notice = (await notices(page)).find(item => item.data?.event_type === 'exchange.request_published' && item.action_url.includes(state.exchange_request_id))
    expect(notice).toBeDefined()
    await page.goto('/notifications')
    for (const surface of ['page', 'center'] as const) {
      const container = surface === 'center' ? await openCenter(page) : page
      const filter = container.getByRole('combobox').filter({ has: page.locator('option[value="exchange_new_request"]') })
      for (const legacy of ['approval', 'general', 'system']) await expect(filter.locator(`option[value="${legacy}"]`)).toHaveCount(0)
      const response = page.waitForResponse(value => value.request().method() === 'GET'
        && new URL(value.url()).pathname === '/api/v1/notifications'
        && new URL(value.url()).searchParams.get('notification_type') === 'exchange_new_request')
      await filter.selectOption('exchange_new_request')
      expect((await response).status()).toBe(200)
      await expect(container.locator(`[data-notification-id="${notice!.id}"]`)).toBeVisible()
      await expect(container.getByText('Не удалось загрузить уведомления. Повторите попытку.')).toHaveCount(0)
    }
  } finally { await context.close() }
})

test('unselected LC sees a red event badge and keeps read-state independent of the outcome', async ({ browser }) => {
  test.setTimeout(90000)
  const state = manifest()
  const client = await rolePage(browser, 'client')
  const lc = await rolePage(browser, 'leasing_company')
  const applicationId = state.followup.navigation_application_id
  const assertNegative = async (container: Page | Locator, notice: Notice) => {
    const link = container.locator(`[data-notification-id="${notice.id}"]`)
    await expect(link).toBeVisible()
    await expect(link.getByText('Клиент выбрал другую лизинговую компанию', { exact: true })).toBeVisible()
    await expect(link.getByText('Решение ЛК', { exact: true })).toHaveClass(/bg-red-100 text-red-800/)
    await expect(link.locator('div.bg-red-100.text-red-700')).toBeVisible()
    await link.focus(); await expect(link).toBeFocused()
  }
  try {
    const selected = await client.page.request.post(`/api/v1/applications/${applicationId}/lca/${state.followup.other_lca_id}/select`)
    expect(selected.status(), await selected.text()).toBe(200)
    const negative = await awaitNotice(lc.page, applicationId, 'leasing.company_not_selected')
    await lc.page.goto('/notifications')
    await assertNegative(lc.page, negative)
    const read = await lc.page.request.patch(`/api/v1/notifications/${negative.id}`, { data: { is_read: true } })
    expect(read.status()).toBe(200)
    await lc.page.reload()
    await assertNegative(lc.page, negative)
    await assertNegative(await openCenter(lc.page), negative)
  } finally { await client.context.close(); await lc.context.close() }
})
