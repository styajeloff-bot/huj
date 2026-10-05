import { randomUUID } from 'node:crypto'
import { expect, test, type APIRequestContext, type APIResponse, type Page } from '@playwright/test'
import {
  getE2EFixtureManifest,
  resetE2EFixture,
  type JsonRecord,
} from '../special-equipment/support/fixtures'
import { appUrl } from '../special-equipment/support/runtime'

const SPECIAL_CART_URL = '/api/v1/special-equipment/cart-items'
const SPECIAL_DRAFT_URL = '/api/v1/special-equipment/leasing-applications'

const json = async (response: APIResponse): Promise<JsonRecord> => {
  expect(response.ok(), `${response.status()} ${response.url()}`).toBeTruthy()
  return response.json() as Promise<JsonRecord>
}

const cartItems = async (request: APIRequestContext): Promise<JsonRecord[]> => {
  const payload = await json(await request.get(SPECIAL_CART_URL))
  expect(Array.isArray(payload.items)).toBeTruthy()
  return payload.items as JsonRecord[]
}

const addFixtureProductToCart = async (request: APIRequestContext): Promise<JsonRecord> => {
  const fixture = getE2EFixtureManifest()
  const added = await json(await request.post(SPECIAL_CART_URL, {
    data: { product_id: fixture.products.attachmentCompatible.id, quantity: 1, is_selected: true },
  }))
  expect(added.created).toBe(true)
  return added.cart_item as JsonRecord
}

const fixtureCompanyId = (): string => {
  const company = Object.values(getE2EFixtureManifest().companies)[0]
  if (!company || typeof company !== 'object' || Array.isArray(company)) {
    throw new Error('E2E fixture must provide a client company')
  }
  const id = (company as JsonRecord).id
  if (typeof id !== 'string') throw new Error('E2E fixture company.id must be a UUID string')
  return id
}

const selectFixtureCompany = async (page: Page): Promise<void> => {
  const companySelect = page.locator('select').filter({ has: page.locator('option') }).first()
  await expect(companySelect).toBeVisible()
  await companySelect.selectOption(fixtureCompanyId())
}

test.describe('Bitrix 22282 — очистка корзины при создании черновика', () => {
  test.use({ storageState: process.env.E2E_CLIENT_STORAGE_STATE })
  test.beforeEach(async () => { await resetE2EFixture() })

  test('special-only: сервер реально удаляет позицию при создании черновика, а второй шаг не делает DELETE', async ({ page, request }, testInfo) => {
    testInfo.annotations.push({ type: 'task', description: '22282' }, { type: 'kind', description: 'full-stack' })
    const cartItem = await addFixtureProductToCart(request)
    const deleteRequests: string[] = []
    page.on('request', browserRequest => {
      if (browserRequest.method() === 'DELETE') deleteRequests.push(new URL(browserRequest.url()).pathname)
    })

    await page.goto(appUrl('/cart'), { waitUntil: 'domcontentloaded' })
    await page.getByRole('button', { name: 'Получить специальное предложение', exact: true }).click()
    await expect(page).toHaveURL(/\/application\/new(?:\?|$)/)
    await selectFixtureCompany(page)

    const creation = page.waitForResponse(response => (
      response.request().method() === 'POST'
      && new URL(response.url()).pathname === SPECIAL_DRAFT_URL
    ))
    await page.getByRole('button', { name: 'Далее', exact: true }).click()
    expect((await creation).status()).toBe(201)
    await expect(page).toHaveURL(/\/application\/[0-9a-f-]+\?step=items$/i)

    expect(await cartItems(request)).toEqual([])
    expect(deleteRequests).toEqual([])
    expect(String(cartItem.id)).toMatch(/^[0-9a-f-]{36}$/i)
  })

  test('special-only: ошибка создания не меняет состав реальной корзины', async ({ request }, testInfo) => {
    testInfo.annotations.push(
      { type: 'task', description: '22282' },
      { type: 'AC', description: 'creation-error-preserves-cart' },
      { type: 'kind', description: 'full-stack' },
    )
    const cartItem = await addFixtureProductToCart(request)
    const before = await cartItems(request)

    const failed = await request.post(SPECIAL_DRAFT_URL, {
      headers: { 'Idempotency-Key': randomUUID() },
      data: {
        company_id: fixtureCompanyId(),
        cart_item_ids: [randomUUID()],
        leasing_purpose: 'special_equipment',
        down_payment_percent: '10',
        lease_term_months: 36,
      },
    })
    expect(failed.status()).toBe(409)
    expect(await cartItems(request)).toEqual(before)
    expect(before.map(item => item.id)).toEqual([cartItem.id])
  })
})
