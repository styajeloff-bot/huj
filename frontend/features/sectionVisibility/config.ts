import type {
  VisibilityMatrix,
  VisibilityScope,
  StorefrontVisibilityScope,
  GlobalVisibilityScope,
  WorkspaceVisibilityScope,
} from './types'

export type {
  GlobalVisibilityScope,
  StorefrontVisibilityScope,
  VisibilityScope,
  WorkspaceVisibilityScope,
} from './types'
export {
  isStorefrontVisibilityScope,
  isVisibilityScope,
  isWorkspaceVisibilityScope,
} from './types'

export interface SectionVisibilityCatalogItem {
  key: string
  label: string
  defaultVisible: boolean
}

export const SECTION_VISIBILITY_CATALOG = {
  public: [
    { key: 'about', label: 'О нас', defaultVisible: true },
    {
      key: 'special_equipment_catalog',
      label: 'Каталог транспортных средств и специальной техники',
      defaultVisible: true,
    },
  ],
  carcraft_employee: [
    {
      key: 'special_equipment_import',
      label: 'Импорт спецтехники',
      defaultVisible: true,
    },
    {
      key: 'special_equipment_catalog',
      label: 'Управление каталогом спецтехники',
      defaultVisible: true,
    },
    { key: 'monetization', label: 'Условия монетизации', defaultVisible: true },
    { key: 'document_registry', label: 'Справочник документов', defaultVisible: true },
  ],
  leasing_company: [
    { key: 'leasing_applications', label: 'Заявки на лизинг', defaultVisible: true },
    { key: 'documents', label: 'Документы клиентов', defaultVisible: true },
    { key: 'document_requirements', label: 'Требования к документам', defaultVisible: true },
    { key: 'support', label: 'Программы стимулирования', defaultVisible: true },
    { key: 'monetization', label: 'Условия монетизации', defaultVisible: true },
    { key: 'document_registry', label: 'Справочник документов', defaultVisible: true },
    { key: 'exchange', label: 'Биржа ТС', defaultVisible: true },
    { key: 'leasing_analytics', label: 'Аналитика', defaultVisible: true },
    { key: 'security', label: 'Безопасность', defaultVisible: true },
    { key: 'employees', label: 'Сотрудники', defaultVisible: true },
  ],
  dealer: [
    { key: 'applications', label: 'Мои заявки', defaultVisible: true },
    { key: 'clients', label: 'Мои клиенты', defaultVisible: true },
    { key: 'inventory', label: 'Склады', defaultVisible: true },
    { key: 'reports', label: 'Отчеты', defaultVisible: true },
    { key: 'distributor_analytics', label: 'Аналитика', defaultVisible: true },
    { key: 'exchange', label: 'Биржа ТС', defaultVisible: true },
    { key: 'support', label: 'Программы стимулирования', defaultVisible: true },
    { key: 'monetization', label: 'Условия монетизации', defaultVisible: true },
    { key: 'document_registry', label: 'Справочник документов', defaultVisible: true },
    { key: 'employees', label: 'Сотрудники', defaultVisible: true },
  ],
  distributor: [
    { key: 'applications', label: 'Мои заявки', defaultVisible: true },
    { key: 'exchange', label: 'Биржа ТС', defaultVisible: true },
    { key: 'warehouses', label: 'Склады', defaultVisible: true },
    { key: 'distributor_analytics', label: 'Аналитика', defaultVisible: true },
    { key: 'dealers', label: 'Дилеры', defaultVisible: true },
    { key: 'companies', label: 'Компании', defaultVisible: true },
    { key: 'support', label: 'Программы стимулирования', defaultVisible: true },
    { key: 'monetization', label: 'Условия монетизации', defaultVisible: true },
    { key: 'document_registry', label: 'Справочник документов', defaultVisible: true },
    { key: 'employees', label: 'Сотрудники', defaultVisible: true },
  ],
} as const satisfies Record<VisibilityScope, readonly SectionVisibilityCatalogItem[]>

const defaultsForScope = (scope: VisibilityScope): VisibilityMatrix => Object.fromEntries(
  SECTION_VISIBILITY_CATALOG[scope].map(section => [section.key, section.defaultVisible]),
)

export const DEFAULT_SECTION_VISIBILITY: Record<VisibilityScope, VisibilityMatrix> = {
  public: defaultsForScope('public'),
  carcraft_employee: defaultsForScope('carcraft_employee'),
  leasing_company: defaultsForScope('leasing_company'),
  dealer: defaultsForScope('dealer'),
  distributor: defaultsForScope('distributor'),
}

export const WORKSPACE_VISIBILITY_SCOPES: readonly WorkspaceVisibilityScope[] = [
  'carcraft_employee',
  'leasing_company',
  'dealer',
  'distributor',
]

export const STOREFRONT_VISIBILITY_SCOPES: readonly StorefrontVisibilityScope[] = [
  'public',
  'leasing_company',
  'dealer',
  'distributor',
]

export const GLOBAL_VISIBILITY_SCOPES: readonly GlobalVisibilityScope[] = [
  'carcraft_employee',
]
