import { expect, test, type Route } from '@playwright/test'
import type { CommerceApplicationItem } from '../../../features/commerce/types'

const USER_ID = '45a010c8-228e-482e-9e36-10ac6f6da801'
const CLIENT_COMPANY_ID = '45a010c8-228e-482e-9e36-10ac6f6da802'
const SELLER_1_ID = '45a010c8-228e-482e-9e36-10ac6f6da803'
const SELLER_2_ID = '45a010c8-228e-482e-9e36-10ac6f6da804'
const APPLICATION_ID = '45a010c8-228e-482e-9e36-10ac6f6da899'
const ITEM_1_ID = '1d9a3fc0-0f11-451e-bacc-fea1ea642c46'
const ITEM_2_ID = '918cfb7e-a144-4daa-aaef-76ecba12f533'

const specialEquipmentItems: CommerceApplicationItem[] = [
  {
    type: 'special_equipment',
    id: ITEM_1_ID,
    item_id: ITEM_1_ID,
    title: 'Погрузчик АМКОДОР 352С',
    image_url: null,
    detail_url: null,
    quantity: 1,
    unit_price: '5000000',
    total_price: '5000000',
    currency_code: 'RUB',
    status: 'active',
    item_role: 'offer',
    snapshot: { mark: 'АМКОДОР', model: '352С', seller_company_id: SELLER_1_ID },
    leasing_purpose: 'business',
    region: null,
    regions: [],
    comment: null,
  },
  {
    type: 'special_equipment',
    id: ITEM_2_ID,
    item_id: ITEM_2_ID,
    title: 'Трактор МТЗ Беларус 82.1',
    image_url: null,
    detail_url: null,
    quantity: 1,
    unit_price: '7000000',
    total_price: '7000000',
    currency_code: 'RUB',
    status: 'active',
    item_role: 'offer',
    snapshot: { mark: 'МТЗ', model: 'Беларус 82.1', seller_company_id: SELLER_2_ID },
    leasing_purpose: 'business',
    region: null,
    regions: [],
    comment: null,
  },
]

