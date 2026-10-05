import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  isTemplateErrorCode,
  localizeImportError,
  localizeImportIssue,
  localizeSheetName,
} from '../../../features/specialEquipmentImport/utils/importErrors'

describe('importErrors utility', () => {
  describe('localizeSheetName', () => {
    it('translates known sheet names', () => {
      assert.equal(localizeSheetName('categories'), 'Категории')
      assert.equal(localizeSheetName('CATEGORIES'), 'Категории')
      assert.equal(localizeSheetName('manufacturers'), 'Производители')
      assert.equal(localizeSheetName('models'), 'Модели')
      assert.equal(localizeSheetName('modifications'), 'Модификации')
      assert.equal(localizeSheetName('trims'), 'Комплектации')
      assert.equal(localizeSheetName('colors'), 'Цвета')
      assert.equal(localizeSheetName('attributes'), 'Характеристики')
      assert.equal(localizeSheetName('products'), 'Объявления/Товары')
    })

    it('returns unknown sheet name as-is', () => {
      assert.equal(localizeSheetName('CustomSheet'), 'CustomSheet')
    })
  })

  describe('localizeImportError', () => {
    it('handles PARAMETERS_VERSION_MISMATCH with correct title and hint', () => {
      const result = localizeImportError('PARAMETERS_VERSION_MISMATCH', 'PARAMETERS_VERSION_MISMATCH')
      assert.equal(result.code, 'PARAMETERS_VERSION_MISMATCH')
      assert.equal(result.title, 'Несоответствие версии шаблона Excel')
      assert.ok(result.description.includes('версии 6'))
      assert.ok(result.hint?.includes('Скачайте актуальный шаблон v6'))
    })

    it('handles parameterized SHEET_HEADER_INVALID with sheet translation', () => {
      const result = localizeImportError('SHEET_HEADER_INVALID:categories')
      assert.equal(result.code, 'SHEET_HEADER_INVALID')
      assert.equal(result.title, 'Неверные заголовки на листе «Категории»')
      assert.ok(result.description.includes('Категории'))
      assert.ok(result.hint?.includes('Категории'))
    })

    it('handles UNKNOWN_SHEET with sheet translation', () => {
      const result = localizeImportError('UNKNOWN_SHEET:foo')
      assert.equal(result.code, 'UNKNOWN_SHEET')
      assert.equal(result.title, 'Неизвестный лист «foo»')
      assert.ok(result.description.includes('«foo»'))
      assert.ok(result.hint?.includes('Удалите лишние листы'))
    })

    it('handles PARAMETERS_KEYS_MISSING with parameters list', () => {
      const result = localizeImportError('PARAMETERS_KEYS_MISSING:schema_version,mode')
      assert.equal(result.code, 'PARAMETERS_KEYS_MISSING')
      assert.equal(result.title, 'Отсутствуют обязательные параметры')
      assert.ok(result.description.includes('schema_version,mode'))
      assert.ok(result.hint)
    })

    it('handles FULL_SNAPSHOT_SHEETS_MISSING with sheet translations', () => {
      const result = localizeImportError('FULL_SNAPSHOT_SHEETS_MISSING:categories,marks')
      assert.equal(result.code, 'FULL_SNAPSHOT_SHEETS_MISSING')
      assert.equal(result.title, 'Отсутствуют листы для полной замены каталога')
      assert.ok(result.description.includes('«Категории»'))
      assert.ok(result.description.includes('«Марки»'))
      assert.ok(result.hint)
    })

    it('handles row-level error codes like MARK_NOT_FOUND', () => {
      const result = localizeImportError('MARK_NOT_FOUND')
      assert.equal(result.code, 'MARK_NOT_FOUND')
      assert.equal(result.title, 'Марка не найдена')
      assert.ok(result.description.includes('Марка с указанным кодом'))
      assert.ok(result.hint?.includes('Марки'))
    })

    it('handles security and format codes like XLSX_ACTIVE_CONTENT_FORBIDDEN and XLSX_FORMULA_FORBIDDEN', () => {
      const activeContent = localizeImportError('XLSX_ACTIVE_CONTENT_FORBIDDEN')
      assert.equal(activeContent.title, 'Запрещённое активное содержимое')
      assert.ok(activeContent.description.includes('макросы'))

      const formula = localizeImportError('XLSX_FORMULA_FORBIDDEN')
      assert.equal(formula.title, 'Формулы в ячейках запрещены')
      assert.ok(formula.description.includes('формулы Excel'))
    })

    it('provides informative fallback for unknown error codes', () => {
      const result = localizeImportError('SOME_UNKNOWN_CODE', 'SOME_UNKNOWN_CODE')
      assert.equal(result.code, 'SOME_UNKNOWN_CODE')
      assert.equal(result.title, 'Ошибка валидации импорта')
      assert.ok(result.description.includes('SOME_UNKNOWN_CODE'))
      assert.ok(result.hint)
    })

    it('uses human-readable detail as description if provided for unknown code', () => {
      const result = localizeImportError('CUSTOM_ERROR', 'База данных временно недоступна для чтения цен')
      assert.equal(result.code, 'CUSTOM_ERROR')
      assert.equal(result.description, 'База данных временно недоступна для чтения цен')
      assert.equal(result.title, 'База данных временно недоступна для чтения цен')
    })

    it('handles image error codes with specific recommendations', () => {
      const urlResult = localizeImportError('PRODUCT_IMAGE_URL_INVALID')
      assert.equal(urlResult.code, 'PRODUCT_IMAGE_URL_INVALID')
      assert.ok(urlResult.hint?.includes('Google Drive'))

      const limitResult = localizeImportError('PRODUCT_IMAGES_LIMIT_EXCEEDED')
      assert.equal(limitResult.code, 'PRODUCT_IMAGES_LIMIT_EXCEEDED')
      assert.ok(limitResult.hint?.includes('50'))

      const statusResult = localizeImportError('IMAGE_HTTP_STATUS_403')
      assert.equal(statusResult.code, 'IMAGE_HTTP_STATUS_403')
      assert.ok(statusResult.hint?.includes('Все, у кого есть ссылка'))

      const contentTypeResult = localizeImportError('IMAGE_CONTENT_TYPE_INVALID')
      assert.equal(contentTypeResult.code, 'IMAGE_CONTENT_TYPE_INVALID')
      assert.ok(contentTypeResult.hint?.includes('Все, у кого есть ссылка'))
    })

    it('handles null/undefined code gracefully', () => {
      const result = localizeImportError(null, null)
      assert.equal(result.title, 'Ошибка проверки импорта')
      assert.ok(result.description)
      assert.ok(result.hint)
      assert.equal(result.code, undefined)
    })

    it('handles REQUIRED_FIELD_MISSING with default and parsed hints', () => {
      const basic = localizeImportError('REQUIRED_FIELD_MISSING')
      assert.equal(basic.code, 'REQUIRED_FIELD_MISSING')
      assert.equal(basic.title, 'Обязательное поле не заполнено')
      assert.equal(basic.description, 'В файле не заполнено обязательное поле.')
      assert.equal(basic.hint, 'Заполните обязательную колонку на указанном листе.')

      const withDetail = localizeImportError(
        'REQUIRED_FIELD_MISSING',
        'Лист «categories», строка 5, код CAT1: Не заполнено обязательное поле «Название»',
      )
      assert.equal(withDetail.description, 'Лист «categories», строка 5, код CAT1: Не заполнено обязательное поле «Название»')
      assert.equal(withDetail.hint, 'Заполните колонку «Название» на листе «Категории», строка 5')

      const withContext = localizeImportError('REQUIRED_FIELD_MISSING', undefined, {
        sheetCode: 'categories',
        rowNumber: 10,
        columnName: 'Название',
      })
      assert.equal(withContext.hint, 'Заполните колонку «Название» на листе «Категории», строка 10')
    })

    it('handles UNIQUE_CONFLICT with informative hint', () => {
      const basic = localizeImportError('UNIQUE_CONFLICT')
      assert.equal(basic.code, 'UNIQUE_CONFLICT')
      assert.equal(basic.title, 'Конфликт уникальности записи')
      assert.equal(basic.description, 'Запись с такими параметрами уже существует.')
      assert.equal(basic.hint, 'Запись с таким названием уже существует — используйте её код или измените название')

      const withDetail = localizeImportError(
        'UNIQUE_CONFLICT',
        'Категория с таким названием уже существует с другим кодом',
      )
      assert.equal(withDetail.description, 'Категория с таким названием уже существует с другим кодом')
      assert.equal(withDetail.hint, 'Запись с таким названием уже существует — используйте её код или измените название')
    })

    it('handles DEPENDENCY_NOT_APPLIED with dependency hint', () => {
      const basic = localizeImportError('DEPENDENCY_NOT_APPLIED')
      assert.equal(basic.code, 'DEPENDENCY_NOT_APPLIED')
      assert.equal(basic.title, 'Связанная запись не применена')
      assert.equal(basic.description, 'Связанная запись не создана — см. ошибку по ней выше.')
      assert.equal(basic.hint, 'Сначала исправьте ошибку в связанной записи')

      const withDetail = localizeImportError(
        'DEPENDENCY_NOT_APPLIED',
        'Не применено, так как категория LEGKOVOI не загружена',
      )
      assert.equal(withDetail.description, 'Не применено, так как категория LEGKOVOI не загружена')
      assert.equal(withDetail.hint, 'Сначала исправьте ошибку в связанной записи')
    })

    it('handles VALUE_OUT_OF_RANGE and AGGREGATE_APPLY_CONFLICT', () => {
      const range = localizeImportError('VALUE_OUT_OF_RANGE')
      assert.equal(range.title, 'Недопустимое значение')
      assert.equal(range.description, 'Значение поля выходит за допустимые границы.')
      assert.equal(range.hint, 'Проверьте допустимые диапазоны и форматы значений.')

      const conflict = localizeImportError('AGGREGATE_APPLY_CONFLICT')
      assert.equal(conflict.title, 'Конфликт применения изменений')
      assert.equal(conflict.description, 'Агрегат не применён из-за конфликта зависимостей или уникальности.')
      assert.equal(conflict.hint, 'Исправьте связанные записи или параметры уникальности в файле каталога.')
    })

    it('handles APPLY_FAILED with internal error message and support hint', () => {
      const result = localizeImportError('APPLY_FAILED')
      assert.equal(result.code, 'APPLY_FAILED')
      assert.equal(result.title, 'Ошибка применения импорта')
      assert.equal(result.description, 'Не удалось применить каталог спецтехники из-за внутренней ошибки.')
      assert.equal(result.hint, 'Внутренняя ошибка при загрузке. Обратитесь в поддержку, указав номер задачи импорта')
    })

    it('shows template v6 recommendation only for template codes, not for data codes', () => {
      const templateCodes = [
        'PARAMETERS_VERSION_MISMATCH',
        'PARAMETERS_SHEET_MISSING',
        'PARAMETERS_KEYS_MISSING',
        'SHEET_HEADER_INVALID',
        'UNKNOWN_SHEET',
        'FULL_SNAPSHOT_SHEETS_MISSING',
        'MANIFEST_SHEET_MISSING',
        'NORMALIZED_ARTIFACT_INVALID',
        'CODE_INVALID',
        'TEMPLATE_SOMETHING_NEW',
      ]
      for (const code of templateCodes) {
        assert.ok(isTemplateErrorCode(code), `${code} should be recognized as template code`)
        const res = localizeImportError(code)
        assert.ok(
          res.hint?.includes('шаблону') || res.hint?.includes('шаблон'),
          `Template code ${code} should have template hint, got: ${res.hint}`,
        )
      }

      const dataCodes = [
        'REQUIRED_FIELD_MISSING',
        'UNIQUE_CONFLICT',
        'DEPENDENCY_NOT_APPLIED',
        'VALUE_OUT_OF_RANGE',
        'AGGREGATE_APPLY_CONFLICT',
        'APPLY_FAILED',
        'CATEGORY_INVALID',
        'MARK_INVALID',
        'PRODUCT_INVALID',
        'CUSTOM_DATA_ERROR',
      ]
      for (const code of dataCodes) {
        assert.ok(!isTemplateErrorCode(code), `${code} should NOT be recognized as template code`)
        const res = localizeImportError(code)
        assert.ok(
          !res.hint?.includes('v6') && !res.hint?.includes('актуальному шаблону'),
          `Data code ${code} must NOT have template v6 recommendation, got: ${res.hint}`,
        )
      }
    })
  })

  describe('localizeImportIssue', () => {
    it('translates code when message repeats code', () => {
      const issue = localizeImportIssue('MARK_NOT_FOUND', 'MARK_NOT_FOUND')
      assert.equal(issue.message, 'Марка с указанным кодом отсутствует в каталоге и не создаётся в текущем файле.')
      assert.ok(issue.hint?.includes('Марки'))
    })

    it('preserves specific message and attaches hint if available', () => {
      const issue = localizeImportIssue('TARGET_WAREHOUSE_INVALID', 'Склад «Северный» деактивирован')
      assert.equal(issue.message, 'Склад «Северный» деактивирован')
      assert.ok(issue.hint?.includes('Выберите активный склад'))
    })

    it('formats contextual hint for REQUIRED_FIELD_MISSING when context is provided', () => {
      const issueWithFullContext = localizeImportIssue(
        'REQUIRED_FIELD_MISSING',
        'Не заполнено обязательное поле «Название»',
        {
          sheetCode: 'categories',
          rowNumber: 12,
          columnName: 'Название',
        },
      )
      assert.equal(issueWithFullContext.message, 'Не заполнено обязательное поле «Название»')
      assert.equal(
        issueWithFullContext.hint,
        'Заполните колонку «Название» на листе «Категории», строка 12',
      )

      const issueWhenMessageRepeatsCode = localizeImportIssue(
        'REQUIRED_FIELD_MISSING',
        'REQUIRED_FIELD_MISSING',
        {
          sheetCode: 'marks',
          rowNumber: 4,
          columnName: 'Код марки',
        },
      )
      assert.equal(issueWhenMessageRepeatsCode.message, 'В файле не заполнено обязательное поле.')
      assert.equal(
        issueWhenMessageRepeatsCode.hint,
        'Заполните колонку «Код марки» на листе «Марки», строка 4',
      )
    })

    it('handles context-free REQUIRED_FIELD_MISSING, UNIQUE_CONFLICT, DEPENDENCY_NOT_APPLIED and APPLY_FAILED', () => {
      const required = localizeImportIssue('REQUIRED_FIELD_MISSING', 'REQUIRED_FIELD_MISSING')
      assert.equal(required.message, 'В файле не заполнено обязательное поле.')
      assert.equal(required.hint, 'Заполните обязательную колонку на указанном листе.')

      const unique = localizeImportIssue('UNIQUE_CONFLICT', 'Категория с таким названием уже существует с другим кодом')
      assert.equal(unique.message, 'Категория с таким названием уже существует с другим кодом')
      assert.equal(unique.hint, 'Запись с таким названием уже существует — используйте её код или измените название')

      const dep = localizeImportIssue('DEPENDENCY_NOT_APPLIED', 'Связанная запись не создана — см. ошибку по ней выше.')
      assert.equal(dep.message, 'Связанная запись не создана — см. ошибку по ней выше.')
      assert.equal(dep.hint, 'Сначала исправьте ошибку в связанной записи')

      const apply = localizeImportIssue('APPLY_FAILED', 'APPLY_FAILED')
      assert.equal(apply.message, 'Не удалось применить каталог спецтехники из-за внутренней ошибки.')
      assert.equal(apply.hint, 'Внутренняя ошибка при загрузке. Обратитесь в поддержку, указав номер задачи импорта')
    })
  })
})
