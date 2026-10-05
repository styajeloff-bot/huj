import type { Component } from 'vue'
import {
  ClipboardDocumentListIcon, UsersIcon, BuildingOffice2Icon, ChartBarIcon,
  ArrowUpTrayIcon, BuildingStorefrontIcon, ArrowsRightLeftIcon, LifebuoyIcon,
  HomeModernIcon, ShieldCheckIcon, UserCircleIcon,
  UserGroupIcon, TruckIcon, DocumentTextIcon, DocumentCheckIcon,
  PresentationChartLineIcon, ReceiptPercentIcon,
  RectangleStackIcon,
} from '@heroicons/vue/24/outline'

export type BusinessRole = 'dealer' | 'leasing_company' | 'distributor' | 'carcraft_employee'

/** Predicate gate against the auth store (kept loose to avoid a store import cycle). */
export interface WorkspaceAuthLike {
  isCarCraftEmployee: boolean
  isCompanyAdmin: boolean
  isCompanyManager: boolean
  canViewApplications: boolean
  sectionAccess?: Record<string, boolean> | null
}

export interface WorkspaceMenuItem {
  /** Stable key shared with the backend visibility catalog. */
  key: string
  label: string
  to: string
  icon: Component
  /** Whether carcraft_employee can configure this section for the role. */
  configurable: boolean
  /** Optional visibility gate (e.g. only company admins/managers). */
  gate?: (auth: WorkspaceAuthLike) => boolean
}

const employeesItem = (configurable: boolean): WorkspaceMenuItem => ({
  key: 'employees',
  label: 'Сотрудники',
  to: '/workspace/employees',
  icon: UserGroupIcon,
  configurable,
  gate: (a) => {
    if (!a.isCarCraftEmployee && a.sectionAccess?.employees === false) return false
    return a.isCarCraftEmployee || a.isCompanyAdmin || a.isCompanyManager
  },
})
const profileItem: WorkspaceMenuItem = {
  key: 'profile',
  label: 'Профиль',
  to: '/workspace/profile',
  icon: UserCircleIcon,
  configurable: false,
}

const monetizationGate = (a: WorkspaceAuthLike): boolean => {
  if (a.isCarCraftEmployee) return true
  if (a.sectionAccess) {
    if (a.sectionAccess.monetization_income === false && a.sectionAccess.monetization_expense === false) return false
    if (a.sectionAccess.monetization === false) return false
  }
  return true
}