test.describe('Allow multiple sellers in a single leasing application', () => {
  test('successfully creates leasing application uniting items from different sellers', async ({ page }) => {
    let postLeasingApplicationPayload: any = null

    await page.route('**/api/v1/**', async (route: Route) => {
      const request = route.request()
      const url = request.url()
      const method = request.method()
      const parsedUrl = new URL(url)
      const path = parsedUrl.pathname

      if (path === '/api/v1/auth/me') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            user: {
              id: USER_ID,
              email: 'client@example.com',
              role: 'client',
              is_active: true,
              can_create_applications: true,
            },
          }),
        })
      }

      if (path === '/api/v1/users/me/company-select-history') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ company_id: CLIENT_COMPANY_ID }),
        })
      }

      if (path === '/api/v1/users/me/companies') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            companies: [
              {
                id: CLIENT_COMPANY_ID,
                name: 'ООO Клиент Лизинга',
                inn: '7701000001',
                kpp: '770101001',
                legal_address: 'Москва, ул. Ленина, 1',
                status: 'ACTIVE',
              },
            ],
          }),
        })
      }

      if (path === '/api/v1/users/me' && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: USER_ID,
            email: 'client@example.com',
            role: 'client',
            company_id: CLIENT_COMPANY_ID,
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

      if (url.includes('/cart/lines') && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [
              {
                cart_item_id: ITEM_1_ID,
                product_id: ITEM_1_ID,
                product_type: 'special_equipment',
                quantity: 1,
                unit_price: '5000000',
                total_price: '5000000',
                seller_company_id: SELLER_1_ID,
                title: 'Погрузчик АМКОДОР 352С',
                is_selected: true,
              },
              {
                cart_item_id: ITEM_2_ID,
                product_id: ITEM_2_ID,
                product_type: 'special_equipment',
                quantity: 1,
                unit_price: '7000000',
                total_price: '7000000',
                seller_company_id: SELLER_2_ID,
                title: 'Трактор МТЗ Беларус 82.1',
                is_selected: true,
              },
            ],
          }),
        })
      }

      if (url.includes('/special-equipment/cart-items') && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            items: [
              {
                id: ITEM_1_ID,
                product_id: ITEM_1_ID,
                seller_company_id: SELLER_1_ID,
                quantity: 1,
                is_selected: true,
              },
              {
                id: ITEM_2_ID,
                product_id: ITEM_2_ID,
                seller_company_id: SELLER_2_ID,
                quantity: 1,
                is_selected: true,
              },
            ],
          }),
        })
      }

      if (url.includes('/special-equipment/leasing-applications') && method === 'POST') {
        postLeasingApplicationPayload = JSON.parse(request.postData() || '{}')
        return route.fulfill({
          status: 201,
          headers: {
            Location: `/api/v1/applications/${APPLICATION_ID}`,
          },
          contentType: 'application/json',
          body: JSON.stringify({
            application_id: APPLICATION_ID,
            source_type: 'platform',
            item_id: ITEM_1_ID,
            product_id: ITEM_1_ID,
            item_ids: [ITEM_1_ID, ITEM_2_ID],
            product_ids: [ITEM_1_ID, ITEM_2_ID],
            status: 'active',
            item_status: 'active',
          }),
        })
      }

      if (url.includes(`/applications/${APPLICATION_ID}`) && method === 'GET') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: APPLICATION_ID,
            display_number: 'APP-MULTI-SELLER-1',
            status: 'active',
            current_stage: 'leasing_companies',
            company_id: CLIENT_COMPANY_ID,
            dealer_company_id: null,
            total_amount: '12000000',
            down_payment: '2400000',
            down_payment_percent: 20,
            lease_term_months: 36,
            items: specialEquipmentItems,
            vehicles: [],
            services: [],
            equipments: [],
          }),
        })
      }

      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      })
    })

    const baseUrl = test.info().project.use.baseURL || 'https://test.multileasing.ru'
    const hostname = new URL(baseUrl).hostname
    await page.context().addCookies([{
      name: 'accessToken',
      value: 'mock-token',
      domain: hostname,
      path: '/',
    }])

    await page.setViewportSize({ width: 1280, height: 900 })

    await page.addInitScript(({ userId, companyId, item1Id, item2Id, seller1Id, seller2Id }) => {
      window.localStorage.setItem('leadgen_auth_token', 'mock-token')
      const checkoutState = {
        currentStep: 1,
        selectedCompanyId: companyId,
        commerceItems: [
          {
            item: {
              ref: { type: 'special_equipment', id: item1Id },
              title: 'Погрузчик АМКОДОР 352С',
              price: 5000000,
              currency_code: 'RUB',
              seller_company_id: seller1Id,
            },
            cart_item_ids: [item1Id],
            quantity: 1,
          },
          {
            item: {
              ref: { type: 'special_equipment', id: item2Id },
              title: 'Трактор МТЗ Беларус 82.1',
              price: 7000000,
              currency_code: 'RUB',
              seller_company_id: seller2Id,
            },
            cart_item_ids: [item2Id],
            quantity: 1,
          },
        ],
        calculation: {
          total_amount: 12000000,
          down_payment: 2400000,
          down_payment_percent: 20,
          lease_term_months: 36,
        },
      }
      window.localStorage.setItem(`checkout-state:u${userId}`, JSON.stringify(checkoutState))
      window.localStorage.setItem('checkout-state:guest', JSON.stringify(checkoutState))
    }, {
      userId: USER_ID,
      companyId: CLIENT_COMPANY_ID,
      item1Id: ITEM_1_ID,
      item2Id: ITEM_2_ID,
      seller1Id: SELLER_1_ID,
      seller2Id: SELLER_2_ID,
    })

    await page.goto('/application/new', { waitUntil: 'domcontentloaded' })

    // Expect application creation form to render without error
    await expect(page.locator('text=Одна лизинговая заявка не может объединять')).not.toBeVisible()

    // Find submit button and submit application
    const submitBtn = page.getByRole('button', { name: 'Далее' })
    await expect(submitBtn).toBeVisible()
    await submitBtn.click()

    // Expect navigation to application page
    await expect(page).toHaveURL(new RegExp(`/application/${APPLICATION_ID}\\?step=items`), { timeout: 10_000 })

    // Verify payload sent to special-equipment/leasing-applications
    expect(postLeasingApplicationPayload).not.toBeNull()
    expect(postLeasingApplicationPayload.company_id).toBe(CLIENT_COMPANY_ID)
    expect(postLeasingApplicationPayload.cart_item_ids).toEqual([ITEM_1_ID, ITEM_2_ID])

    // Verify error is NOT shown on the resulting page
    await expect(page.locator('text=Одна лизинговая заявка не может объединять')).not.toBeVisible()
  })
})
