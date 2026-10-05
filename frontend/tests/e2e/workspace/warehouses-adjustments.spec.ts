import {
  expect,
  test,
  type APIRequestContext,
  type APIResponse,
  type Page,
} from '@playwright/test'

import {
  getE2EFixtureManifest,
  requireStorageStatePath,
  resetE2EFixture,
  type JsonRecord,
} from '../special-equipment/support/fixtures'
import { appUrl } from '../special-equipment/support/runtime'

const record = (value: unknown, label: string): JsonRecord => {
  expect(value, `${label} must be an object`).toBeTruthy()
  expect(Array.isArray(value), `${label} must not be an array`).toBe(false)
  expect(typeof value, `${label} must be an object`).toBe('object')
  return value as JsonRecord
}

const records = (value: unknown, label: string): JsonRecord[] => {
  expect(Array.isArray(value), `${label} must be an array`).toBe(true)
  return (value as unknown[]).map((item, index) => record(item, `${label}[${index}]`))
}

const responseJson = async (
  response: APIResponse,
  expectedStatus: number,
): Promise<JsonRecord> => {
  const body = await response.text()
  expect(
    response.status(),
    `${response.url()} returned ${response.status()}: ${body}`,
  ).toBe(expectedStatus)
  return record(JSON.parse(body), `${response.url()} response`)
}

test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })

test.beforeEach(async ({}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'warehouses-adjustments проверяется только в desktop browser',
  )
  await resetE2EFixture()
})

