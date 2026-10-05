import { expect, test, type APIRequestContext } from '@playwright/test'

test.use({
  baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3002',
  actionTimeout: 60_000,
})

const authenticate = async (
  request: APIRequestContext,
  phone: string,
): Promise<any> => {
  const login = await request.post('/api/v1/auth/login', {
    data: { phone },
    timeout: 60_000,
  })
  expect([200, 403]).toContain(login.status())
  const verification = await request.post('/api/v1/auth/verify-phone', {
    data: { phone, code: '0000' },
    timeout: 60_000,
  })
  expect(verification.status()).toBe(200)
  const body = await verification.json()
  return body.user
}

test.describe('Задача 21952 — Персональные права доступа сотрудников дилеров и дистрибьюторов', () => {
  test.setTimeout(240_000)

  test('Сквозной сценарий: additional_phone, права доступа к объектам и разделам, монетизация и делегирование', async ({
    request,
  }) => {
    // 1. Авторизация под carcraft_employee (администратор)
    const adminUser = await authenticate(request, '+76660000001')
    expect(adminUser).toBeDefined()

    // 2. Получение списка сотрудников для определения компании
    const empRes = await request.get('/api/v1/employees', { timeout: 60_000 })
    expect(empRes.status()).toBe(200)
    const empBody = await empRes.json()
    expect(Array.isArray(empBody.items)).toBe(true)
    const targetItem = empBody.items.find((i: any) => i.role === 'dealer' || i.role === 'distributor') || empBody.items[0]
    const targetCompanyId = targetItem.company_id
    const targetRole = targetItem.role && targetItem.role !== 'client' ? targetItem.role : 'distributor'

    // 3. Создание нового сотрудника с additional_phone (префикс +7666 для тестового OTP-кода 0000)
    const randomDigits = Math.floor(1000000 + Math.random() * 9000000).toString()
    const employeePhone = `+7666${randomDigits}`
    const initialAdditionalPhone = '+79991112233'
    const updatedAdditionalPhone = '+79998887766'

    const createRes = await request.post('/api/v1/employees', {
      data: {
        name: `Сотрудник E2E 21952 ${randomDigits}`,
        phone: employeePhone,
        additional_phone: initialAdditionalPhone,
        company_id: targetCompanyId,
        role: targetRole,
        can_view_applications: true,
        can_create_applications: true,
        is_active: true,
      },
      timeout: 60_000,
    })
    expect(createRes.status()).toBe(201)
    const created = await createRes.json()
    expect(created.phone).toBe(employeePhone)
    expect(created.additional_phone).toBe(initialAdditionalPhone)
    const testUserId = created.user_id

    // 4. Редактирование сотрудника — обновление additional_phone
    const updateRes = await request.put(`/api/v1/employees/${testUserId}/${targetCompanyId}`, {
      data: {
        name: `Сотрудник E2E 21952 ${randomDigits} Обновленный`,
        role: targetRole,
        additional_phone: updatedAdditionalPhone,
        can_view_applications: true,
        can_create_applications: true,
        is_active: true,
      },
      timeout: 60_000,
    })
    expect(updateRes.status()).toBe(200)
    const updated = await updateRes.json()
    expect(updated.additional_phone).toBe(updatedAdditionalPhone)

    // 5. Получение прав сотрудника по умолчанию (GET access-settings)
    const getRes = await request.get(`/api/v1/employees/${testUserId}/${targetCompanyId}/access-settings`, {
      timeout: 60_000,
    })
    expect(getRes.status()).toBe(200)
    const settings = await getRes.json()
    expect(settings.can_create_employees).toBe(false)
    expect(Array.isArray(settings.access_rules)).toBe(true)
    expect(typeof settings.sections).toBe('object')
    // По умолчанию все 9 разделов разрешены
    expect(settings.sections.applications).toBe(true)
    expect(settings.sections.warehouses).toBe(true)

    // 6. Сохранение персональных прав: can_create_employees=true, ограничение разделов и объектов
    const putRes = await request.put(`/api/v1/employees/${testUserId}/${targetCompanyId}/access-settings`, {
      data: {
        can_create_employees: true,
        rules: [
          { object_type: 'warehouse', access_mode: 'all' },
          { object_type: 'brand', access_mode: 'none' },
          { object_type: 'dealer', access_mode: 'all' },
          { object_type: 'dealer_warehouse', access_mode: 'all' },
          { object_type: 'application_creator', access_mode: 'all' },
        ],
        sections: {
          applications: true,
          warehouses: false,
          vehicle_exchange: true,
          employees: true,
          catalog_management: true,
          analytics: true,
          monetization_income: true,
          monetization_expense: false,
          incentive_programs: true,
        },
      },
      timeout: 60_000,
    })
    expect(putRes.status()).toBe(200)
    const saved = await putRes.json()
    expect(saved.can_create_employees).toBe(true)
    expect(saved.sections.warehouses).toBe(false)
    expect(saved.sections.monetization_expense).toBe(false)
    expect(saved.sections.monetization_income).toBe(true)

    // 7. Авторизация под созданным сотрудником
    const empUser = await authenticate(request, employeePhone)
    expect(empUser).toBeDefined()
    expect(empUser.can_create_employees).toBe(true)

    // 8. Проверка видимости разделов сотрудника
    const visRes = await request.get('/api/v1/workspace/section-visibility', { timeout: 60_000 })
    expect(visRes.status()).toBe(200)
    const visData = await visRes.json()
    expect(Array.isArray(visData.sections)).toBe(true)
    const secMap = Object.fromEntries(visData.sections.map((s: any) => [s.key, s.is_visible]))
    if (secMap.warehouses !== undefined) {
      expect(secMap.warehouses).toBe(false)
    }
    if (secMap.inventory !== undefined) {
      expect(secMap.inventory).toBe(false)
    }
    expect(secMap.monetization).toBe(true)

    // 9. Проверка монетизации с monetization_income: true, monetization_expense: false
    const monetRes = await request.get('/api/v1/admin/monetization/programs', { timeout: 60_000 })
    expect(monetRes.status()).toBe(200)
    const monetData = await monetRes.json()
    expect(Array.isArray(monetData.items)).toBe(true)

    // 10. Отзыв права can_create_employees и запрет monetization_income администратором
    await authenticate(request, '+76660000001')
    await request.put(`/api/v1/employees/${testUserId}/${targetCompanyId}/access-settings`, {
      data: {
        can_create_employees: false,
        rules: [],
        sections: {
          applications: true,
          warehouses: false,
          vehicle_exchange: true,
          employees: true,
          catalog_management: true,
          analytics: true,
          monetization_income: false,
          monetization_expense: false,
          incentive_programs: true,
        },
      },
      timeout: 60_000,
    })

    // 11. Проверка отзыва прав под сотрудником
    await authenticate(request, employeePhone)

    const visRes2 = await request.get('/api/v1/workspace/section-visibility', { timeout: 60_000 })
    expect(visRes2.status()).toBe(200)
    const visData2 = await visRes2.json()
    const secMap2 = Object.fromEntries(visData2.sections.map((s: any) => [s.key, s.is_visible]))
    expect(secMap2.monetization).toBe(false)

    // При обоих запрещенных направлениях монетизации — 403 Forbidden
    const forbiddenMonet = await request.get('/api/v1/admin/monetization/programs', { timeout: 60_000 })
    expect(forbiddenMonet.status()).toBe(403)

    // При can_create_employees=false — запрет создания сотрудников (403 Forbidden)
    const illegalPhone = `+7998${Math.floor(1000000 + Math.random() * 9000000).toString()}`
    const illegalCreate = await request.post('/api/v1/employees', {
      data: {
        name: 'Недопустимый Сотрудник',
        phone: illegalPhone,
        company_id: targetCompanyId,
        role: targetRole,
        can_view_applications: true,
        can_create_applications: true,
        is_active: true,
      },
      timeout: 60_000,
    })
    expect(illegalCreate.status()).toBe(403)
  })
})
