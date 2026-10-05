export interface LocalizedImportError {
  title: string
  description: string
  hint?: string
  code?: string
}

export const SHEET_NAME_TRANSLATIONS: Record<string, string> = {
  marks: 'Марки',
  manufacturers: 'Производители',
  models: 'Модели',
  modifications: 'Модификации',
  trims: 'Комплектации',
  modification_categories: 'Категории модификаций',
  modification_attribute_values: 'Характеристики модификаций',
  trim_attributes: 'Характеристики комплектаций',
  trim_attribute_values: 'Значения комплектаций',
  categories: 'Категории',
  category_relations: 'Связи категорий',
  attribute_groups: 'Группы характеристик',
  attributes: 'Характеристики',
  attribute_options: 'Варианты характеристик',
  category_attributes: 'Характеристики категорий',
  colors: 'Цвета',
  products: 'Объявления/Товары',
  product_categories: 'Категории объявлений',
  product_attachments: 'Совместимые надстройки',
  product_components: 'Компоненты составных объявлений',
  parameters: 'Параметры',
  instructions: 'Инструкция',
  workbook: 'Книга',
}

export function localizeSheetName(sheet: string): string {
  const normalized = sheet.trim().toLowerCase()
  return SHEET_NAME_TRANSLATIONS[normalized] ?? sheet
}

export interface ImportIssueContext {
  sheetCode?: string
  rowNumber?: number | null
  columnName?: string | null
}

export function isTemplateErrorCode(code?: string | null): boolean {
  if (!code) return false
  const normalized = code.trim().toUpperCase()
  const base = normalized.split(':')[0].trim()
  return (
    base.startsWith('TEMPLATE_') ||
    base.startsWith('PARAMETERS_') ||
    base.startsWith('MANIFEST_') ||
    base.startsWith('XLSX_') ||
    base === 'UNKNOWN_SHEET' ||
    base === 'SHEET_HEADER_INVALID' ||
    base === 'FULL_SNAPSHOT_SHEETS_MISSING' ||
    base === 'NORMALIZED_ARTIFACT_INVALID' ||
    base === 'CODE_INVALID' ||
    base === 'CODE_TOO_LONG'
  )
}

interface ErrorDefinition {
  title: string | ((param?: string) => string)
  description: string | ((param?: string, detail?: string) => string)
  hint?: string | ((param?: string, detail?: string) => string)
}