export const WORKSPACE_MENU: Record<BusinessRole, WorkspaceMenuItem[]> = {
  carcraft_employee: [
    { key: 'applications', label: 'Распределение заявок', to: '/workspace/applications', icon: ClipboardDocumentListIcon, configurable: false },
    { key: 'users', label: 'Пользователи', to: '/workspace/users', icon: UsersIcon, configurable: false },
    { key: 'companies', label: 'Компании', to: '/workspace/companies', icon: BuildingOffice2Icon, configurable: false },
    { key: 'stats', label: 'Статистика', to: '/workspace/stats', icon: ChartBarIcon, configurable: false },
    { key: 'questionnaire_settings', label: 'Настройки анкет', to: '/workspace/questionnaire-settings', icon: DocumentTextIcon, configurable: false },
    { key: 'calculator_rates', label: 'Ставки калькулятора', to: '/workspace/calculator-rates', icon: ReceiptPercentIcon, configurable: false },
    { key: 'special_equipment_import', label: 'Импорт спецтехники', to: '/workspace/special-equipment-import', icon: ArrowUpTrayIcon, configurable: true },
    { key: 'special_equipment_catalog', label: 'Управление каталогом', to: '/workspace/special-equipment-catalog', icon: RectangleStackIcon, configurable: true },
    { key: 'warehouses', label: 'Склады', to: '/workspace/warehouses', icon: BuildingStorefrontIcon, configurable: false },
    { key: 'storefronts', label: 'Витрины', to: '/workspace/storefronts', icon: BuildingStorefrontIcon, configurable: false },
    { key: 'exchange_import', label: 'Биржа ТС', to: '/workspace/exchange-import', icon: ArrowsRightLeftIcon, configurable: false },
    { key: 'support', label: 'Программы стимулирования', to: '/workspace/support', icon: LifebuoyIcon, configurable: false },
    { key: 'monetization', label: 'Условия монетизации', to: '/workspace/monetization', icon: ReceiptPercentIcon, configurable: true, gate: monetizationGate },
    { key: 'document_registry', label: 'Справочник документов', to: '/workspace/document-registry', icon: DocumentTextIcon, configurable: true },
    { key: 'featured', label: 'Главная страница', to: '/workspace/featured', icon: HomeModernIcon, configurable: false },
    { key: 'security', label: 'Безопасность', to: '/workspace/security', icon: ShieldCheckIcon, configurable: false },
    employeesItem(false),
  ],
  dealer: [
    { key: 'applications', label: 'Мои заявки', to: '/workspace/applications', icon: ClipboardDocumentListIcon, configurable: true, gate: (a) => a.canViewApplications },
    { key: 'clients', label: 'Мои клиенты', to: '/workspace/clients', icon: UserGroupIcon, configurable: true },
    { key: 'inventory', label: 'Склады', to: '/workspace/warehouses', icon: BuildingStorefrontIcon, configurable: true },
    { key: 'reports', label: 'Отчеты', to: '/workspace/reports', icon: ChartBarIcon, configurable: true },
    {
      key: 'distributor_analytics',
      label: 'Аналитика',
      to: '/workspace/distributor-analytics',
      icon: PresentationChartLineIcon,
      configurable: true,
      gate: (a) => a.canViewApplications,
    },
    { key: 'exchange', label: 'Биржа ТС', to: '/workspace/exchange', icon: ArrowsRightLeftIcon, configurable: true },
    { key: 'support', label: 'Программы стимулирования', to: '/workspace/support', icon: LifebuoyIcon, configurable: true },
    { key: 'monetization', label: 'Условия монетизации', to: '/workspace/monetization', icon: ReceiptPercentIcon, configurable: true, gate: monetizationGate },
    { key: 'document_registry', label: 'Справочник документов', to: '/workspace/document-registry', icon: DocumentTextIcon, configurable: true },
    profileItem,
    employeesItem(true),
  ],
  distributor: [
    { key: 'applications', label: 'Мои заявки', to: '/workspace/applications', icon: ClipboardDocumentListIcon, configurable: true, gate: (a) => a.canViewApplications },
    { key: 'exchange', label: 'Биржа ТС', to: '/workspace/exchange', icon: ArrowsRightLeftIcon, configurable: true, gate: a => a.canViewApplications },
    { key: 'warehouses', label: 'Склады', to: '/workspace/warehouses', icon: BuildingStorefrontIcon, configurable: true },
    { key: 'distributor_analytics', label: 'Аналитика', to: '/workspace/distributor-analytics', icon: PresentationChartLineIcon, configurable: true },
    { key: 'dealers', label: 'Дилеры', to: '/workspace/dealers', icon: TruckIcon, configurable: true },
    { key: 'companies', label: 'Компании', to: '/workspace/companies', icon: BuildingOffice2Icon, configurable: true },
    { key: 'support', label: 'Программы стимулирования', to: '/workspace/support', icon: LifebuoyIcon, configurable: true },
    { key: 'monetization', label: 'Условия монетизации', to: '/workspace/monetization', icon: ReceiptPercentIcon, configurable: true, gate: monetizationGate },
    { key: 'document_registry', label: 'Справочник документов', to: '/workspace/document-registry', icon: DocumentTextIcon, configurable: true },
    profileItem,
    employeesItem(true),
  ],
  leasing_company: [
    { key: 'leasing_applications', label: 'Заявки на лизинг', to: '/workspace/leasing-applications', icon: ClipboardDocumentListIcon, configurable: true, gate: (a) => a.canViewApplications },
    { key: 'documents', label: 'Документы клиентов', to: '/workspace/documents', icon: DocumentTextIcon, configurable: true },
    { key: 'document_requirements', label: 'Требования к документам', to: '/workspace/document-requirements', icon: DocumentCheckIcon, configurable: true },
    { key: 'support', label: 'Программы стимулирования', to: '/workspace/support', icon: LifebuoyIcon, configurable: true },
    { key: 'monetization', label: 'Условия монетизации', to: '/workspace/monetization', icon: ReceiptPercentIcon, configurable: true, gate: monetizationGate },
    { key: 'document_registry', label: 'Справочник документов', to: '/workspace/document-registry', icon: DocumentTextIcon, configurable: true },
    { key: 'exchange', label: 'Биржа ТС', to: '/workspace/exchange', icon: ArrowsRightLeftIcon, configurable: true },
    { key: 'leasing_analytics', label: 'Аналитика', to: '/workspace/leasing-analytics', icon: PresentationChartLineIcon, configurable: true },
    { key: 'security', label: 'Безопасность', to: '/workspace/security', icon: ShieldCheckIcon, configurable: true },
    profileItem,
    employeesItem(true),
  ],
}

export function isBusinessRoleName(role: string | null | undefined): role is BusinessRole {
  return role === 'dealer' || role === 'leasing_company' || role === 'distributor' || role === 'carcraft_employee'
}
