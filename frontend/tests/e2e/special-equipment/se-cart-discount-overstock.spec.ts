import { execFileSync, spawnSync } from 'node:child_process'
import { expect, test, type Route } from '@playwright/test'

// Б24 22250: проверяем пользовательские поверхности, не внутренние composable-функции.
const oldPriceLabels = /Скидка:|Цена со скидкой|Примен[её]нные скидки|Цена без выгоды/
const normalizeText = (text: string) => text.replace(/\s+/g, ' ').trim()

const PRODUCT_ID = '44444444-0000-4000-8000-000000000001'
const CART_ITEM_ID = '44444444-0000-4000-8000-000000000002'
const BODY_COLOR_ID = '44444444-0000-4000-8000-000000000003'

const mockProductCard = {
  id: PRODUCT_ID,
  slug: 'faw-jiefang-j6p',
  detail_url: `/special-equipment/products/${PRODUCT_ID}/faw-jiefang-j6p`,
  mark: { id: '44444444-0000-4000-8000-000000000010', name: 'FAW' },
  model: { id: '44444444-0000-4000-8000-000000000011', name: 'Jiefang' },
  modification: { id: '44444444-0000-4000-8000-000000000012', name: 'J6P' },
  manufacture_year: 2025,
  body_color: { id: BODY_COLOR_ID, name: 'Белый' },
  price: '2881000',
  base_price: '4031000',
  special_price: '2881000',
  price_on_request: false,
  price_from: null,
  currency_code: 'RUB',
  publication_status: 'published',
  sale_status: 'available',
  primary_image: null,
  capabilities: {
    can_favorite: true,
    can_add_to_cart: true,
    can_lease: true,
    can_buy: true,
    can_preorder: true,
  },
  available_count: 2,
}

const mockCartItem = {
  id: CART_ITEM_ID,
  product_id: PRODUCT_ID,
  quantity: 2,
  allow_overstock: false,
  parent_item_id: null,
  transfer_id: null,
  is_selected: true,
  custom_price: null,
  comment: '',
  equipments: [],
  services: [],
  product: mockProductCard,
  available_count: 2,
  has_conflicts: false,
}

