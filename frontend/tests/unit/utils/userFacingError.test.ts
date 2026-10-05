// @ts-ignore vitest is executed via bunx vitest
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { getUserFacingErrorMessage, DEFAULT_USER_FACING_ERROR } from '../../../utils/userFacingError'

describe('getUserFacingErrorMessage', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('masks snake_case technical identifiers (leasing_purpose) and logs to console.error', () => {
    const error = { data: { detail: 'Некорректное значение leasing_purpose' } }
    const result = getUserFacingErrorMessage(error, 'Не удалось сохранить позиции заявки')

    expect(result).toBe('Не удалось сохранить позиции заявки')
    expect(console.error).toHaveBeenCalledWith('[API Error]', error)
  })

  it('returns default message if no fallback is provided for technical error', () => {
    const error = { data: { detail: 'Некорректное значение leasing_purpose' } }
    const result = getUserFacingErrorMessage(error)

    expect(result).toBe(DEFAULT_USER_FACING_ERROR)
    expect(console.error).toHaveBeenCalledWith('[API Error]', error)
  })

  it('masks other snake_case identifiers like line_id, item_id, status_code, vehicle_id, application_id', () => {
    expect(getUserFacingErrorMessage({ data: { detail: 'line_id не найден' } })).toBe(DEFAULT_USER_FACING_ERROR)
    expect(getUserFacingErrorMessage({ data: { detail: 'item_id is required' } })).toBe(DEFAULT_USER_FACING_ERROR)
    expect(getUserFacingErrorMessage({ data: { detail: 'Invalid status_code' } })).toBe(DEFAULT_USER_FACING_ERROR)
    expect(getUserFacingErrorMessage({ data: { detail: 'vehicle_id mismatch' } })).toBe(DEFAULT_USER_FACING_ERROR)
    expect(getUserFacingErrorMessage({ data: { detail: 'application_id отсутствует' } })).toBe(DEFAULT_USER_FACING_ERROR)
  })

  it('masks Pydantic/FastAPI validation error array in detail', () => {
    const error = {
      data: {
        detail: [
          { loc: ['body', 'items', 0, 'leasing_purpose'], msg: 'field required', type: 'value_error.missing' },
        ],
      },
    }
    const result = getUserFacingErrorMessage(error, 'Ошибка валидации данных')

    expect(result).toBe('Ошибка валидации данных')
    expect(console.error).toHaveBeenCalledWith('[API Error]', error)
  })

  it('masks stack traces and service words', () => {
    const tracebackError = new Error('Traceback (most recent call last):\n  File "main.py", line 12\nZeroDivisionError')
    expect(getUserFacingErrorMessage(tracebackError)).toBe(DEFAULT_USER_FACING_ERROR)

    const pydanticError = new Error('Pydantic ValidationError occurred')
    expect(getUserFacingErrorMessage(pydanticError)).toBe(DEFAULT_USER_FACING_ERROR)

    const internalError = new Error('500 Internal Server Error')
    expect(getUserFacingErrorMessage(internalError)).toBe(DEFAULT_USER_FACING_ERROR)

    const status500Error = new Error('Server returned status 500')
    expect(getUserFacingErrorMessage(status500Error)).toBe(DEFAULT_USER_FACING_ERROR)

    const typeError = new TypeError('Cannot read properties of undefined')
    expect(getUserFacingErrorMessage(typeError)).toBe(DEFAULT_USER_FACING_ERROR)

    const objectObject = new Error('[object Object]')
    expect(getUserFacingErrorMessage(objectObject)).toBe(DEFAULT_USER_FACING_ERROR)
  })

  it('masks serialized JSON string errors and unhandled objects', () => {
    const jsonError = { data: { detail: '{"code": 500, "message": "internal_server_error"}' } }
    expect(getUserFacingErrorMessage(jsonError)).toBe(DEFAULT_USER_FACING_ERROR)

    const objectDetailError = { data: { detail: { unhandled_field: 123 } } }
    expect(getUserFacingErrorMessage(objectDetailError)).toBe(DEFAULT_USER_FACING_ERROR)
  })

  it('returns fallback or default when error is null, undefined, or empty', () => {
    expect(getUserFacingErrorMessage(null)).toBe(DEFAULT_USER_FACING_ERROR)
    expect(getUserFacingErrorMessage(undefined, 'Кастомный фоллбэк')).toBe('Кастомный фоллбэк')
    expect(getUserFacingErrorMessage({}, 'Кастомный фоллбэк')).toBe('Кастомный фоллбэк')
    expect(getUserFacingErrorMessage('', 'Кастомный фоллбэк')).toBe('Кастомный фоллбэк')
    expect(getUserFacingErrorMessage('   ')).toBe(DEFAULT_USER_FACING_ERROR)
  })

  it('returns human-readable Russian business messages without masking or logging', () => {
    const validError1 = { data: { detail: 'Пожалуйста, выберите цель лизинга из списка' } }
    expect(getUserFacingErrorMessage(validError1, 'Не удалось сохранить')).toBe('Пожалуйста, выберите цель лизинга из списка')
    expect(console.error).not.toHaveBeenCalled()

    const validError2 = { data: { detail: 'Позиция не найдена в заявке' } }
    expect(getUserFacingErrorMessage(validError2)).toBe('Позиция не найдена в заявке')
    expect(console.error).not.toHaveBeenCalled()

    const validError3 = { data: { detail: { message: 'Компания не найдена' } } }
    expect(getUserFacingErrorMessage(validError3)).toBe('Компания не найдена')
    expect(console.error).not.toHaveBeenCalled()

    const validError4 = { data: { message: 'Заполните обязательные поля анкеты' } }
    expect(getUserFacingErrorMessage(validError4)).toBe('Заполните обязательные поля анкеты')
    expect(console.error).not.toHaveBeenCalled()

    const validError5 = new Error('Для оформления спецтехники выберите сохранённую компанию.')
    expect(getUserFacingErrorMessage(validError5)).toBe('Для оформления спецтехники выберите сохранённую компанию.')
    expect(console.error).not.toHaveBeenCalled()

    const validError6 = { message: 'Не удалось проверить статус платежа' }
    expect(getUserFacingErrorMessage(validError6)).toBe('Не удалось проверить статус платежа')
    expect(console.error).not.toHaveBeenCalled()
  })
})
