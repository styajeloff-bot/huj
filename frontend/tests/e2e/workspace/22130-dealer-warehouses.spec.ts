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

interface WarehouseFixture {
  id: string
  address: string
}

interface VehicleFixture {
  id: string
  vin: string
  markName: string
  modelName: string
  year: string
  color: string
}

const record = (value: unknown, label: string): JsonRecord => {
  expect(value, `${label} must be an object`).toBeTruthy()
  expect(Array.isArray(value), `${label} must not be an array`).toBe(false)
  expect(typeof value, `${label} must be an object`).toBe('object')
  return value as JsonRecord
}

const string = (value: unknown, label: string): string => {
  expect(typeof value, `${label} must be a string`).toBe('string')
  expect(String(value).trim(), `${label} must not be empty`).not.toBe('')
  return String(value)
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

const expectStatus = async (
  response: APIResponse,
  expectedStatus: number,
): Promise<void> => {
  const body = await response.text()
  expect(
    response.status(),
    `${response.url()} returned ${response.status()}: ${body}`,
  ).toBe(expectedStatus)
}

const createWarehouse = async (
  employee: APIRequestContext,
  payload: { address: string; brand: string; company_id: string },
): Promise<WarehouseFixture> => {
  const response = await responseJson(await employee.post('/api/v1/admin/warehouses', {
    data: payload,
  }), 201)
  const warehouse = record(response.warehouse, 'created warehouse')
  return {
    id: string(warehouse.id, 'created warehouse.id'),
    address: string(warehouse.address, 'created warehouse.address'),
  }
}

const findVehicleWarehouse = async (
  employee: APIRequestContext,
  vehicleId: string,
): Promise<{ warehouseId: string; vehicle: VehicleFixture }> => {
  const response = await responseJson(await employee.get('/api/v1/admin/warehouses', {
    params: { page: '1', limit: '200', status: 'active' },
  }), 200)
  const warehouses = records(response.warehouses, 'warehouse list')
    .filter(warehouse => (
      typeof warehouse.vehicles_count === 'number'
      && warehouse.vehicles_count > 0
    ))

  for (const warehouse of warehouses) {
    const warehouseId = string(warehouse.id, 'warehouse.id')
    const vehiclesResponse = await responseJson(await employee.get(
      `/api/v1/admin/warehouses/${warehouseId}/vehicles`,
      { params: { page: '1', limit: '200' } },
    ), 200)
    const vehicle = records(vehiclesResponse.vehicles, 'warehouse vehicles')
      .find(item => item.id === vehicleId)
    if (!vehicle) continue
    return {
      warehouseId,
      vehicle: {
        id: vehicleId,
        vin: string(vehicle.vin, 'vehicle.vin'),
        markName: string(vehicle.mark_name, 'vehicle.mark_name'),
        modelName: string(vehicle.model_name, 'vehicle.model_name'),
        year: String(vehicle.year ?? ''),
        color: String(vehicle.color ?? '-'),
      },
    }
  }
  throw new Error(`Fixture vehicle ${vehicleId} is not bound to an active warehouse`)
}

const authenticateDealer = async (
  dealer: APIRequestContext,
  phone: string,
): Promise<void> => {
  const login = await dealer.post('/api/v1/auth/login', { data: { phone } })
  expect(
    [200, 403],
    `dealer login returned ${login.status()}: ${await login.text()}`,
  ).toContain(login.status())

  const verification = await responseJson(await dealer.post('/api/v1/auth/verify-phone', {
    data: { phone, code: '0000' },
  }), 200)
  expect(verification.mfaRequired).not.toBe(true)
  expect(verification.mfaSetupRequired).not.toBe(true)
  const user = record(verification.user, 'dealer verification user')
  expect(user.role).toBe('dealer')
}

const assertDealerApiScope = async (
  dealer: APIRequestContext,
  target: WarehouseFixture,
  foreign: WarehouseFixture,
  vehicleId: string,
): Promise<void> => {
  const listing = await responseJson(await dealer.get('/api/v1/admin/warehouses', {
    params: { page: '1', limit: '200' },
  }), 200)
  const visibleIds = records(listing.warehouses, 'dealer warehouse list')
    .map(warehouse => string(warehouse.id, 'dealer warehouse.id'))
  expect(visibleIds).toContain(target.id)
  expect(visibleIds).not.toContain(foreign.id)

  const vehicles = await responseJson(await dealer.get(
    `/api/v1/admin/warehouses/${target.id}/vehicles`,
    { params: { page: '1', limit: '200' } },
  ), 200)
  expect(records(vehicles.vehicles, 'dealer warehouse vehicles').map(item => item.id))
    .toContain(vehicleId)

  await expectStatus(
    await dealer.get(`/api/v1/admin/warehouses/${foreign.id}`),
    404,
  )
  await expectStatus(
    await dealer.get(`/api/v1/admin/warehouses/${foreign.id}/vehicles`),
    404,
  )
}

const assertReadOnlyWarehouseUi = async (
  page: Page,
  target: WarehouseFixture,
  foreign: WarehouseFixture,
  vehicle: VehicleFixture,
): Promise<void> => {
  await page.goto(appUrl('/workspace/profile'), { waitUntil: 'domcontentloaded' })

  await expect(page.getByRole('heading', { name: 'Профиль дилера' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Основная информация' })).toBeVisible()
  await expect(page.getByText('Статистика деятельности', { exact: true })).toHaveCount(0)

  const workspaceNavigation = page.getByRole('navigation', {
    name: 'Навигация рабочего кабинета',
  })
  const warehousesLink = workspaceNavigation.getByRole('link', {
    name: 'Склады',
    exact: true,
  })
  await expect(warehousesLink).toHaveAttribute('href', '/workspace/warehouses')
  await warehousesLink.click()

  await expect(page).toHaveURL(/\/workspace\/warehouses$/)
  await expect(page.getByRole('heading', { name: 'Склады', level: 2 })).toBeVisible()

  const targetRow = page.getByRole('row').filter({ hasText: target.address })
  await expect(targetRow).toHaveCount(1)
  await expect(targetRow).toContainText(vehicle.markName)
  await expect(targetRow).toContainText('1')
  await expect(page.getByText(foreign.address, { exact: true })).toHaveCount(0)

  for (const managementControl of [
    'Создать склад',
    'Перемещение ТС',
    'Загрузить склады (CSV)',
    'Загрузить ТС (CSV)',
  ]) {
    await expect(page.getByText(managementControl, { exact: true })).toHaveCount(0)
  }
  for (const managementAction of ['Редактировать', 'Удалить', 'Привязать машины']) {
    await expect(page.getByRole('button', { name: managementAction })).toHaveCount(0)
  }

  await targetRow.getByRole('button', { name: 'Посмотреть ТС' }).click()
  await expect(page.getByRole('heading', { name: 'Машины на складе', level: 3 })).toBeVisible()

  const vehicleRow = page.getByRole('row').filter({ hasText: vehicle.vin })
  await expect(vehicleRow).toHaveCount(1)
  await expect(vehicleRow).toContainText(vehicle.markName)
  await expect(vehicleRow).toContainText(vehicle.modelName)
  await expect(vehicleRow).toContainText(vehicle.year)
  await expect(vehicleRow).toContainText(vehicle.color)
  await expect(page.getByText('Добавить машины', { exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Отвязать' })).toHaveCount(0)
}

test.use({ storageState: process.env.E2E_EMPLOYEE_STORAGE_STATE })

test.beforeEach(async ({}, testInfo) => {
  test.skip(
    testInfo.project.name !== 'desktop-chromium',
    'Bitrix 22130 проверяется только в desktop browser',
  )
  await resetE2EFixture()
})

test.describe('Bitrix 22130 — склады и профиль дилера', () => {
  test('employee готовит два склада и ТС, dealer видит только свой склад без управления', async ({
    page,
    playwright,
    request: employee,
  }) => {
    requireStorageStatePath('employee')
    const apiBaseUrl = process.env.E2E_BASE_URL
    expect(apiBaseUrl, 'E2E_BASE_URL is required').toBeTruthy()

    const manifest = getE2EFixtureManifest()
    const auth = record(manifest.auth, 'manifest.auth')
    const clientActor = record(auth.client, 'manifest.auth.client')
    const clientId = string(clientActor.id, 'manifest.auth.client.id')
    const clientPhone = string(clientActor.phone, 'manifest.auth.client.phone')
    const companies = record(manifest.companies, 'manifest.companies')
    const ownCompany = record(companies.seller, 'manifest.companies.seller')
    const foreignCompany = record(companies.alternate, 'manifest.companies.alternate')
    const ownCompanyId = string(ownCompany.id, 'manifest.companies.seller.id')
    const foreignCompanyId = string(foreignCompany.id, 'manifest.companies.alternate.id')
    const modelShowcase = record(manifest.model_showcase, 'manifest.model_showcase')
    const showcaseVehicles = record(modelShowcase.vehicles, 'manifest.model_showcase.vehicles')
    const sourceVehicleId = string(
      record(showcaseVehicles.alpha, 'manifest.model_showcase.vehicles.alpha').id,
      'manifest.model_showcase.vehicles.alpha.id',
    )

    let targetWarehouse: WarehouseFixture | null = null
    let foreignWarehouse: WarehouseFixture | null = null
    let dealer: APIRequestContext | null = null

    try {
      for (const [label, companyId] of [
        ['own dealer company', ownCompanyId],
        ['foreign dealer company', foreignCompanyId],
      ] as const) {
        const companyResponse = await responseJson(
          await employee.get(`/api/v1/companies/${companyId}`),
          200,
        )
        expect(companyResponse.company_type, `${label} must be a dealer`).toBe('dealer')
      }

      const clientResponse = await responseJson(
        await employee.get(`/api/v1/users/${clientId}`),
        200,
      )
      expect(record(clientResponse.user, 'fixture client').role).toBe('client')
      await responseJson(await employee.patch(`/api/v1/users/${clientId}`, {
        data: { role: 'dealer', company_id: ownCompanyId },
      }), 200)

      const source = await findVehicleWarehouse(employee, sourceVehicleId)
      const suffix = manifest.prefix.replace(/[^A-Za-z0-9_-]/g, '-').slice(-40)
      targetWarehouse = await createWarehouse(employee, {
        address: `${suffix} склад дилера 22130`,
        brand: source.vehicle.markName,
        company_id: ownCompanyId,
      })
      foreignWarehouse = await createWarehouse(employee, {
        address: `${suffix} чужой склад 22130`,
        brand: source.vehicle.markName,
        company_id: foreignCompanyId,
      })

      await responseJson(await employee.delete(
        `/api/v1/admin/warehouses/${source.warehouseId}/vehicles/${source.vehicle.id}`,
      ), 200)
      await responseJson(await employee.post(
        `/api/v1/admin/warehouses/${targetWarehouse.id}/vehicles`,
        { data: { vehicle_id: source.vehicle.id } },
      ), 201)

      dealer = await playwright.request.newContext({ baseURL: apiBaseUrl! })
      await authenticateDealer(dealer, clientPhone)
      await assertDealerApiScope(
        dealer,
        targetWarehouse,
        foreignWarehouse,
        source.vehicle.id,
      )

      const dealerState = await dealer.storageState()
      expect(dealerState.cookies.some(cookie => cookie.name === 'accessToken')).toBe(true)
      await page.context().clearCookies()
      await page.context().addCookies(dealerState.cookies)
      await assertReadOnlyWarehouseUi(
        page,
        targetWarehouse,
        foreignWarehouse,
        source.vehicle,
      )
    } finally {
      await page.context().clearCookies()
      await resetE2EFixture()
      for (const warehouse of [targetWarehouse, foreignWarehouse]) {
        if (!warehouse) continue
        const deletion = await employee.delete(`/api/v1/admin/warehouses/${warehouse.id}`)
        expect(
          [204, 404],
          `cleanup warehouse ${warehouse.id} returned ${deletion.status()}: ${await deletion.text()}`,
        ).toContain(deletion.status())
      }
      await dealer?.dispose()
    }
  })
})
