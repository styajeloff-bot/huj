import { expect, test, type Route } from '@playwright/test'
import type { CommerceApplicationItem } from '../../../features/commerce/types'

const USER_ID = '36b010c8-228e-482e-9e36-10ac6f6da701'
const COMPANY_ID = '36b010c8-228e-482e-9e36-10ac6f6da702'
const APPLICATION_ID = '36b010c8-228e-482e-9e36-10ac6f6da79e'
const LINE_ID = '36b010c8-228e-482e-9e36-10ac6f6da704'

const specialEquipmentItem: CommerceApplicationItem = {
  type: 'special_equipment',
  id: LINE_ID,
  item_id: LINE_ID,
  title: 'Экскаватор-погрузчик',
  image_url: null,
  detail_url: null,
  quantity: 1,
  unit_price: '5000000',
  total_price: '5000000',
  currency_code: 'RUB',
  status: 'active',
  item_role: 'offer',
  snapshot: { mark: 'JCB', model: '3CX' },
  leasing_purpose: 'special_equipment', // Legacy / invalid purpose
  region: null,
  regions: [],
  comment: null,
}

test.describe('leasing_purpose normalization & user-friendly error sanitization', () => {
  test('normalizes invalid legacy leasing_purpose to null when saving items', async ({ page }) => {
    let putPayload: any = null

    await page.route('**/api/v1/**', async (route: Route) => {
      const request = route.request()
      const url = request.url()
      const method = request.method()

      if (url.includes('/users/me') && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: USER_ID,
            email: 'client@example.com',
            role: 'client',
            company_id: COMPANY_ID,
          }),
        })
      }

      if (url.includes('/users/me/company-select-history')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ company_id: COMPANY_ID }),
        })
      }

      if (url.includes('/users/me/companies')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            companies: [
              {
                id: COMPANY_ID,
                name: 'Тестовая компания',
                inn: '7701000001',
                kpp: '770101001',
                legal_address: 'Москва, ул. Ленина, 1',
                status: 'ACTIVE',
              },
            ],
          }),
        })
      }

      if (url.includes('/section-visibility/public')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ sections: [] }),
        })
      }

      if (url.includes('/applications/leasing-purposes')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            purposes: [
              { purpose_name: 'business', purpose_display_name: 'Для предпринимательской деятельности' },
              { purpose_name: 'personal', purpose_display_name: 'Личное пользование' },
              { purpose_name: 'other', purpose_display_name: 'Прочее' },
            ],
          }),
        })
      }

      if (url.includes('/applications/leasing-regions')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            regions: [
              { region_name: 'r077', region_display_name: 'Москва', region_number: '77' },
              { region_name: 'r078', region_display_name: 'Санкт-Петербург', region_number: '78' },
            ],
          }),
        })
      }

      if (url.includes(`/api/v1/applications/${APPLICATION_ID}/items`) && method === 'PUT') {
        putPayload = JSON.parse(request.postData() || '{}')
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ ok: true, items: putPayload.items }),
        })
      }

      if (url.includes(`/api/v1/applications/${APPLICATION_ID}`) && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: APPLICATION_ID,
            status: 'draft',
            company_id: COMPANY_ID,
            items: [specialEquipmentItem],
            vehicles: [],
            total_amount: 5000000,
            down_payment: 1000000,
            down_payment_percent: 20,
            lease_term_months: 36,
          }),
        })
      }

      return route.continue()
    })

    await page.goto(`/application/${APPLICATION_ID}?step=items`)

    // Verify item title is visible
    await expect(page.locator('text=Экскаватор-погрузчик')).toBeVisible()

    // Click "Создать заявку"
    const submitBtn = page.locator('button:has-text("Создать заявку")')
    await expect(submitBtn).toBeVisible()
    await submitBtn.click()

    // Verify that the payload sent to PUT /items normalized the legacy purpose to null
    await expect.poll(() => putPayload).not.toBeNull()
    expect(putPayload.items[0].leasing_purpose).toBeNull()
  })

  test('masks technical snake_case errors and shows user-friendly message', async ({ page }) => {
    await page.route('**/api/v1/**', async (route: Route) => {
      const request = route.request()
      const url = request.url()
      const method = request.method()

      if (url.includes('/users/me') && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: USER_ID,
            email: 'client@example.com',
            role: 'client',
            company_id: COMPANY_ID,
          }),
        })
      }

      if (url.includes('/users/me/company-select-history')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ company_id: COMPANY_ID }),
        })
      }

      if (url.includes('/users/me/companies')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            companies: [
              {
                id: COMPANY_ID,
                name: 'Тестовая компания',
                inn: '7701000001',
                kpp: '770101001',
                legal_address: 'Москва, ул. Ленина, 1',
                status: 'ACTIVE',
              },
            ],
          }),
        })
      }

      if (url.includes('/applications/leasing-purposes')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            purposes: [
              { purpose_name: 'business', purpose_display_name: 'Для предпринимательской деятельности' },
            ],
          }),
        })
      }

      if (url.includes('/applications/leasing-regions')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ regions: [] }),
        })
      }

      if (url.includes(`/api/v1/applications/${APPLICATION_ID}/items`) && method === 'PUT') {
        // Return 422 with technical error detail
        return route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Некорректное значение leasing_purpose' }),
        })
      }

      if (url.includes(`/api/v1/applications/${APPLICATION_ID}`) && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: APPLICATION_ID,
            status: 'draft',
            company_id: COMPANY_ID,
            items: [specialEquipmentItem],
            vehicles: [],
          }),
        })
      }

      return route.continue()
    })

    await page.goto(`/application/${APPLICATION_ID}?step=items`)

    // Click "Создать заявку"
    const submitBtn = page.locator('button:has-text("Создать заявку")')
    await submitBtn.click()

    // Assert that technical message with "leasing_purpose" is NOT visible to user
    await expect(page.locator('text=leasing_purpose')).not.toBeVisible()

    // Assert that safe fallback message is displayed
    await expect(page.locator('text=Не удалось сохранить позиции заявки')).toBeVisible()
  })

  test('displays clear human-readable business error without masking', async ({ page }) => {
    await page.route('**/api/v1/**', async (route: Route) => {
      const request = route.request()
      const url = request.url()
      const method = request.method()

      if (url.includes('/users/me') && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: USER_ID,
            email: 'client@example.com',
            role: 'client',
            company_id: COMPANY_ID,
          }),
        })
      }

      if (url.includes('/users/me/company-select-history')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ company_id: COMPANY_ID }),
        })
      }

      if (url.includes('/users/me/companies')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            companies: [
              {
                id: COMPANY_ID,
                name: 'Тестовая компания',
                inn: '7701000001',
                kpp: '770101001',
                legal_address: 'Москва, ул. Ленина, 1',
                status: 'ACTIVE',
              },
            ],
          }),
        })
      }

      if (url.includes('/applications/leasing-purposes')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ purposes: [] }),
        })
      }

      if (url.includes('/applications/leasing-regions')) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ regions: [] }),
        })
      }

      if (url.includes(`/api/v1/applications/${APPLICATION_ID}/items`) && method === 'PUT') {
        // Return 422 with friendly Russian message
        return route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Пожалуйста, выберите цель лизинга из списка' }),
        })
      }

      if (url.includes(`/api/v1/applications/${APPLICATION_ID}`) && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: APPLICATION_ID,
            status: 'draft',
            company_id: COMPANY_ID,
            items: [specialEquipmentItem],
            vehicles: [],
          }),
        })
      }

      return route.continue()
    })

    await page.goto(`/application/${APPLICATION_ID}?step=items`)

    // Click "Создать заявку"
    const submitBtn = page.locator('button:has-text("Создать заявку")')
    await submitBtn.click()

    // Assert that the friendly Russian message IS displayed
    await expect(page.locator('text=Пожалуйста, выберите цель лизинга из списка')).toBeVisible()
  })
})