const ERROR_DEFINITIONS: Record<string, ErrorDefinition> = {
  // Parameters sheet errors
  PARAMETERS_VERSION_MISMATCH: {
    title: 'Несоответствие версии шаблона Excel',
    description: 'В загруженном файле указана устаревшая версия шаблона или повреждён лист «Параметры». Система ожидает актуальный шаблон версии 6.',
    hint: 'Скачайте актуальный шаблон v6 по кнопке «Скачать шаблон» выше и перенесите в него данные, либо укажите значение «6» для параметра «Версия шаблона» на листе «Параметры».',
  },
  PARAMETERS_SHEET_MISSING: {
    title: 'Отсутствует лист «Параметры»',
    description: 'В книге Excel не найден обязательный служебный лист «Параметры», содержащий версию и параметры импорта.',
    hint: 'Скачайте актуальный шаблон каталога. Служебный лист «Параметры» формируется автоматически и не должен удаляться.',
  },
  PARAMETERS_MODE_MISMATCH: {
    title: 'Несоответствие режима импорта',
    description: 'Режим импорта на листе «Параметры» не совпадает с режимом, выбранным на странице загрузки.',
    hint: 'Убедитесь, что выбранный режим импорта совпадает со значением параметра «Режим импорта» в файле.',
  },
  PARAMETERS_KEYS_MISSING: {
    title: 'Отсутствуют обязательные параметры',
    description: (param) => param
      ? `На служебном листе «Параметры» отсутствуют обязательные параметры: ${param}.`
      : 'На служебном листе «Параметры» отсутствуют обязательные параметры конфигурации импорта.',
    hint: 'Восстановите параметры на листе «Параметры» из оригинального шаблона каталога.',
  },
  PARAMETERS_KEY_UNKNOWN: {
    title: 'Неизвестный параметр на листе «Параметры»',
    description: (param) => param
      ? `На листе «Параметры» указан неизвестный параметр: «${param}».`
      : 'На служебном листе «Параметры» обнаружен лишний параметр.',
    hint: 'Удалите посторонние параметры с листа «Параметры» или используйте оригинальный шаблон.',
  },
  PARAMETERS_KEY_INVALID: {
    title: 'Некорректный параметр на листе «Параметры»',
    description: 'Один из параметров на листе «Параметры» пуст, содержит недопустимое значение или дублируется.',
    hint: 'Проверьте названия и значения параметров на листе «Параметры» по образцу актуального шаблона.',
  },
  PARAMETERS_CLEAR_TOKEN_INVALID: {
    title: 'Неверный маркер очистки',
    description: 'В параметре «Маркер очистки» указано недопустимое значение. Ожидается токен «__CLEAR__».',
    hint: 'Укажите точное значение «__CLEAR__» для параметра маркера очистки на листе «Параметры».',
  },
  PARAMETERS_GENERATED_AT_INVALID: {
    title: 'Некорректная дата формирования шаблона',
    description: 'Параметр даты формирования на листе «Параметры» имеет неверный формат даты и времени (ожидается ISO 8601).',
    hint: 'Скачайте новый шаблон каталога с корректной датой формирования.',
  },

  // Sheets and headers
  UNKNOWN_SHEET: {
    title: (param) => param ? `Неизвестный лист «${localizeSheetName(param)}»` : 'Обнаружен неизвестный лист в книге',
    description: (param) => param
      ? `В файле обнаружен неизвестный лист «${localizeSheetName(param)}». Файл импорта должен содержать только стандартные листы каталога.`
      : 'В книге Excel обнаружен лист, не входящий в структуру каталога спецтехники.',
    hint: 'Удалите лишние листы из книги Excel. Допускаются только стандартные листы шаблона.',
  },
  SHEET_HEADER_INVALID: {
    title: (param) => param ? `Неверные заголовки на листе «${localizeSheetName(param)}»` : 'Неверные заголовки колонок',
    description: (param) => param
      ? `Заголовки колонок на листе «${localizeSheetName(param)}» не соответствуют актуальному шаблону. Возможно, колонки удалены, переименованы или нарушен их порядок.`
      : 'Строка заголовков на одном из листов не соответствует формату актуального шаблона.',
    hint: (param) => param
      ? `Сверьте заголовки колонок листа «${localizeSheetName(param)}» с оригинальным шаблоном версии 6.`
      : 'Сверьте заголовки первой строки колонок с оригинальным шаблоном версии 6.',
  },
  FULL_SNAPSHOT_SHEETS_MISSING: {
    title: 'Отсутствуют листы для полной замены каталога',
    description: (param) => {
      if (!param) return 'В режиме полной замены каталога (FULL_SNAPSHOT) файл должен содержать все листы справочников.'
      const sheets = param.split(',').map((s) => `«${localizeSheetName(s.trim())}»`).join(', ')
      return `В режиме полной замены каталога отсутствуют обязательные листы: ${sheets}.`
    },
    hint: 'Добавьте все отсутствующие листы согласно шаблону или используйте режим импорта «Добавление и изменение» (PATCH).',
  },
  MANIFEST_SHEET_MISSING: {
    title: 'Отсутствует лист манифеста устаревшего шаблона',
    description: 'Файл сформирован по устаревшему контракту v1, но лист manifest не найден.',
    hint: 'Используйте актуальный шаблон импорта версии 6.',
  },
  MANIFEST_HEADER_INVALID: {
    title: 'Неверный заголовок листа параметров',
    description: 'Первая строка на листе параметров не содержит обязательные колонки («Параметр», «Значение»).',
    hint: 'Убедитесь, что первая строка листа «Параметры» содержит колонки «Параметр» и «Значение».',
  },

  // File and security
  XLSX_ZIP_INVALID: {
    title: 'Повреждённый файл Excel',
    description: 'Файл не является корректным архивом OpenXML (.xlsx) или был повреждён при сохранении либо передаче.',
    hint: 'Откройте файл в Excel или LibreOffice, сохраните его заново в формате .xlsx и повторите загрузку.',
  },
  XLSX_OPEN_FAILED: {
    title: 'Не удалось открыть книгу Excel',
    description: 'Произошла ошибка при чтении файла. Возможно, структура книги повреждена или файл защищён паролем.',
    hint: 'Убедитесь, что файл открывается на компьютере, не защищён паролем и сохранён в формате .xlsx.',
  },
  XLSX_ACTIVE_CONTENT_FORBIDDEN: {
    title: 'Запрещённое активное содержимое',
    description: 'В файле обнаружены макросы (VBA), элементы ActiveX или внешние подключения, запрещённые политикой безопасности.',
    hint: 'Сохраните книгу в обычном формате «Книга Excel (.xlsx)» без поддержки макросов и удалите любые скрипты.',
  },
  XLSX_FORMULA_FORBIDDEN: {
    title: 'Формулы в ячейках запрещены',
    description: 'В таблице обнаружены формулы Excel. Шаблон импорта принимает только статические текстовые и числовые значения.',
    hint: 'Скопируйте все ячейки таблицы и вставьте их как «Только значения» (Ctrl+Shift+V), затем сохраните файл.',
  },
  CELL_TEXT_TOO_LONG: {
    title: 'Превышена максимальная длина ячейки',
    description: 'Текст в одной из ячеек превышает допустимый предел длины (100 000 символов).',
    hint: 'Сократите длинные текстовые описания и повторите загрузку.',
  },
  XLSX_TOO_MANY_ZIP_ENTRIES: {
    title: 'Слишком много элементов в файле',
    description: 'Структура книги Excel превышает лимиты безопасности по количеству внутренних элементов.',
    hint: 'Удалите из книги лишнее сложное форматирование, скрытые листы и встроенные объекты.',
  },
  XLSX_UNCOMPRESSED_SIZE_EXCEEDED: {
    title: 'Превышен размер распакованных данных',
    description: 'Объём данных книги Excel после распаковки превышает допустимый лимит безопасности.',
    hint: 'Разделите большой файл импорта на несколько частей меньшего объёма.',
  },
  XLSX_COMPRESSION_RATIO_EXCEEDED: {
    title: 'Подозрительный коэффициент сжатия',
    description: 'Файл заблокирован системой безопасности из-за аномально высокого коэффициента сжатия архива.',
    hint: 'Пересохраните файл в Microsoft Excel или разделите данные на несколько файлов.',
  },

  // State & environment
  PREVIEW_STALE: {
    title: 'Предварительный просмотр устарел',
    description: 'Каталог спецтехники был изменён после формирования предварительного просмотра.',
    hint: 'Запустите повторную проверку файла, чтобы обновить сводку изменений перед применением.',
  },
  DESTRUCTIVE_CONFIRMATION_REQUIRED: {
    title: 'Требуется подтверждение удаления данных',
    description: 'Применение импорта приведёт к удалению или архивации значительного количества объектов каталога.',
    hint: 'Введите проверочную фразу в блоке подтверждения применения для выполнения операции.',
  },
  TARGET_WAREHOUSE_INVALID: {
    title: 'Некорректный склад назначения',
    description: 'Указанный склад назначения не существует, неактивен или недоступен для выбранных объявлений.',
    hint: 'Выберите активный склад из выпадающего списка или проверьте идентификатор склада в файле.',
  },
  WAREHOUSE_NOT_FOUND: {
    title: 'Склад не найден',
    description: 'Склад с указанным идентификатором не найден в базе данных.',
    hint: 'Проверьте ID склада в колонке «ID склада» на листе объявлений или выберите склад при настройке импорта.',
  },
  VALIDATION_RUNTIME_ERROR: {
    title: 'Временная ошибка проверки',
    description: 'Во время проверки файла произошёл внутренний сбой сервиса обработки. Повторная попытка будет выполнена автоматически.',
    hint: 'Подождите несколько минут или обновите статус импорта.',
  },
  RETRIES_EXHAUSTED: {
    title: 'Превышено число попыток обработки',
    description: 'Сервис не смог завершить проверку файла после нескольких автоматических попыток.',
    hint: 'Попробуйте запустить импорт повторно или обратитесь в техническую поддержку.',
  },

  // Row-level catalog errors
  MARK_NOT_FOUND: {
    title: 'Марка не найдена',
    description: 'Марка с указанным кодом отсутствует в каталоге и не создаётся в текущем файле.',
    hint: 'Добавьте марку на лист «Марки» или укажите существующий код марки.',
  },
  MODEL_NOT_FOUND: {
    title: 'Модель не найдена',
    description: 'Модель с указанным кодом отсутствует в каталоге и не создаётся в файле.',
    hint: 'Добавьте модель на лист «Модели» или проверьте правильность кода.',
  },
  MODIFICATION_NOT_FOUND: {
    title: 'Модификация не найдена',
    description: 'Модификация с указанным кодом не найдена в каталоге.',
    hint: 'Убедитесь, что модификация заведена на листе «Модификации».',
  },
  TRIM_NOT_FOUND: {
    title: 'Комплектация не найдена',
    description: 'Комплектация с указанным кодом не найдена в каталоге.',
    hint: 'Проверьте код комплектации на листе «Комплектации».',
  },
  TRIM_MODIFICATION_NOT_FOUND: {
    title: 'Модификация комплектации не найдена',
    description: 'Модификация, к которой привязана комплектация, отсутствует в системе.',
    hint: 'Проверьте связь комплектации с кодом модификации.',
  },
  ATTRIBUTE_NOT_FOUND: {
    title: 'Характеристика не найдена',
    description: 'Характеристика с указанным кодом отсутствует в справочнике.',
    hint: 'Добавьте характеристику на лист «Характеристики» или проверьте код.',
  },
  COLOR_INVALID: {
    title: 'Недопустимый цвет',
    description: 'Указанный цвет не найден в справочнике цветов каталога.',
    hint: 'Используйте стандартные цвета с листа «Цвета».',
  },
  CONFLICTING_DUPLICATE: {
    title: 'Конфликтующий дубликат',
    description: 'В файле обнаружено несколько строк с одинаковым кодом, но разными значениями полей.',
    hint: 'Оставьте только одну актуальную версию строки для каждого уникального кода.',
  },
  IDENTICAL_DUPLICATE: {
    title: 'Полный дубликат строки',
    description: 'В файле найдена повторяющаяся строка с абсолютно идентичными данными.',
    hint: 'Удалите дублирующиеся строки из книги Excel.',
  },
  DUPLICATE_LINK: {
    title: 'Повторяющаяся связь',
    description: 'Связь между объектами дублируется в пределах одного листа или каталога.',
    hint: 'Удалите повторяющуюся строку связи.',
  },
  CARD_ATTRIBUTE_LIMIT_EXCEEDED: {
    title: 'Превышен лимит характеристик в карточке',
    description: 'Для категории превышено максимальное количество характеристик, выводимых в карточке товара.',
    hint: 'Уменьшите число характеристик с флагом показа в карточке для данной категории.',
  },
  CATEGORY_GRAPH_INVALID: {
    title: 'Ошибка структуры категорий',
    description: 'Обнаружена циклическая зависимость или недопустимая иерархия в дереве категорий.',
    hint: 'Проверьте связи родительских и дочерних категорий на отсутствие циклов.',
  },
  ATTRIBUTE_OPTION_REQUIRES_SELECT: {
    title: 'Опции допустимы только для списочных характеристик',
    description: 'Варианты значений (опции) могут задаваться только для характеристик с типом SELECT.',
    hint: 'Убедитесь, что характеристика имеет тип SELECT на листе «Характеристики».',
  },
  ATTRIBUTE_MUTATION_BLOCKED: {
    title: 'Изменение характеристики заблокировано',
    description: 'Нельзя изменить тип данных характеристики, для которой уже сохранены значения в каталоге.',
    hint: 'Для изменения типа создайте новую характеристику.',
  },
  IMAGE_FETCH_FAILED: {
    title: 'Не удалось загрузить изображение',
    description: 'Внешний сервер с изображением недоступен или вернул ошибку при скачивании.',
    hint: 'Проверьте доступность URL-адреса изображения в браузере.',
  },
  IMAGE_HOST_INVALID: {
    title: 'Недопустимый хост изображения',
    description: 'Хост в URL изображения не входит в список разрешённых доменов.',
    hint: 'Размещайте изображения на разрешённых CDN или хостингах.',
  },
  IMAGE_SSRF_ADDRESS_BLOCKED: {
    title: 'Заблокированный адрес изображения',
    description: 'URL изображения указывает на локальный или приватный IP-адрес (заблокировано политикой безопасности).',
    hint: 'Используйте публичные ссылки на изображения в интернете.',
  },
  IMAGE_CONTENT_TYPE_INVALID: {
    title: 'Недопустимый формат изображения',
    description: 'Файл по ссылке не является допустимым графическим форматом (поддерживаются JPEG, PNG, WebP).',
    hint: 'Откройте доступ к файлу на Google Drive: «Все, у кого есть ссылка»',
  },
  IMAGE_REDIRECT_INVALID: {
    title: 'Недопустимое перенаправление при скачивании',
    description: 'Ссылка на изображение выполняет перенаправление на неразрешённый адрес.',
    hint: 'Откройте доступ к файлу на Google Drive: «Все, у кого есть ссылка»',
  },
  IMAGE_FETCH_BUDGET_EXCEEDED: {
    title: 'Превышен лимит времени на скачивание фото',
    description: 'Время, отведённое на скачивание фото импорта, истекло.',
    hint: 'Повторите попытку импорта или уменьшите количество новых изображений.',
  },
  PRODUCT_IMAGE_URL_INVALID: {
    title: 'Некорректная ссылка на изображение',
    description: 'Ссылка на изображение не соответствует требованиям безопасности или ведёт на неразрешённый домен.',
    hint: 'Проверьте, что ссылка начинается с https:// и ведёт на Google Drive',
  },
  PRODUCT_IMAGES_LIMIT_EXCEEDED: {
    title: 'Превышен лимит изображений',
    description: (param) => param ? `Число ссылок на изображения превышает лимит. ${param}` : 'Для объявления указано больше 50 ссылок на изображения.',
    hint: 'Оставьте не больше 50 ссылок',
  },
  PRODUCT_IMAGE_CLEAR_MIXED: {
    title: 'Недопустимое сочетание маркера очистки',
    description: 'Маркер «Очистить» не может сочетаться со ссылками на изображения.',
    hint: 'Укажите либо только ссылки на изображения, либо только маркер «Очистить».',
  },
  PRODUCT_IMAGES_ALL_FAILED: {
    title: 'Не удалось загрузить изображения объявления',
    description: 'Ни одно из указанных изображений объявления не удалось загрузить.',
    hint: 'Откройте доступ к файлу на Google Drive: «Все, у кого есть ссылка»',
  },
  CATEGORY_IMAGE_MULTIPLE: {
    title: 'Несколько ссылок на картинку категории',
    description: 'Для категории допускается одна ссылка на изображение.',
    hint: 'Укажите только одну ссылку на изображение для категории.',
  },
  IMAGE_SIZE_EXCEEDED: {

    title: 'Превышен размер изображения',
    description: 'Размер скачиваемого изображения превышает допустимый предел (10 МБ).',
    hint: 'Сожмите изображение перед добавлением ссылки в шаблон.',
  },
  IMAGE_PIXEL_LIMIT_EXCEEDED: {
    title: 'Слишком большое разрешение изображения',
    description: 'Разрешение изображения превышает допустимые геометрические размеры.',
    hint: 'Уменьшите разрешение картинки (рекомендуется до 4000x4000 пикселей).',
  },
  IMAGE_DECODE_FAILED: {
    title: 'Ошибка декодирования изображения',
    description: 'Файл изображения повреждён и не может быть обработан графическим модулем.',
    hint: 'Проверьте корректность файла изображения и пересохраните его.',
  },
  MARK_INVALID: {
    title: 'Некорректная марка',
    description: 'Данные марки не прошли валидацию.',
    hint: 'Проверьте обязательные поля (код, название) на листе «Марки».',
  },
  MODEL_INVALID: {
    title: 'Некорректная модель',
    description: 'Данные модели не прошли валидацию.',
    hint: 'Проверьте обязательные поля и код марки на листе «Модели».',
  },
  MODIFICATION_INVALID: {
    title: 'Некорректная модификация',
    description: 'Данные модификации не прошли валидацию.',
    hint: 'Проверьте обязательные поля и диапазон лет выпуска на листе «Модификации».',
  },
  TRIM_INVALID: {
    title: 'Некорректная комплектация',
    description: 'Данные комплектации не прошли валидацию.',
    hint: 'Проверьте обязательные поля на листе «Комплектации».',
  },
  CATEGORY_INVALID: {
    title: 'Некорректная категория',
    description: 'Данные категории не прошли валидацию.',
    hint: 'Проверьте обязательные поля на листе «Категории».',
  },
  ATTRIBUTE_INVALID: {
    title: 'Некорректная характеристика',
    description: 'Данные характеристики не прошли валидацию.',
    hint: 'Проверьте поля на листе «Характеристики».',
  },
  ATTRIBUTE_OPTION_INVALID: {
    title: 'Некорректный вариант характеристики',
    description: 'Данные варианта характеристики не прошли валидацию.',
    hint: 'Проверьте поля на листе «Варианты характеристик».',
  },
  PRODUCT_INVALID: {
    title: 'Некорректное объявление',
    description: 'Данные объявления не прошли валидацию.',
    hint: 'Проверьте обязательные поля на листе «Объявления».',
  },
  REQUIRED_FIELD_MISSING: {
    title: 'Обязательное поле не заполнено',
    description: (_param, detail) => detail && /[А-Яа-яЁё]/.test(detail) ? detail : 'В файле не заполнено обязательное поле.',
    hint: (_param, detail) => {
      if (detail) {
        const fullMatch = detail.match(/Лист\s*[«"]([^»"]+)[»"],\s*строка\s*(\d+).*?(?:поле|колонк[ау])\s*[«"]([^»"]+)[»"]/i)
        if (fullMatch) {
          const [, sheet, row, col] = fullMatch
          return `Заполните колонку «${col}» на листе «${localizeSheetName(sheet)}», строка ${row}`
        }
      }
      return 'Заполните обязательную колонку на указанном листе.'
    },
  },
  UNIQUE_CONFLICT: {
    title: 'Конфликт уникальности записи',
    description: (_param, detail) => detail && /[А-Яа-яЁё]/.test(detail) ? detail : 'Запись с такими параметрами уже существует.',
    hint: 'Запись с таким названием уже существует — используйте её код или измените название',
  },
  DEPENDENCY_NOT_APPLIED: {
    title: 'Связанная запись не применена',
    description: (_param, detail) => detail && /[А-Яа-яЁё]/.test(detail) ? detail : 'Связанная запись не создана — см. ошибку по ней выше.',
    hint: 'Сначала исправьте ошибку в связанной записи',
  },
  VALUE_OUT_OF_RANGE: {
    title: 'Недопустимое значение',
    description: (_param, detail) => detail && /[А-Яа-яЁё]/.test(detail) ? detail : 'Значение поля выходит за допустимые границы.',
    hint: 'Проверьте допустимые диапазоны и форматы значений.',
  },
  AGGREGATE_APPLY_CONFLICT: {
    title: 'Конфликт применения изменений',
    description: (_param, detail) => detail && /[А-Яа-яЁё]/.test(detail) ? detail : 'Агрегат не применён из-за конфликта зависимостей или уникальности.',
    hint: 'Исправьте связанные записи или параметры уникальности в файле каталога.',
  },
  APPLY_FAILED: {
    title: 'Ошибка применения импорта',
    description: (_param, detail) => detail && /[А-Яа-яЁё]/.test(detail) ? detail : 'Не удалось применить каталог спецтехники из-за внутренней ошибки.',
    hint: 'Внутренняя ошибка при загрузке. Обратитесь в поддержку, указав номер задачи импорта',
  },
  CODE_INVALID: {
    title: 'Недопустимый код объекта',
    description: (param, detail) => detail && /[А-Яа-яЁё]/.test(detail)
      ? detail
      : (param ? `Код «${param}» содержит недопустимые символы или не соответствует формату.` : 'Код объекта содержит недопустимые символы.'),
    hint: 'Убедитесь, что файл соответствует актуальному шаблону v6, или скачайте новый шаблон каталога.',
  },
  NORMALIZED_ARTIFACT_INVALID: {
    title: 'Некорректный артефакт импорта',
    description: (_param, detail) => detail && /[А-Яа-яЁё]/.test(detail)
      ? detail
      : 'Файл или промежуточные данные импорта не соответствуют требуемому формату.',
    hint: 'Убедитесь, что файл соответствует актуальному шаблону v6, или скачайте новый шаблон каталога.',
  },
}

