import { expect, test, type APIRequestContext } from '@playwright/test'

test.use({
  baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1',
})

const authenticate = async (
  request: APIRequestContext,
  phone: string,
): Promise<void> => {
  const login = await request.post('/api/v1/auth/login', { data: { phone } })
  expect([200, 403]).toContain(login.status())
  const verification = await request.post('/api/v1/auth/verify-phone', {
    data: { phone, code: '0000' },
  })
  expect(verification.status()).toBe(200)
}

test.describe('Задача 21674 — Доработка раздела «Сотрудники», справочник должностей, мульти-компания', () => {
  test('21674.1. Справочник должностей: CRUD и ограничение прав', async ({ request }) => {
    // 1. carcraft_employee доступен справочник
    await authenticate(request, '+76660000001')

    // GET /api/v1/positions
    const listRes = await request.get('/api/v1/positions')
    expect(listRes.status()).toBe(200)
    const listBody = await listRes.json()
    expect(Array.isArray(listBody.items)).toBe(true)

    // Должны быть хотя бы дефолтные seed-должности: manager, supervisor
    const codes = listBody.items.map((p: any) => p.code)
    expect(codes).toContain('manager')
    expect(codes).toContain('supervisor')

    // POST /api/v1/positions
    const uniqueCode = `test_pos_${Date.now()}`
    const createRes = await request.post('/api/v1/positions', {
      data: {
        name: 'Тестовая должность E2E',
        code: uniqueCode,
        is_active: true,
      },
    })
    expect(createRes.status()).toBe(201)
    const created = await createRes.json()
    expect(created.name).toBe('Тестовая должность E2E')
    expect(created.code).toBe(uniqueCode)
    expect(created.is_active).toBe(true)

    const positionId = created.id

    // PUT /api/v1/positions/{id}
    const updateRes = await request.put(`/api/v1/positions/${positionId}`, {
      data: {
        name: 'Обновленная должность E2E',
        code: uniqueCode,
        is_active: true,
      },
    })
    expect(updateRes.status()).toBe(200)
    const updated = await updateRes.json()
    expect(updated.name).toBe('Обновленная должность E2E')

    // PATCH /api/v1/positions/{id}/deactivate
    const deactivateRes = await request.patch(`/api/v1/positions/${positionId}/deactivate`)
    expect(deactivateRes.status()).toBe(200)
    const deactivated = await deactivateRes.json()
    expect(deactivated.is_active).toBe(false)

    // 2. dealer (+76660000003) не имеет доступа к /api/v1/positions (403)
    await authenticate(request, '+76660000003')
    const forbiddenRes = await request.get('/api/v1/positions')
    expect(forbiddenRes.status()).toBe(403)
  })

  test('21674.2. API Сотрудников: список, создание, редактирование и деактивация', async ({ request }) => {
    // Авторизуемся как carcraft_employee
    await authenticate(request, '+76660000001')

    // 1. Получим список доступных компаний
    const meRes = await request.get('/api/v1/auth/me')
    expect(meRes.status()).toBe(200)
    const meBody = await meRes.json()
    expect(meBody.user).toBeDefined()

    // 2. GET /api/v1/employees
    const employeesRes = await request.get('/api/v1/employees')
    expect(employeesRes.status()).toBe(200)
    const employeesBody = await employeesRes.json()
    expect(Array.isArray(employeesBody.items)).toBe(true)
    expect(typeof employeesBody.total).toBe('number')

    if (employeesBody.items.length > 0) {
      const targetCompanyId = employeesBody.items[0].company_id
      const newPhone = `+7999${Math.floor(1000000 + Math.random() * 9000000)}`

      // 3. POST /api/v1/employees
      const createEmpRes = await request.post('/api/v1/employees', {
        data: {
          name: 'Иванов Иван Иванович E2E',
          phone: newPhone,
          company_id: targetCompanyId,
          role: 'client',
          can_view_applications: true,
          can_create_applications: true,
          is_active: true,
        },
      })
      expect(createEmpRes.status()).toBe(201)
      const createdEmp = await createEmpRes.json()
      expect(createdEmp.name).toBe('Иванов Иван Иванович E2E')
      expect(createdEmp.phone).toBe(newPhone)
      expect(createdEmp.role).toBe('client')

      const empUserId = createdEmp.user_id

      // 4. PUT /api/v1/employees/{user_id}/{company_id}
      const updateEmpRes = await request.put(`/api/v1/employees/${empUserId}/${targetCompanyId}`, {
        data: {
          name: 'Иванов Иван Петрович E2E',
          role: 'client',
          can_view_applications: false,
          can_create_applications: false,
          is_active: true,
        },
      })
      expect(updateEmpRes.status()).toBe(200)
      const updatedEmp = await updateEmpRes.json()
      expect(updatedEmp.name).toBe('Иванов Иван Петрович E2E')
      expect(updatedEmp.can_view_applications).toBe(false)

      // 5. PATCH /api/v1/employees/{user_id}/{company_id}/deactivate
      const deactEmpRes = await request.patch(`/api/v1/employees/${empUserId}/${targetCompanyId}/deactivate`)
      expect(deactEmpRes.status()).toBe(200)

      // Проверяем, что в списке сотрудник стал неактивен
      const verifyRes = await request.get(`/api/v1/employees?phone=${newPhone}`)
      expect(verifyRes.status()).toBe(200)
      const verifyBody = await verifyRes.json()
      expect(verifyBody.items.length).toBeGreaterThan(0)
      expect(verifyBody.items[0].is_active).toBe(false)
    }
  })

  test('21674.3. Обогащение /auth/me и переключатель компании', async ({ request }) => {
    // Вход под пользователем
    await authenticate(request, '+76660000003')

    const meRes = await request.get('/api/v1/auth/me')
    expect(meRes.status()).toBe(200)
    const meData = await meRes.json()
    const user = meData.user

    // Проверяем новые поля контракта
    expect(user).toHaveProperty('active_role')
    expect(user).toHaveProperty('active_company_id')
    expect(user).toHaveProperty('available_companies')
    expect(Array.isArray(user.available_companies)).toBe(true)

    // Если доступно несколько компаний, тестируем переключение
    if (user.available_companies.length > 1) {
      const targetCompany = user.available_companies.find(
        (c: any) => c.id !== user.active_company_id,
      )
      if (targetCompany) {
        const switchRes = await request.put('/api/v1/users/me/company-select-history', {
          data: { company_id: targetCompany.id },
        })
        expect(switchRes.status()).toBe(200)

        // Проверяем, что /auth/me обновился
        const updatedMeRes = await request.get('/api/v1/auth/me')
        const updatedMeData = await updatedMeRes.json()
        expect(updatedMeData.user.active_company_id).toBe(targetCompany.id)
      }
    }
  })

  test('21674.4. UI: вкладки на странице /workspace/employees', async ({ page }) => {
    // 1. Проверяем carcraft_employee: видит вкладку «Справочник должностей»
    await authenticate(page.request, '+76660000001')
    await page.goto('/workspace/employees', { waitUntil: 'networkidle' })

    const positionsTabBtn = page.getByRole('button', { name: 'Справочник должностей' })
    await expect(positionsTabBtn).toBeVisible()

    const employeesTabBtn = page.getByRole('button', { name: 'Сотрудники компании' })
    await expect(employeesTabBtn).toBeVisible()

    // Переключаемся на «Справочник должностей»
    await positionsTabBtn.click()
    await expect(page.getByRole('button', { name: 'Создать должность' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Справочник должностей' })).toBeVisible()

    // 2. Проверяем dealer: НЕ видит вкладку «Справочник должностей»
    await authenticate(page.request, '+76660000003')
    await page.goto('/workspace/employees', { waitUntil: 'networkidle' })

    await expect(page.getByRole('button', { name: 'Справочник должностей' })).toHaveCount(0)
    await expect(page.getByRole('heading', { name: 'Сотрудники компании' })).toBeVisible()
  })
})
