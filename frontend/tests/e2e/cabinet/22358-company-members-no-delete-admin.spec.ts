import fs from 'node:fs'
import { expect, test } from '@playwright/test'

const isDocker = fs.existsSync('/.dockerenv')
const defaultBaseUrl = isDocker ? 'http://nginx' : 'http://127.0.0.1'

test.use({
  baseURL: process.env.E2E_BASE_URL ?? defaultBaseUrl,
})

test.describe('Панель сотрудников компании в ЛК', () => {
  const COMPANY_ID = '22222222-2222-4222-8222-222222222222'
  const ADMIN_ID = '33333333-3333-4333-8333-333333333333'
  const EMPLOYEE_ID = '44444444-4444-4444-8444-444444444444'

  test('Администратор компании может управлять сотрудниками и видит кнопки удаления участников кроме себя', async ({
    page,
  }) => {
    const fulfill = (route: any, json: unknown, status = 200) =>
      route.fulfill({
        status,
        json,
        headers: {
          'access-control-allow-origin': route.request().headers().origin || '*',
          'access-control-allow-credentials': 'true',
        },
      })

    await page.route(
      (url: URL) => url.pathname.startsWith('/api/'),
      async (route: any) => {
        const req = route.request()
        const url = new URL(req.url())
        const path = url.pathname.replace(/\/$/, '')
        const method = req.method()

        if (method === 'OPTIONS') {
          return route.fulfill({
            status: 204,
            headers: {
              'access-control-allow-origin': req.headers().origin || '*',
              'access-control-allow-credentials': 'true',
              'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
              'access-control-allow-headers': '*',
            },
          })
        }

        if (path === '/api/v1/auth/me') {
          return fulfill(route, {
            user: {
              id: ADMIN_ID,
              phone: '+79990001122',
              name: 'Иван Администратор',
              role: 'client',
              sub_role: 'administrator',
              company_id: COMPANY_ID,
              active_company_id: COMPANY_ID,
              active_company_name: 'Тестовая Компания',
              can_view_applications: true,
              can_create_applications: true,
              is_active: true,
            },
          })
        }

        if (path === '/api/v1/users/me/companies') {
          return fulfill(route, {
            companies: [
              {
                id: COMPANY_ID,
                name: 'Тестовая Компания',
                inn: '7707083893',
                sub_role: 'administrator',
                can_view_applications: true,
                can_create_applications: true,
              },
            ],
          })
        }

        if (path === `/api/v1/users/me/companies/${COMPANY_ID}/members`) {
          return fulfill(route, {
            members: [
              {
                user_id: ADMIN_ID,
                name: 'Иван Администратор',
                phone: '+79990001122',
                sub_role: 'administrator',
                can_view_applications: true,
                can_create_applications: true,
              },
              {
                user_id: EMPLOYEE_ID,
                name: 'Сергей Сотрудник',
                phone: '+79995556677',
                sub_role: 'employee',
                can_view_applications: false,
                can_create_applications: false,
              },
            ],
          })
        }

        if (path === `/api/v1/users/me/companies/${COMPANY_ID}/members/${EMPLOYEE_ID}` && method === 'DELETE') {
          return fulfill(route, { success: true })
        }

        if (path === '/api/v1/section-visibility/public') {
          return fulfill(route, { visible: true })
        }

        if (path.startsWith('/api/v1/applications')) {
          return fulfill(route, { applications: [], pagination: null })
        }

        return fulfill(route, {})
      },
    )

    await page.goto('/cabinet?tab=employees', { waitUntil: 'networkidle' })

    await expect(page.getByRole('heading', { name: 'Сотрудники компании' })).toBeVisible()

    const table = page.locator('table')
    await expect(table).toBeVisible()

    // На строке самого администратора кнопка «Удалить» заблокирована (disabled)
    const adminRow = table.locator('tr', { hasText: 'Иван Администратор' })
    await expect(adminRow).toBeVisible()
    const adminDeleteBtn = adminRow.locator('button', { hasText: 'Удалить' })
    await expect(adminDeleteBtn).toBeDisabled()

    // На строке другого участника кнопка «Удалить» активна
    const employeeRow = table.locator('tr', { hasText: 'Сергей Сотрудник' })
    await expect(employeeRow).toBeVisible()
    const employeeDeleteBtn = employeeRow.locator('button', { hasText: 'Удалить' })
    await expect(employeeDeleteBtn).toBeEnabled()

    // Проверяем удаление сотрудника
    page.once('dialog', (dialog) => dialog.accept())
    await employeeDeleteBtn.click()
    await expect(table.locator('tr', { hasText: 'Сергей Сотрудник' })).toHaveCount(0)
  })

  test('Сотрудник компании видит вкладку «Сотрудники», но не видит кнопку «Удалить» и не может управлять составом', async ({
    page,
  }) => {
    const fulfill = (route: any, json: unknown, status = 200) =>
      route.fulfill({
        status,
        json,
        headers: {
          'access-control-allow-origin': route.request().headers().origin || '*',
          'access-control-allow-credentials': 'true',
        },
      })

    await page.route(
      (url: URL) => url.pathname.startsWith('/api/'),
      async (route: any) => {
        const req = route.request()
        const url = new URL(req.url())
        const path = url.pathname.replace(/\/$/, '')
        const method = req.method()

        if (method === 'OPTIONS') {
          return route.fulfill({
            status: 204,
            headers: {
              'access-control-allow-origin': req.headers().origin || '*',
              'access-control-allow-credentials': 'true',
              'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
              'access-control-allow-headers': '*',
            },
          })
        }

        if (path === '/api/v1/auth/me') {
          return fulfill(route, {
            user: {
              id: EMPLOYEE_ID,
              phone: '+79995556677',
              name: 'Сергей Сотрудник',
              role: 'client',
              sub_role: 'employee',
              company_id: COMPANY_ID,
              active_company_id: COMPANY_ID,
              active_company_name: 'Тестовая Компания',
              can_view_applications: false,
              can_create_applications: false,
              is_active: true,
            },
          })
        }

        if (path === '/api/v1/users/me/companies') {
          return fulfill(route, {
            companies: [
              {
                id: COMPANY_ID,
                name: 'Тестовая Компания',
                inn: '7707083893',
                sub_role: 'employee',
                can_view_applications: false,
                can_create_applications: false,
              },
            ],
          })
        }

        if (path === `/api/v1/users/me/companies/${COMPANY_ID}/members`) {
          return fulfill(route, {
            members: [
              {
                user_id: ADMIN_ID,
                name: 'Иван Администратор',
                phone: '+79990001122',
                sub_role: 'administrator',
                can_view_applications: true,
                can_create_applications: true,
              },
              {
                user_id: EMPLOYEE_ID,
                name: 'Сергей Сотрудник',
                phone: '+79995556677',
                sub_role: 'employee',
                can_view_applications: false,
                can_create_applications: false,
              },
            ],
          })
        }

        if (path === '/api/v1/section-visibility/public') {
          return fulfill(route, { visible: true })
        }

        if (path.startsWith('/api/v1/applications')) {
          return fulfill(route, { applications: [], pagination: null })
        }

        return fulfill(route, {})
      },
    )

    await page.goto('/cabinet', { waitUntil: 'networkidle' })

    // Сотрудник компании ВИДИТ вкладку «Сотрудники» в навигации
    const employeesTabButton = page.locator('nav button', { hasText: 'Сотрудники' })
    await expect(employeesTabButton).toBeVisible()

    // Переходим на вкладку «Сотрудники»
    await employeesTabButton.click()
    await expect(page.getByRole('heading', { name: 'Сотрудники компании' })).toBeVisible()

    // Таблица отображается со списком участников компании
    const table = page.locator('table')
    await expect(table).toBeVisible()
    await expect(table.locator('tr', { hasText: 'Иван Администратор' })).toBeVisible()
    await expect(table.locator('tr', { hasText: 'Сергей Сотрудник' })).toBeVisible()

    // Кнопки «Удалить» у сотрудника НЕТ ни на одной строке
    const deleteButtons = page.locator('button', { hasText: 'Удалить' })
    await expect(deleteButtons).toHaveCount(0)

    // Кнопка «Пригласить сотрудника» также скрыта
    const inviteButton = page.locator('button', { hasText: 'Пригласить сотрудника' })
    await expect(inviteButton).toHaveCount(0)

    // Заголовок колонки «Действия» остаётся видимым
    const actionsHeader = page.locator('th', { hasText: 'Действия' })
    await expect(actionsHeader).toBeVisible()
  })

  test('Менеджер компании видит список сотрудников, колонку «Действия» и кнопку «Пригласить», но не видит кнопку «Удалить»', async ({
    page,
  }) => {
    const MANAGER_ID = '33333333-3333-4333-8333-333333333333'
    const fulfill = (route: any, json: unknown, status = 200) =>
      route.fulfill({
        status,
        json,
        headers: {
          'access-control-allow-origin': route.request().headers().origin || '*',
          'access-control-allow-credentials': 'true',
        },
      })

    await page.route(
      (url: URL) => url.pathname.startsWith('/api/'),
      async (route: any) => {
        const req = route.request()
        const url = new URL(req.url())
        const path = url.pathname.replace(/\/$/, '')
        const method = req.method()

        if (method === 'OPTIONS') {
          return route.fulfill({
            status: 204,
            headers: {
              'access-control-allow-origin': req.headers().origin || '*',
              'access-control-allow-credentials': 'true',
              'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
              'access-control-allow-headers': '*',
            },
          })
        }

        if (path === '/api/v1/auth/me') {
          return fulfill(route, {
            user: {
              id: MANAGER_ID,
              phone: '+79993334455',
              name: 'Мария Менеджер',
              role: 'client',
              sub_role: 'manager',
              company_id: COMPANY_ID,
              active_company_id: COMPANY_ID,
              active_company_name: 'Тестовая Компания',
              can_view_applications: true,
              can_create_applications: true,
              is_active: true,
            },
          })
        }

        if (path === '/api/v1/users/me/companies') {
          return fulfill(route, {
            companies: [
              {
                id: COMPANY_ID,
                name: 'Тестовая Компания',
                inn: '7707083893',
                sub_role: 'manager',
                can_view_applications: true,
                can_create_applications: true,
              },
            ],
          })
        }

        if (path === `/api/v1/users/me/companies/${COMPANY_ID}/members`) {
          return fulfill(route, {
            members: [
              {
                user_id: ADMIN_ID,
                name: 'Иван Администратор',
                phone: '+79991112233',
                sub_role: 'administrator',
                can_view_applications: true,
                can_create_applications: true,
              },
              {
                user_id: MANAGER_ID,
                name: 'Мария Менеджер',
                phone: '+79993334455',
                sub_role: 'manager',
                can_view_applications: true,
                can_create_applications: true,
              },
            ],
          })
        }

        if (path === '/api/v1/section-visibility/public') {
          return fulfill(route, { visible: true })
        }

        if (path.startsWith('/api/v1/applications')) {
          return fulfill(route, { applications: [], pagination: null })
        }

        return fulfill(route, {})
      },
    )

    await page.goto('/cabinet?tab=employees', { waitUntil: 'networkidle' })

    await expect(page.getByRole('heading', { name: 'Сотрудники компании' })).toBeVisible()

    // Кнопка «Пригласить сотрудника» видна менеджеру
    const inviteButton = page.locator('button', { hasText: 'Пригласить сотрудника' })
    await expect(inviteButton).toBeVisible()

    // Колонка «Действия» остаётся видимой
    const actionsHeader = page.locator('th', { hasText: 'Действия' })
    await expect(actionsHeader).toBeVisible()

    // Кнопка «Удалить» отсутствует
    const deleteButtons = page.locator('button', { hasText: 'Удалить' })
    await expect(deleteButtons).toHaveCount(0)
  })

  test('Пользователь без компании не видит вкладку «Сотрудники»', async ({
    page,
  }) => {
    const fulfill = (route: any, json: unknown, status = 200) =>
      route.fulfill({
        status,
        json,
        headers: {
          'access-control-allow-origin': route.request().headers().origin || '*',
          'access-control-allow-credentials': 'true',
        },
      })

    await page.route(
      (url: URL) => url.pathname.startsWith('/api/'),
      async (route: any) => {
        const req = route.request()
        const url = new URL(req.url())
        const path = url.pathname.replace(/\/$/, '')
        const method = req.method()

        if (method === 'OPTIONS') {
          return route.fulfill({
            status: 204,
            headers: {
              'access-control-allow-origin': req.headers().origin || '*',
              'access-control-allow-credentials': 'true',
              'access-control-allow-methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
              'access-control-allow-headers': '*',
            },
          })
        }

        if (path === '/api/v1/auth/me') {
          return fulfill(route, {
            user: {
              id: '99999999-9999-4999-8999-999999999999',
              phone: '+79998887766',
              name: 'Клиент Без Компании',
              role: 'client',
              sub_role: null,
              company_id: null,
              active_company_id: null,
              active_company_name: null,
              can_view_applications: true,
              can_create_applications: true,
              is_active: true,
            },
          })
        }

        if (path === '/api/v1/users/me/companies') {
          return fulfill(route, { companies: [] })
        }

        if (path === '/api/v1/section-visibility/public') {
          return fulfill(route, { visible: true })
        }

        if (path.startsWith('/api/v1/applications')) {
          return fulfill(route, { applications: [], pagination: null })
        }

        return fulfill(route, {})
      },
    )

    await page.goto('/cabinet', { waitUntil: 'networkidle' })

    const employeesTabButton = page.locator('nav button', { hasText: 'Сотрудники' })
    await expect(employeesTabButton).toHaveCount(0)
  })
})

