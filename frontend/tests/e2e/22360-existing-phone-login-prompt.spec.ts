import fs from 'node:fs'
import { expect, test } from '@playwright/test'

const isDocker = fs.existsSync('/.dockerenv')
const defaultBaseUrl = isDocker ? 'http://nginx' : 'http://127.0.0.1'

test.use({
  baseURL: process.env.E2E_BASE_URL ?? defaultBaseUrl,
})

test.describe('Задача 22360: Уведомление об уже зарегистрированном номере и кнопка перехода к логину', () => {
  test('Отображение уведомления и кнопки Войти при вводе уже зарегистрированного номера', async ({
    page,
  }) => {
    // 1. Открываем страницу авторизации
    await page.goto('/auth')

    // 2. Проверяем наличие модального окна входа
    const modalDialog = page.getByRole('dialog')
    const modalTitle = modalDialog.locator('h3')
    await expect(modalTitle).toHaveText('Вход в личный кабинет')

    // 3. Переключаемся на форму регистрации
    const toRegisterBtn = modalDialog.getByRole('button', { name: 'Нет аккаунта? Зарегистрироваться' })
    await toRegisterBtn.click()

    await expect(modalTitle).toHaveText('Регистрация')

    // 4. Вводим номер телефона, который уже зарегистрирован в системе (+76660000001)
    const phoneInput = modalDialog.locator('#phone')
    await phoneInput.fill('6660000001')
    await expect(phoneInput).toHaveValue('+7 (666) 000-00-01')

    // 5. Отмечаем обязательные согласия
    const privacyCheckboxes = modalDialog.locator('input[type="checkbox"]')
    await privacyCheckboxes.nth(0).check()
    await privacyCheckboxes.nth(1).check()

    // 6. Отправляем форму регистрации
    const submitBtn = modalDialog.getByRole('button', { name: 'Зарегистрироваться', exact: true })
    await submitBtn.click()

    // 7. Проверяем появление уведомления об уже зарегистрированном номере
    const alertMessage = modalDialog.getByText('Введеный номер уже зарегистрирован на платформе')
    await expect(alertMessage).toBeVisible()

    // 8. Проверяем наличие кнопки "Войти" под уведомлением
    const loginBtn = modalDialog.getByRole('button', { name: 'Войти', exact: true })
    await expect(loginBtn).toBeVisible()

    // Сохраняем скриншот уведомления и кнопки
    await page.screenshot({ path: '/app/test-results/22360-conflict-alert.png' })

    // 9. Кликаем по кнопке "Войти"
    await loginBtn.click()

    // 10. Проверяем, что модальное окно переключилось на шаг логина
    await expect(modalTitle).toHaveText('Вход в личный кабинет')

    // 11. Проверяем, что введённый номер телефона сохранился в поле ввода
    await expect(phoneInput).toHaveValue('+7 (666) 000-00-01')

    // 12. Проверяем, что кнопка отправки изменилась на "Получить код"
    const getCodeBtn = modalDialog.getByRole('button', { name: 'Получить код', exact: true })
    await expect(getCodeBtn).toBeVisible()

    // 13. Проверяем, что предупреждение об уже существующем номере скрыто
    await expect(alertMessage).not.toBeVisible()

    // Ждём полного завершения CSS-анимации перехода
    await page.waitForTimeout(1000)

    // Сохраняем скриншот формы входа с сохранённым номером
    await page.screenshot({ path: '/app/test-results/22360-switched-to-login.png' })
  })
})