test.describe('Special Equipment Cart — Discount, Year/Color Order, and Overstock (specs/task_2026-09-24_18-43-01_MSK.md)', () => {
  let cartState = { ...mockCartItem }

  test.beforeEach(async ({ page }) => {
    cartState = { ...mockCartItem, allow_overstock: false, quantity: 2 }

    await page.route('**/api/v1/auth/**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user: { id: '44444444-0000-4000-8000-000000000099', role: 'client' } }),
      })
    })

    await page.route('**/api/v1/cart', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total_count: 0 }),
      })
    })

    await page.route(`**/api/v1/special-equipment/products/${PRODUCT_ID}**`, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: PRODUCT_ID,
          slug: 'faw-jiefang-j6p',
          detail_url: `/special-equipment/products/${PRODUCT_ID}/faw-jiefang-j6p`,
          modification: {
            id: '44444444-0000-4000-8000-000000000012',
            name: 'J6P',
            model: {
              id: '44444444-0000-4000-8000-000000000011',
              name: 'Jiefang',
              mark: { id: '44444444-0000-4000-8000-000000000010', name: 'FAW' },
            },
          },
          trim: null,
          manufacture_year: 2025,
          body_color: { id: BODY_COLOR_ID, name: 'Белый' },
          price: '2881000',
          base_price: '4031000',
          special_price: '2881000',
          price_on_request: false,
          price_from: null,
          currency_code: 'RUB',
          sale_status: 'available',
          primary_image: null,
          capabilities: {
            can_favorite: true,
            can_add_to_cart: true,
            can_lease: true,
            can_buy: true,
            can_preorder: true,
          },
          available_count: 2,
        }),
      })
    })

    await page.route('**/api/v1/special-equipment/cart-items', async (route: Route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [cartState] }),
        })
      } else {
        await route.continue()
      }
    })

    await page.route(`**/api/v1/special-equipment/cart-items/${CART_ITEM_ID}`, async (route: Route) => {
      if (route.request().method() === 'PATCH') {
        const patchData = JSON.parse(route.request().postData() || '{}')
        if (patchData.allow_overstock !== undefined) {
          cartState.allow_overstock = patchData.allow_overstock
        }
        if (patchData.quantity !== undefined) {
          cartState.quantity = patchData.quantity
        }
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ cart_item: cartState }),
        })
      } else {
        await route.continue()
      }
    })
  })

  test('Б24 22250: cart card and summary use «Выгода» without changing amounts or adding price rows', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/cart', { waitUntil: 'networkidle' })

    const card = page.getByTestId(`cart-item-${CART_ITEM_ID}`)
    await expect(card.getByText('2025 | Белый', { exact: true })).toBeVisible()
    await expect(card.getByText('Выгода: −1 150 000 ₽ (29%)', { exact: true })).toBeVisible()
    await expect(card.getByText('Цена с выгодой: 2 881 000 ₽', { exact: true })).toBeVisible()

    // У спецтехники существовала только строка специальной цены: исходную не добавляем.
    await expect(card.getByText(/Цена в каталоге/)).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Выгода', exact: true })).toBeVisible()
    await expect(page.getByText('−2 300 000 ₽', { exact: true })).toBeVisible()
    await expect(page.getByText(oldPriceLabels)).toHaveCount(0)
  })

  test('Б24 22250: no benefit means no benefit block or extra price row', async ({ page }) => {
    cartState = {
      ...cartState,
      product: { ...mockProductCard, base_price: '2881000' },
    }
    await page.goto('/cart', { waitUntil: 'networkidle' })

    const card = page.getByTestId(`cart-item-${CART_ITEM_ID}`)
    await expect(card.getByText('2025 | Белый', { exact: true })).toBeVisible()
    await expect(card.getByText(/Выгода:|Цена с выгодой:|Цена в каталоге:/)).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Выгода', exact: true })).toHaveCount(0)
    await expect(page.getByText(oldPriceLabels)).toHaveCount(0)
  })

  test('Б24 22250: email form generates agreed text and HTML without sending external mail', async ({ page }) => {
    // Перехват обязателен: запрос никогда не передаётся реальному сервису рассылки.
    await page.route('**/api/v1/calculator/send-calculation-email', async (route: Route) => {
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
    })
    await page.goto('/cart', { waitUntil: 'networkidle' })
    await expect(page.getByTestId(`cart-item-${CART_ITEM_ID}`)).toBeVisible()
    await page.getByRole('button', { name: 'Отправить на почту', exact: true }).click()
    await page.getByPlaceholder('email@example.com', { exact: true }).fill('cart-22250@example.test')
    const emailRequest = page.waitForRequest(request =>
      new URL(request.url()).pathname === '/api/v1/calculator/send-calculation-email'
      && request.method() === 'POST',
    )
    await page.getByRole('button', { name: 'Отправить', exact: true }).click()
    const payload = (await emailRequest).postDataJSON()
    expect(payload.to).toBe('cart-22250@example.test')
    expect(payload.subject).toBe('Расчет лизинга — корзина')
    expect(typeof payload.text).toBe('string')
    expect(typeof payload.html).toBe('string')

    // DOMParser проверяет видимый текст HTML, а не строки шаблона или внутренние функции.
    const htmlText = await page.evaluate((html: string) =>
      new DOMParser().parseFromString(html, 'text/html').body.textContent || '', payload.html,
    )
    const textContent = normalizeText(payload.text)
    const htmlContent = normalizeText(htmlText)
    // TEXT сохраняет обе строки: discountLines и подробные характеристики.
    expect(textContent.match(/Цена с выгодой: 2 881 000(?=\s|$)/g)).toHaveLength(2)
    const [textSummary, textDetails] = payload.text.split('Подробные характеристики:')
    expect(normalizeText(textSummary).match(/Цена с выгодой: 2 881 000(?=\s|$)/g)).toHaveLength(1)
    expect(normalizeText(textDetails).match(/Цена с выгодой: 2 881 000(?=\s|$)/g)).toHaveLength(1)
    // В HTML details подпись и сумма находятся в соседних ячейках без двоеточия.
    expect(htmlContent.match(/Цена с выгодой: 2 881 000(?=\s|$)/g)).toHaveLength(1)
    expect(htmlContent.match(/Цена с выгодой 2 881 000(?=\s|$)/g)).toHaveLength(1)
    for (const content of [textContent, htmlContent]) {
      // Экспорты используют Intl ru-RU без валюты; ₽ остаётся только в UI.
      expect(content).toContain('Выгода: −1 150 000 (29%)')
      expect(content).toContain('Цена за 1 ТС: 2 881 000')
      expect(content).toContain('Количество: 2')
      expect(content).toContain('Стоимость имущества: 5 762 000')
      expect(content).toContain('Выгода: −2 300 000')
      expect(content).not.toContain('₽')
      expect(content).not.toContain('4 031 000')
      expect(content).not.toMatch(/Цена в каталоге|Исходная цена|Базовая цена|Цена без скидки/)
      expect(content).not.toMatch(oldPriceLabels)
    }
  })

  test('Б24 22250: downloaded PDF contains agreed benefit labels and unchanged amounts', async ({ page }, testInfo) => {
    // Нужен реальный парсер скачанного PDF, а не подмена pdfmake или проверка исходников.
    test.skip(Boolean(spawnSync('pdftotext', ['-v']).error), 'Для проверки текста скачанного PDF нужен доступный pdftotext (Poppler)')
    await page.goto('/cart', { waitUntil: 'networkidle' })
    await expect(page.getByTestId(`cart-item-${CART_ITEM_ID}`)).toBeVisible()
    const downloadEvent = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Скачать PDF', exact: true }).click()
    const download = await downloadEvent
    expect(await download.failure()).toBeNull()
    expect(download.suggestedFilename()).toMatch(/\.pdf$/i)
    const pdfPath = testInfo.outputPath('cart-22250.pdf')
    await download.saveAs(pdfPath)
    await testInfo.attach('cart-22250.pdf', { path: pdfPath, contentType: 'application/pdf' })
    const content = normalizeText(execFileSync('pdftotext', ['-layout', pdfPath, '-'], { encoding: 'utf8' }))
    // Проверяем существующие строки, не добавляя исходную цену list_price.
    expect(content).toContain('Выгода: −1 150 000 (29%)')
    expect(content).toContain('Цена за 1 ТС: 2 881 000')
    expect(content.match(/Цена с выгодой: 2 881 000(?=\s|$)/g)).toHaveLength(1)
    // PDF details сохраняет отдельную строку подписи и суммы без двоеточия.
    expect(content.match(/Цена с выгодой 2 881 000(?=\s|$)/g)).toHaveLength(1)
    expect(content).toContain('Количество: 2')
    expect(content).toContain('Стоимость имущества: 5 762 000')
    expect(content).toContain('Выгода: −2 300 000')
    expect(content).not.toContain('₽')
    expect(content).not.toContain('4 031 000')
    expect(content).not.toMatch(/Цена в каталоге|Исходная цена|Базовая цена|Цена без скидки/)
    expect(content).not.toMatch(oldPriceLabels)
  })

  test('toggles overstock, allows quantity up to 1000, shows warning hint, blocks purchase, and clamps on disable', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/cart', { waitUntil: 'networkidle' })

    // Initially overstock is off, shows button "Указать больше доступного"
    const toggleBtn = page.getByRole('button', { name: 'Указать больше доступного' })
    await expect(toggleBtn).toBeVisible()

    // Click toggle to enable overstock
    await toggleBtn.click()
    await expect(page.getByRole('button', { name: 'Ограничить наличием' })).toBeVisible()

    // Set quantity to 5 (available is 2, overstock is 3)
    const quantityInput = page.locator('input[type="number"]').first()
    await quantityInput.fill('5')
    await quantityInput.dispatchEvent('change')

    // Warning hint under quantity input should appear
    await expect(page.getByText(/Сверх наличия:\s*3\s*шт/)).toBeVisible()

    // Applied discounts still counts only billable quantity (2 * 1 150 000 = 2 300 000 ₽)
    await expect(page.getByText('−2 300 000 ₽')).toBeVisible()

    // Purchase button should be blocked with tooltip / disabled
    const buyButton = page.getByRole('button', { name: /Купить/ }).first()
    if (await buyButton.isVisible()) {
      await expect(buyButton).toBeDisabled()
      await expect(page.getByText('Для покупки ограничьте количество наличием или оформите лизинговую заявку.')).toBeVisible()
    }

    // Click "Ограничить наличием" to disable overstock
    const disableBtn = page.getByRole('button', { name: 'Ограничить наличием' })
    await disableBtn.click()

    // Quantity should be clamped back to available (2) and hint disappears
    await expect(page.getByRole('button', { name: 'Указать больше доступного' })).toBeVisible()
    await expect(page.getByText(/Сверх наличия/)).not.toBeVisible()
    await expect(quantityInput).toHaveValue('2')
  })

  test('guest cart stores allow_overstock in localStorage and clamps quantity up to 1000', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })

    // Unauthenticated state
    await page.route('**/api/v1/auth/**', async (route: Route) => {
      await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ error: 'unauthorized' }) })
    })

    // Set initial guest cart in localStorage
    await page.addInitScript(() => {
      localStorage.setItem('carcraft:special-equipment:cart:v2', JSON.stringify({
        version: 2,
        transfer_id: '44444444-0000-4000-8000-000000000099',
        updated_at: new Date().toISOString(),
        items: [{
          local_id: '44444444-0000-4000-8000-000000000002',
          product_id: '44444444-0000-4000-8000-000000000001',
          quantity: 4,
          allow_overstock: true,
          parent_local_id: null,
          is_selected: true,
          comment: '',
          equipments: [],
          services: [],
        }],
      }))
    })

    await page.goto('/cart', { waitUntil: 'networkidle' })

    // Overstock button should be "Ограничить наличием" because allow_overstock was true in localStorage
    await expect(page.getByRole('button', { name: 'Ограничить наличием' })).toBeVisible()
    await expect(page.getByText(/Сверх наличия:\s*2\s*шт/)).toBeVisible()
  })

  test('application details displays overstock banner for dealer/client but hides it for leasing company', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })

    const APPLICATION_ID = '44444444-0000-4000-8000-000000000055'
    const appState = {
      application: {
        id: APPLICATION_ID,
        number: '12345',
        status: 'new',
        total_amount: 5762000,
        items_count: 1,
        total_items_price: '5762000',
        items: [
          {
            id: '44444444-0000-4000-8000-000000000056',
            type: 'special_equipment',
            item_role: 'offer',
            title: 'FAW Jiefang J6P',
            quantity: 2,
            unit_price: '2881000',
            total_price: '5762000',
            overstock_requested_quantity: 3,
            status: 'active',
          },
        ],
      },
      link: { id: '44444444-0000-4000-8000-000000000057', status: 'submitted' },
      proposals: [],
      can_review: true,
    }

    await page.context().addCookies([{
      name: 'accessToken',
      value: 'e2e-dealer-test-token',
      domain: 'localhost',
      path: '/',
    }])

    // Role: dealer
    await page.route('**/api/v1/auth/**', async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ user: { id: '44444444-0000-4000-8000-000000000088', role: 'dealer' } }),
      })
    })

    await page.route(`**/api/v1/leasing/applications/${APPLICATION_ID}/response**`, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(appState),
      })
    })

    await page.goto(`/workspace/leasing-applications/${APPLICATION_ID}`, { waitUntil: 'networkidle' })

    // Dealer sees warning banner
    await expect(page.getByText('Клиент запросил сверх наличия: 3 шт. — не включено в заявку.')).toBeVisible()
  })
})