test.describe('warehouses-adjustments — проверка интерфейса и API складов', () => {
  test('employee видит обновленные термины ТС, колонку владельца и модальные окна', async ({
    page,
    request: employee,
  }) => {
    requireStorageStatePath('employee')

    // 1. Проверка API правил доступа: наличие полей владельца
    const rulesResp = await responseJson(
      await employee.get('/api/v1/warehouses/access-rules', {
        params: { page: '1', limit: '10' },
      }),
      200,
    )
    const rules = records(rulesResp.rules, 'access rules')
    if (rules.length > 0) {
      const firstRule = rules[0]
      expect(firstRule).toHaveProperty('owner_company_id')
      expect(firstRule).toHaveProperty('owner_company_name')
      expect(firstRule).toHaveProperty('warehouse_brand_names')
    }

    // 2. Проверка UI: переход на страницу складов
    await page.goto(appUrl('/workspace/warehouses'), { waitUntil: 'domcontentloaded' })
    await expect(page.getByRole('heading', { name: 'Склады и управление доступом' })).toBeVisible()
    await expect(page.getByText('Справочник складов ТС и правила доступа дилеров')).toBeVisible()

    // 3. Кнопка перемещения ТС
    const transferBtn = page.getByRole('button', { name: 'Перемещение ТС' })
    await expect(transferBtn).toBeVisible()
    await transferBtn.click()

    // 4. Модальное окно перемещения ТС
    await expect(page.getByRole('heading', { name: 'Перемещение ТС' })).toBeVisible()
    await expect(page.getByText('Выберите исходный склад, целевой склад и ТС')).toBeVisible()
    await page.getByRole('button', { name: '✕' }).or(page.getByRole('button', { name: 'Отмена' })).first().click()

    // 5. Модальное окно создания склада (проверка полей марки, категории и поиска владельца/города)
    const createWarehouseBtn = page.getByRole('button', { name: 'Создать склад' })
    await expect(createWarehouseBtn).toBeVisible()
    await createWarehouseBtn.click()

    await expect(page.getByRole('heading', { name: 'Создать склад' })).toBeVisible()
    await expect(page.getByText('Марка спецтехники')).toHaveCount(0)
    await expect(page.getByText('Марки ТС', { exact: true })).toBeVisible()
    await expect(page.getByText('Категория ТС', { exact: true })).toBeVisible()
    await expect(page.getByText('Компания-владелец')).toBeVisible()
    await expect(page.getByText('Город')).toBeVisible()
    await expect(page.getByRole('button', { name: '+ Новый' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Отмена' })).toBeVisible()
    await page.getByRole('button', { name: 'Отмена' }).click()

    // 5.1. Проверка кнопки «Удалить склад» и модального окна каскадного удаления
    const deleteBtn = page.getByRole('button', { name: 'Удалить склад' }).first()
    if (await deleteBtn.isVisible()) {
      await deleteBtn.click()
      await expect(page.getByRole('heading', { name: 'Удалить склад и связанные данные?' })).toBeVisible()
      await expect(page.getByText('Будут удалены склад и все его объявления')).toBeVisible()
      await expect(page.getByText('Удаляемые объекты каталога')).toBeVisible()
      await page.getByRole('button', { name: 'Отмена' }).click()
      await expect(page.getByRole('heading', { name: 'Удалить склад и связанные данные?' })).toHaveCount(0)
    }

    // 6. Переход на вкладку «Управление складами»
    const managementTab = page.getByRole('button', { name: 'Управление складами' })
    await expect(managementTab).toBeVisible()
    await managementTab.click()

    // Первая колонка таблицы должна быть «Владелец склада»
    const ownerHeader = page.getByRole('columnheader', { name: 'Владелец склада' })
    await expect(ownerHeader).toBeVisible()

    // Текст «Базовое» не должен отображаться в колонке действий
    await expect(page.getByText('Базовое', { exact: true })).toHaveCount(0)

    // 7. Проверка модального окна создания правила доступа
    const createRuleBtn = page.getByRole('button', { name: 'Создать правило' })
    await expect(createRuleBtn).toBeVisible()
    await createRuleBtn.click()

    await expect(page.getByRole('heading', { name: 'Предоставить доступ к складу' })).toBeVisible()
    await expect(page.getByText('Владелец склада')).toBeVisible()
    await expect(page.getByText('Марка ТС')).toBeVisible()
    await expect(page.getByText('В – разрешена работа с заявками')).toBeVisible()
    await expect(page.getByText('С – работа с заявками недоступна')).toBeVisible()
    await page.getByRole('button', { name: 'Отмена' }).click()
  })

  test('API каскадного удаления: delete-preview, валидация УДАЛИТЬ, stale token и успешное удаление', async ({
    request: employee,
  }) => {
    requireStorageStatePath('employee')
    const manifest = getE2EFixtureManifest()
    const companies = record(manifest.companies, 'manifest.companies')
    const seller = record(companies.seller, 'seller company')

    // 1. Создаем тестовый склад для проверки каскада
    const createResp = await responseJson(
      await employee.post('/api/v1/admin/warehouses', {
        data: {
          name: `E2E Каскадный Склад ${Date.now()}`,
          owner_company_id: seller.id,
          address: 'г. Москва, ул. Тестовая, 100',
          is_active: true,
        },
      }),
      201,
    )
    const createdWh = record(createResp.warehouse, 'created warehouse')
    const whId = createdWh.id as string
    expect(whId).toBeTruthy()

    // 2. Запрос delete-preview (проверка через оба пути: /api/v1/admin/warehouses/... и /api/v1/warehouses/...)
    const previewResp = await responseJson(
      await employee.get(`/api/v1/admin/warehouses/${whId}/delete-preview`),
      200,
    )
    expect(previewResp).toHaveProperty('warehouse')
    expect(previewResp).toHaveProperty('counts')
    expect(previewResp).toHaveProperty('retained')
    expect(previewResp).toHaveProperty('blockers')
    expect(previewResp).toHaveProperty('can_delete')
    expect(previewResp).toHaveProperty('preview_token')
    expect(previewResp).toHaveProperty('catalog_revision')

    const counts = record(previewResp.counts, 'preview counts')
    expect(counts).toHaveProperty('products')
    expect(counts).toHaveProperty('marks')
    expect(counts).toHaveProperty('models')
    expect(counts).toHaveProperty('modifications')
    expect(counts).toHaveProperty('attributes')
    expect(counts).toHaveProperty('attribute_groups')
    expect(counts).toHaveProperty('trims')
    expect(counts).toHaveProperty('attribute_values')
    expect(counts).toHaveProperty('options')
    expect(counts).toHaveProperty('images')
    expect(counts).toHaveProperty('cart_items')
    expect(counts).toHaveProperty('favorites')
    expect(counts).toHaveProperty('access_rules')
    expect(counts).toHaveProperty('storefront_bindings')

    expect(previewResp.can_delete).toBe(true)
    const previewToken = previewResp.preview_token as string
    expect(typeof previewToken).toBe('string')
    expect(previewToken.length).toBeGreaterThan(0)

    // Проверка альтернативного пути без /admin
    const altPreview = await responseJson(
      await employee.get(`/api/v1/warehouses/${whId}/delete-preview`),
      200,
    )
    expect(altPreview.preview_token).toBe(previewToken)

    // 3. Попытка удаления с неверным подтверждением (не УДАЛИТЬ) -> 422
    const invalidConfirmResp = await employee.post(`/api/v1/admin/warehouses/${whId}/cascade-delete`, {
      data: {
        confirmation: 'DELETE',
        preview_token: previewToken,
      },
    })
    expect(invalidConfirmResp.status()).toBe(422)

    // 4. Попытка удаления с устаревшим токеном -> 409
    const staleTokenResp = await employee.post(`/api/v1/admin/warehouses/${whId}/cascade-delete`, {
      data: {
        confirmation: 'УДАЛИТЬ',
        preview_token: 'stale_or_invalid_token_12345',
      },
    })
    expect(staleTokenResp.status()).toBe(409)

    // 5. Успешное каскадное удаление
    const deleteResp = await responseJson(
      await employee.post(`/api/v1/admin/warehouses/${whId}/cascade-delete`, {
        data: {
          confirmation: 'УДАЛИТЬ',
          preview_token: previewToken,
        },
      }),
      200,
    )
    expect(deleteResp.warehouse_id).toBe(whId)
    expect(deleteResp).toHaveProperty('deleted')
    expect(deleteResp).toHaveProperty('retained')
    expect(deleteResp).toHaveProperty('catalog_revision')

    // 6. Проверка, что склад действительно удален (404)
    const getAfterDelete = await employee.get(`/api/v1/admin/warehouses/${whId}`)
    expect(getAfterDelete.status()).toBe(404)

    // 7. Повторное удаление уже удаленного склада -> 404
    const repeatDelete = await employee.post(`/api/v1/admin/warehouses/${whId}/cascade-delete`, {
      data: {
        confirmation: 'УДАЛИТЬ',
        preview_token: previewToken,
      },
    })
    expect(repeatDelete.status()).toBe(404)
  })

  test('создание группы дилеров отклоняет дилера не из дилерской сети дистрибьютора', async ({
    request: employee,
  }) => {
    requireStorageStatePath('employee')
    const manifest = getE2EFixtureManifest()
    const companies = record(manifest.companies, 'manifest.companies')
    const seller = record(companies.seller, 'seller company')
    const alternate = record(companies.alternate, 'alternate company')

    // Попытка создать группу с произвольной компанией, не привязанной в сети
    const response = await employee.post('/api/v1/dealer-groups', {
      data: {
        name: `Test Group ${Date.now()}`,
        distributor_company_id: seller.id,
        dealer_company_ids: [alternate.id],
      },
    })
    // Должна вернуть ошибку 400 из-за валидации дилерской сети
    expect(response.status()).toBe(400)
    const body = await response.json()
    expect(body.message || body.detail || body.error).toContain('дилерскую сеть')
  })
})

