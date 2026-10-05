import { readFileSync } from 'node:fs'
import { expect, test, type Browser, type BrowserContext, type Page } from '@playwright/test'

interface Application { id: string; source_type: string | null; display_number: string; deal_id?: string }
interface Fixture { base_url: string; storage_states: Record<string, string>; applications: Record<string, Application>; storefront_slug: string; user_ids: Record<string, string>; products: Record<string, string>; companies: Record<string, { company_id: string }> }
const enabled = process.env.APPLICATION_SOURCES_E2E === '1'
const fixture: Fixture | null = enabled
  ? JSON.parse(readFileSync(process.env.APPLICATION_SOURCES_FIXTURE ?? '/tmp/carcraft-22320-e2e/manifest.json', 'utf8'))
  : null
test.skip(!enabled, 'Requires the isolated task 22320 application')
test.setTimeout(90_000)
const labels = { platform: 'Заявка с сайта платформы МЛ', dealer_site: 'Заявка с сайта дилера', distributor_site: 'Заявка с сайта дистрибьютора' } as const
const prefixes = { platform: 'AP', dealer_site: 'ADE', distributor_site: 'ADI' } as const

async function actor(browser: Browser, role: string, width = 1440) {
  const context = await browser.newContext({ baseURL: fixture!.base_url, storageState: fixture!.storage_states[role], viewport: { width, height: 1000 } })
  const page = await context.newPage()
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  return { context, page, errors }
}
async function finish(context: BrowserContext, errors: string[]) {
  await context.close()
  expect(errors).toEqual([])
}
const listPath = (role: string) => role === 'leasing' ? '/workspace/leasing-applications' : '/workspace/applications'
const apiPath = (role: string) => role === 'admin' ? '/api/v1/admin/applications' : role === 'leasing' ? '/api/v1/leasing/applications' : '/api/v1/applications'
function searchInput(page: Page, role: string) {
  return role === 'admin' ? page.getByPlaceholder('Номер заявки, имя, email, ИНН...') : page.locator(role === 'leasing' ? '#leasing-application-search' : '#application-search')
}
async function search(page: Page, role: string, value: string) {
  const response = page.waitForResponse(item => {
    const url = new URL(item.url())
    return item.request().method() === 'GET' && url.pathname === apiPath(role) && url.searchParams.get('search') === value
  })
  await searchInput(page, role).fill(value)
  expect((await response).status()).toBe(200)
}

for (const role of ['admin', 'dealer', 'distributor', 'leasing']) {
  test(role + ' real list filters, source badges, prefix search and detail', async ({ browser }, info) => {
    const session = await actor(browser, role)
    const { page } = session
    try {
      await page.goto(listPath(role))
      const filter = page.getByTestId('application-source-filter')
      await expect(filter).toBeVisible()
      for (const source of Object.keys(labels) as (keyof typeof labels)[]) {
        const app = fixture!.applications['draft-' + source]!
        const number = prefixes[source] + ' ' + app.display_number
        await search(page, role, prefixes[source].toLowerCase() + app.display_number.replace(/\D/g, ''))
        const heading = page.getByRole('heading', { name: 'Заявка ' + number, exact: true })
        await expect(heading).toBeVisible()
        await expect(page.getByTestId('application-source').first()).toHaveText(labels[source])
        await filter.getByRole('checkbox', { name: labels[source], exact: true }).check()
        await expect(heading).toBeVisible()
        const wrong = source === 'platform' ? 'ADI' : 'AP'
        await search(page, role, wrong + app.display_number)
        await expect(heading).toHaveCount(0)
        await filter.getByRole('checkbox', { name: labels[source], exact: true }).uncheck()
      }
      const app = fixture!.applications['draft-dealer_site']!
      await search(page, role, app.display_number)
      const heading = page.getByRole('heading', { name: 'Заявка ADE ' + app.display_number, exact: true })
      await expect(heading).toBeVisible()
      if (role === 'admin') {
        const card = page.locator('.card').filter({ has: heading })
        await card.getByRole('button', { name: 'Подробнее', exact: true }).click()
        await expect(card.getByTestId('application-source')).toHaveCount(2)
      } else if (role === 'leasing') {
        await page.getByRole('link', { name: 'Открыть заявку', exact: true }).click()
        await expect(page.getByTestId('application-source')).toHaveText(labels.dealer_site)
        await expect(page.getByRole('heading', { name: 'Заявка ADE ' + app.display_number, exact: true })).toBeVisible()
      } else {
        await page.getByRole('button', { name: 'Открыть заявку', exact: true }).click()
        await expect(page.getByTestId('application-source')).toHaveCount(2)
      }
      await page.screenshot({ path: info.outputPath(role + '-source-detail.png'), fullPage: true })
    } finally { await finish(session.context, session.errors) }
  })
}

test('real client hides source in list and application while retaining ordinary number search', async ({ browser }, info) => {
  const session = await actor(browser, 'client')
  const { page } = session
  try {
    const app = fixture!.applications['draft-distributor_site']!
    await page.goto('/cabinet')
    await expect(page.locator('#client-application-search')).toBeVisible()
    await page.locator('#client-application-search').fill(app.display_number)
    await expect(page.getByRole('heading', { name: 'Заявка ' + app.display_number, exact: true })).toBeVisible()
    await expect(page.getByTestId('application-source')).toHaveCount(0)
    await expect(page.getByTestId('application-source-filter')).toHaveCount(0)
    const response = await session.context.request.get('/api/v1/applications/' + app.id)
    expect(response.status()).toBe(200)
    expect(JSON.stringify(await response.json())).not.toContain('"source_type"')
    await page.goto('/application/' + app.id)
    await expect(page.getByTestId('application-source')).toHaveCount(0)
    await expect(page.getByTestId('application-source-filter')).toHaveCount(0)
    await expect(page.getByText('ADI ' + app.display_number, { exact: false })).toHaveCount(0)
    await page.screenshot({ path: info.outputPath('client-no-source.png'), fullPage: true })
  } finally { await finish(session.context, session.errors) }
})

