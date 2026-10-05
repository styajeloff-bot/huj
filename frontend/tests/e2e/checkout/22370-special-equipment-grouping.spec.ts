import { expect, test, type Page, type Route } from '@playwright/test'
import type { CommerceApplicationItem } from '../../../features/commerce/types'

const USER_ID = '22370000-0000-4000-8000-000000000001'
const COMPANY_ID = '22370000-0000-4000-8000-000000000002'
const APPLICATION_ID = '22370000-0000-4000-8000-000000000003'
const GROUP_1_ID = '22370000-0000-4000-8000-000000000010'
const GROUP_2_ID = '22370000-0000-4000-8000-000000000020'
const LINE_1_ID = '22370000-0000-4000-8000-000000000011'
const LINE_2_ID = '22370000-0000-4000-8000-000000000021'

const item1: CommerceApplicationItem = {
  type: 'special_equipment',
  id: LINE_1_ID,
  item_id: GROUP_1_ID,
  title: 'FAW J7 Тягач',
  image_url: null,
  detail_url: null,
  quantity: 15,
  unit_price: '1500000',
  total_price: '22500000',
  currency_code: 'RUB',
  status: 'active',
  item_role: 'offer',
  snapshot: { mark: 'FAW', model: 'J7' },
  leasing_purpose: null,
  region: null,
  regions: [],
  comment: null,
  product_ids: Array.from({ length: 15 }, (_, i) => `22370000-0000-4000-8000-00000000100${i.toString(16)}`),
}

const item2: CommerceApplicationItem = {
  type: 'special_equipment',
  id: LINE_2_ID,
  item_id: GROUP_2_ID,
  title: 'Тонар Полуприцеп',
  image_url: null,
  detail_url: null,
  quantity: 8,
  unit_price: '800000',
  total_price: '6400000',
  currency_code: 'RUB',
  status: 'active',
  item_role: 'offer',
  snapshot: { mark: 'Тонар', model: 'Полуприцеп' },
  leasing_purpose: null,
  region: null,
  regions: [],
  comment: null,
  product_ids: Array.from({ length: 8 }, (_, i) => `22370000-0000-4000-8000-00000000200${i.toString(16)}`),
}

test.describe('Bitrix 22370 — ТС в заявке группируются по количеству', () => {
  test('шаг «Техника в заявке» отображает 2 позиции (15 шт. и 8 шт.), а не 23 карточки', async ({ page }) => {
    let savedItems: CommerceApplicationItem[] = [{ ...item1 }, { ...item2 }]
    let putItemsPayload: unknown = null

    await page.route('**/api/v1/**', async (route: Route) => {
      const request = route.request()
      const url = new URL(request.url())
      const path = url.pathname
      const method = request.method()

      if (path === '/api/v1/auth/me') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user: {
              id: USER_ID,
              email: 'client@example.com',
              phone: '+76660002629',
              role: 'client',
              is_active: true,
              can_create_applications: true,
            },
          }),
        })
      }

      if (path === '/api/v1/users/me/companies') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            companies: [
              {
                id: COMPANY_ID,
                name: 'ООО Компания 22370',
                can_create_applications: true,
              },
            ],
          }),
        })
      }

      if (path === '/api/v1/applications/' + APPLICATION_ID && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: APPLICATION_ID,
            status: 'draft',
            company_id: COMPANY_ID,
            company: { id: COMPANY_ID, name: 'ООO Компания 22370', inn: '7700223700' },
            items: savedItems,
            items_count: 23,
            total_items_price: '28900000',
            vehicles: [],
            questionnaire: null,
            leasing_company_applications: [],
          }),
        })
      }

      if (path === '/api/v1/applications/' + APPLICATION_ID + '/items' && method === 'PUT') {
        putItemsPayload = request.postDataJSON()
        const updates = (putItemsPayload as { items: Array<Partial<CommerceApplicationItem>> }).items
        savedItems = savedItems.map((item) => {
          const update = updates.find((u) => u.id === item.id)
          return update ? { ...item, ...update } : item
        })
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true }),
        })
      }

      if (path === '/api/v1/applications/leasing-purposes') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            purposes: [
              { purpose_name: 'business', purpose_display_name: 'Для бизнеса' },
              { purpose_name: 'expansion', purpose_display_name: 'Расширение парка' },
            ],
          }),
        })
      }

      if (path === '/api/v1/applications/leasing-regions') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            regions: [
              { region_name: 'moscow', region_display_name: 'Москва', region_number: '77' },
              { region_name: 'spb', region_display_name: 'Санкт-Петербург', region_number: '78' },
            ],
          }),
        })
      }

      if (path === '/api/v1/applications/' + APPLICATION_ID + '/leasing-responses') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ approval_offers: { preliminary: [], final: [] } }),
        })
      }

      if (path === '/api/v1/leasing-company-applications') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        })
      }

      if (path === '/api/v1/section-visibility/public') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            sections: [
              { key: 'cars', is_visible: true },
              { key: 'special_equipment', is_visible: true },
            ],
          }),
        })
      }

      if (path === '/api/v1/notifications') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ notifications: [], total_count: 0, unread_count: 0 }),
        })
      }

      if (path === '/api/v1/cart' || path.startsWith('/api/v1/cart/')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [], count: 0 }),
        })
      }

      if (path.startsWith('/api/v1/companies/')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ id: COMPANY_ID, name: 'ООО Компания 22370' }),
        })
      }

      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      })
    })

    // Navigate to items step
    await page.goto('/application/' + APPLICATION_ID + '?step=items', { waitUntil: 'domcontentloaded' })

    // Verify header and page loaded
    await expect(page.getByRole('heading', { name: 'Транспортные средства в заявке', exact: true })).toBeVisible({ timeout: 15_000 })

    // Verify exactly 2 vehicle cards are rendered (not 23!)
    const articles = page.locator('section[aria-labelledby="application-items-step-title"] article')
    await expect(articles).toHaveCount(2)

    // Verify first card: FAW J7 with quantity 15
    const card1 = articles.nth(0)
    await expect(card1.getByText('FAW J7 Тягач')).toBeVisible()
    await expect(card1.getByText('Количество: 15 шт.')).toBeVisible()

    // Verify second card: Tonar Trailer with quantity 8
    const card2 = articles.nth(1)
    await expect(card2.getByText('Тонар Полуприцеп')).toBeVisible()
    await expect(card2.getByText('Количество: 8 шт.')).toBeVisible()

    // Fill comment on the first card
    const commentInput = card1.locator('textarea')
    await commentInput.fill('Комментарий к первому ТС')

    // Submit items step
    const submitButton = page.getByRole('button', { name: 'Создать заявку', exact: true })
    await expect(submitButton).toBeEnabled()
    await submitButton.click()

    // Verify PUT /api/v1/applications/{id}/items was called with 2 items
    await expect(page).toHaveURL(new RegExp('/application/' + APPLICATION_ID + '\\?step=1$'))
    expect(putItemsPayload).not.toBeNull()
    const submittedItems = (putItemsPayload as { items: Array<unknown> }).items
    expect(submittedItems).toHaveLength(2)

    // Check header summary on step 1: shows "2 позиции · 23 единицы"
    const summaryHeader = page.locator('section[aria-labelledby="application-items-title"]')
    await expect(summaryHeader.getByText(/2\s+позици.*23\s+единиц/)).toBeVisible()
  })
})