export function localizeImportError(
  code: string | null | undefined,
  detail?: string | null,
  context?: ImportIssueContext,
): LocalizedImportError {
  const rawCode = (code?.trim() || '').trim()
  const rawDetail = (detail?.trim() || '').trim()

  // If both code and detail are empty
  if (!rawCode && !rawDetail) {
    return {
      title: 'Ошибка проверки импорта',
      description: 'Не удалось проверить файл. Пожалуйста, попробуйте снова.',
      hint: 'Скачайте актуальный шаблон каталога v6 и заполните данные заново.',
      code: undefined,
    }
  }

  // Determine effective code string
  const sourceString = rawCode || rawDetail
  let baseCode = sourceString
  let param: string | undefined

  const colonIdx = sourceString.indexOf(':')
  if (colonIdx !== -1) {
    baseCode = sourceString.slice(0, colonIdx).trim()
    param = sourceString.slice(colonIdx + 1).trim()
  } else if (rawDetail && rawDetail.includes(':') && rawDetail.startsWith(baseCode)) {
    const detailColon = rawDetail.indexOf(':')
    param = rawDetail.slice(detailColon + 1).trim()
  }

  if (baseCode.startsWith('IMAGE_HTTP_STATUS_')) {
    const status = baseCode.replace('IMAGE_HTTP_STATUS_', '')
    return {
      title: 'Ошибка доступа к изображению',
      description: rawDetail && /[А-Яа-яЁё]/.test(rawDetail) && !rawDetail.startsWith(baseCode)
        ? rawDetail
        : `Сервер вернул статус HTTP ${status} при попытке скачать файл изображения.`,
      hint: 'Откройте доступ к файлу на Google Drive: «Все, у кого есть ссылка»',
      code: baseCode,
    }
  }

  const def = ERROR_DEFINITIONS[baseCode]
  if (def) {
    const title = typeof def.title === 'function' ? def.title(param) : def.title
    let description = typeof def.description === 'function' ? def.description(param, rawDetail || undefined) : def.description

    // If rawDetail is descriptive Russian text and not identical to baseCode or sourceString
    if (rawDetail && rawDetail !== rawCode && !rawDetail.startsWith(baseCode) && /[А-Яа-яЁё]/.test(rawDetail)) {
      description = rawDetail
    }

    let hint = typeof def.hint === 'function' ? def.hint(param, rawDetail || undefined) : def.hint
    if (baseCode === 'REQUIRED_FIELD_MISSING' && context) {
      if (context.columnName && context.sheetCode && context.rowNumber) {
        hint = `Заполните колонку «${context.columnName}» на листе «${localizeSheetName(context.sheetCode)}», строка ${context.rowNumber}`
      } else if (context.sheetCode && context.rowNumber) {
        hint = `Заполните обязательную колонку на листе «${localizeSheetName(context.sheetCode)}», строка ${context.rowNumber}`
      } else if (context.columnName && context.sheetCode) {
        hint = `Заполните колонку «${context.columnName}» на листе «${localizeSheetName(context.sheetCode)}»`
      } else if (context.columnName) {
        hint = `Заполните колонку «${context.columnName}» на указанном листе.`
      } else if (context.sheetCode) {
        hint = `Заполните обязательную колонку на листе «${localizeSheetName(context.sheetCode)}».`
      }
    }

    return {
      title,
      description,
      hint,
      code: baseCode,
    }
  }

  // Fallback for unknown codes
  const hasRussian = rawDetail && /[А-Яа-яЁё]/.test(rawDetail)
  const isDetailSameAsCode = rawDetail === rawCode || rawDetail === baseCode
  const isTemplate = isTemplateErrorCode(baseCode)

  return {
    title: hasRussian && !isDetailSameAsCode && rawDetail.length < 80
      ? rawDetail
      : 'Ошибка валидации импорта',
    description: hasRussian && !isDetailSameAsCode
      ? rawDetail
      : (rawDetail && !isDetailSameAsCode
        ? `${rawDetail} (код: ${baseCode})`
        : `Произошла ошибка при обработке книги Excel (код: ${baseCode}). Проверьте структуру и данные файла.`),
    hint: isTemplate
      ? 'Убедитесь, что файл соответствует актуальному шаблону v6, или скачайте новый шаблон каталога.'
      : 'Проверьте корректность данных в файле каталога.',
    code: baseCode,
  }
}

export function localizeImportIssue(
  code: string,
  message: string,
  context?: ImportIssueContext,
): { message: string; hint?: string } {
  const normalizedCode = (code?.trim() || '').trim()
  const rawMessage = (message?.trim() || '').trim()

  const localized = localizeImportError(normalizedCode, rawMessage, context)

  const isMessageCode = !rawMessage || rawMessage === normalizedCode || rawMessage.toUpperCase() === normalizedCode.toUpperCase()

  if (isMessageCode) {
    return {
      message: localized.description,
      hint: localized.hint,
    }
  }

  return {
    message: rawMessage,
    hint: localized.hint,
  }
}