test('real 768 desktop supports source multi-filter without hiding labels', async ({ browser }, info) => {
  const session = await actor(browser, 'dealer', 768)
  try {
    const { page } = session
    await page.goto('/workspace/applications')
    const filter = page.getByTestId('application-source-filter')
    await filter.getByRole('checkbox', { name: labels.dealer_site, exact: true }).check()
    const response = page.waitForResponse(item => {
      const url = new URL(item.url())
      return url.pathname === '/api/v1/applications' && url.searchParams.get('source_type') === 'dealer_site,distributor_site'
    })
    await filter.getByRole('checkbox', { name: labels.distributor_site, exact: true }).check()
    expect((await response).status()).toBe(200)
    await expect(page.getByTestId('application-source').first()).toBeVisible()
    for (const text of await page.getByTestId('application-source').allTextContents()) {
      expect([labels.dealer_site, labels.distributor_site]).toContain(text.trim())
    }
    await expect(filter.getByText(labels.distributor_site, { exact: true })).toBeVisible()
    await page.screenshot({ path: info.outputPath('dealer-multi-source-768.png'), fullPage: true })
  } finally { await finish(session.context, session.errors) }
})

test('real monetization deal presents the captured distributor source', async ({ browser }, info) => {
  const session = await actor(browser, 'admin')
  try {
    const app = fixture!.applications['application-distributor_site']!
    expect(app.deal_id).toBeTruthy()
    await session.page.goto('/workspace/monetization?deal=' + app.deal_id)
    const dialog = session.page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await expect(dialog.getByTestId('application-source')).toHaveText(labels.distributor_site)
    await expect(dialog).toContainText('ADI ' + app.display_number)
    await session.page.screenshot({ path: info.outputPath('monetization-distributor-source.png'), fullPage: true })
  } finally { await finish(session.context, session.errors) }
})

for (const storefront of [false, true]) {
  test('real UI creation sends ' + (storefront ? 'dealer_site from storefront' : 'platform from main site'), async ({ browser }, info) => {
    const session = await actor(browser, 'client')
    const admin = await actor(browser, 'admin')
    try {
      const prefix = storefront ? '/' + fixture!.storefront_slug : ''
      const api = '/api/v1' + (storefront ? '/storefronts/' + fixture!.storefront_slug : '')
      const product = fixture!.products[(storefront ? 'distributor' : 'dealer') + '/35']!
      const csrf = (await session.context.cookies()).find(cookie => cookie.name === 'csrfToken')!.value
      const cart = await session.context.request.post(api + '/special-equipment/cart-items', {
        headers: { 'X-CSRF-Token': csrf, Origin: fixture!.base_url },
        data: { product_id: product, quantity: 1 },
      })
      expect([200, 201], await cart.text()).toContain(cart.status())
      const cartItemId = (await cart.json()).cart_item.id
      const itemResponse = await session.context.request.get(api + '/commerce/items/special_equipment/' + product)
      expect(itemResponse.status()).toBe(200)
      const item = (await itemResponse.json()).item
      await session.page.goto(prefix + '/cabinet')
      // Start at the conditions screen with real server cart data, as restored
      // by a returning shopper; all submission and persistence use real APIs.
      await session.page.evaluate(({ userId, companyId, item, cartItemId }) => {
        localStorage.setItem('checkout-state:u' + userId, JSON.stringify({
          currentStep: 1, currentStage: 'leasing_companies', applicationId: null,
          applicationCreateIdempotencyKey: crypto.randomUUID(),
          selectedCompanyId: companyId, selectedApplicationCompany: null,
          vehicles: [], applicationItems: [], calculation: null,
          commerceItems: [{ item, quantity: 1, custom_price: null, comment: '',
            equipments: [], services: [], leasing_purpose: 'special_equipment',
            leasing_purpose_comment: null, regions: [], cart_item_ids: [cartItemId] }],
        }))
      }, { userId: fixture!.user_ids.client!, companyId: fixture!.companies.client!.company_id, item, cartItemId })
      await session.page.goto(prefix + '/cart/conditions')
      await session.page.locator('select').first().selectOption(fixture!.companies.client!.company_id)
      await session.page.screenshot({ path: info.outputPath(storefront ? 'storefront-create-conditions.png' : 'platform-create-conditions.png'), fullPage: true })
      const createResponse = session.page.waitForResponse(response =>
        new URL(response.url()).pathname === api + '/special-equipment/leasing-applications'
          && response.request().method() === 'POST')
      await session.page.getByRole('button', { name: 'Далее', exact: true }).click()
      const response = await createResponse
      expect([200, 201], await response.text()).toContain(response.status())
      expect(response.request().postDataJSON().source_type).toBe(storefront ? 'dealer_site' : 'platform')
      const created = await response.json()
      expect(created).not.toHaveProperty('source_type')
      await expect(session.page).toHaveURL(new RegExp('/application/' + created.application_id))
      const persisted = await admin.context.request.get(api + '/applications/' + created.application_id)
      expect(persisted.status(), await persisted.text()).toBe(200)
      expect((await persisted.json()).source_type).toBe(storefront ? 'distributor_site' : 'platform')
      await expect(session.page.getByTestId('application-source')).toHaveCount(0)
    } finally {
      await finish(session.context, session.errors)
      await finish(admin.context, admin.errors)
    }
  })
}
