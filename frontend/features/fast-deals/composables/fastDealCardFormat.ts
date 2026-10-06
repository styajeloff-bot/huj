import type { UUID } from '~/types/ids'
import type { LookupItem } from '../api/fastDealsApi'
import type {
  FastDealCard,
  FastDealFileKind,
  FastDealParty,
  FastDealSource,
  FastDealStatus,
  FastDealVehicle,
  LcApplicationStatus,
  MoneyString,
} from '../types'
import { FAST_DEAL_STATUS_LABELS, fastDealStatusClass } from '../status'

/*
 * Presentation helpers of the fast deal card. Money is an exact decimal STRING end to end:
 * these helpers only format it for display, compare it as text or do kopeck arithmetic on
 * BigInt. Nothing here converts money to a JS number.
 */

const NBSP = ' '

// ------------------------------------------------------------------------------ decimals

interface DecimalParts {
  negative: boolean
  integer: string
  fraction: string
}

function splitDecimal(value: string): DecimalParts | null {
  const match = /^([+-])?(\d+)(?:\.(\d+))?$/.exec(value.trim())
  if (!match) return null
  return {
    negative: match[1] === '-',
    integer: match[2].replace(/^0+(?=\d)/, ''),
    fraction: match[3] ?? '',
  }
}

function groupDigits(integer: string): string {
  return integer.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP)
}

/** `1250000.5` -> `1 250 000,50 ₽`; anything that is not a decimal string -> `—`. */
export function formatMoney(value: MoneyString | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const parts = splitDecimal(String(value))
  if (!parts) return '—'
  const fraction = `${parts.fraction}00`.slice(0, 2)
  return `${parts.negative ? '−' : ''}${groupDigits(parts.integer)},${fraction}${NBSP}₽`
}

/** `20.50` -> `20,5 %`. */
export function formatPercent(value: MoneyString | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const parts = splitDecimal(String(value))
  if (!parts) return '—'
  const fraction = parts.fraction.replace(/0+$/, '')
  return `${parts.negative ? '−' : ''}${parts.integer}${fraction ? `,${fraction}` : ''}${NBSP}%`
}

/** Kopecks as BigInt; fractions beyond two digits are cut (display arithmetic only). */
export function toMinor(value: MoneyString | null | undefined): bigint | null {
  if (value === null || value === undefined || value === '') return null
  const parts = splitDecimal(String(value))
  if (!parts) return null
  const minor = BigInt(`${parts.integer}${`${parts.fraction}00`.slice(0, 2)}`)
  return parts.negative ? -minor : minor
}

export function fromMinor(minor: bigint): MoneyString {
  const zero = BigInt(0)
  const negative = minor < zero
  const digits = (negative ? -minor : minor).toString().padStart(3, '0')
  return `${negative ? '-' : ''}${digits.slice(0, -2)}.${digits.slice(-2)}`
}

/** `a - b` in kopecks; `null` when either side is not a decimal string. */
export function subtractMoney(a: MoneyString | null | undefined, b: MoneyString | null | undefined): MoneyString | null {
  const left = toMinor(a)
  const right = toMinor(b)
  return left === null || right === null ? null : fromMinor(left - right)
}

/** `total * percent / 100` rounded half up to kopecks, for a read-only hint next to a percent input. */
export function percentOfMoney(total: MoneyString | null | undefined, percent: MoneyString | null | undefined): MoneyString | null {
  const base = toMinor(total)
  const parts = percent === null || percent === undefined ? null : splitDecimal(percent)
  if (base === null || !parts) return null
  const scaled = BigInt(`${parts.integer}${`${parts.fraction}00`.slice(0, 2)}`)
  const zero = BigInt(0)
  const divisor = BigInt(10000)
  const product = base * scaled
  const half = divisor / BigInt(2)
  const rounded = product >= zero ? (product + half) / divisor : (product - half) / divisor
  return fromMinor(rounded)
}

function trimmedDecimal(value: string): string {
  const parts = splitDecimal(value)
  if (!parts) return value.trim()
  const fraction = parts.fraction.replace(/0+$/, '')
  const isZero = /^0*$/.test(parts.integer) && !fraction
  return `${parts.negative && !isZero ? '-' : ''}${parts.integer}${fraction ? `.${fraction}` : ''}`
}

/** Numeric equality of two decimal strings (`1.50` equals `1.5`); two empty values are equal. */
export function sameDecimal(a: MoneyString | null | undefined, b: MoneyString | null | undefined): boolean {
  const left = a === null || a === undefined || a === '' ? null : trimmedDecimal(String(a))
  const right = b === null || b === undefined || b === '' ? null : trimmedDecimal(String(b))
  return left === right
}

/** True for a strictly positive decimal string. */
export function isPositiveMoney(value: MoneyString | null | undefined): boolean {
  const minor = toMinor(value)
  return minor !== null && minor > BigInt(0)
}

// ---------------------------------------------------------------------------- user input

/** Canonical `123.45` from `1 234,5`; `null` when the text is not an amount with up to 2 decimals. */
export function parseMoneyInput(raw: string | null | undefined): MoneyString | null {
  const cleaned = (raw ?? '').replace(/[\s ₽]/g, '').replace(',', '.')
  if (!/^\d{1,13}(\.\d{1,2})?$/.test(cleaned)) return null
  const [integer, fraction = ''] = cleaned.split('.')
  return `${integer.replace(/^0+(?=\d)/, '')}.${`${fraction}00`.slice(0, 2)}`
}

/** Canonical percent (`20.5`) with up to 2 decimals, at most 100. */
export function parsePercentInput(raw: string | null | undefined): MoneyString | null {
  const cleaned = (raw ?? '').replace(/[\s %]/g, '').replace(',', '.')
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(cleaned)) return null
  const [integer, fraction = ''] = cleaned.split('.')
  const whole = integer.replace(/^0+(?=\d)/, '')
  const overHundred = whole.length > 3 || (whole.length === 3 && !(whole === '100' && /^0*$/.test(fraction)))
  return overHundred ? null : `${whole}.${`${fraction}00`.slice(0, 2)}`
}

/** Plain-text form of a decimal string for an input (`1250000.00` -> `1250000.00`, null -> ``). */
export function moneyToInput(value: MoneyString | null | undefined): string {
  return value === null || value === undefined ? '' : String(value)
}

export function parseTermInput(raw: string | number | null | undefined): number | null {
  const text = String(raw ?? '').trim()
  if (!/^\d{1,3}$/.test(text)) return null
  return Number.parseInt(text, 10)
}

// ------------------------------------------------------------------------------- dates

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' })
}

export function formatFileSize(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return '—'
  if (bytes < 1024) return `${bytes}${NBSP}Б`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1).replace('.', ',')}${NBSP}КБ`
  return `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')}${NBSP}МБ`
}

// ------------------------------------------------------------------------------- labels

// The same wording and colors as the list: `status.ts` owns the dictionary of deal statuses.
export const dealStatusLabels: Record<FastDealStatus, string> = FAST_DEAL_STATUS_LABELS

export const dealStatusLabel = (status: string): string => dealStatusLabels[status as FastDealStatus] ?? status
export const dealStatusTone = (status: string): string => fastDealStatusClass(status)

export const lcStatusLabels: Record<LcApplicationStatus, string> = {
  pending_review: 'Ожидает КП',
  offer_sent: 'КП отправлено',
  selected_by_dealer: 'Выбрана дилером',
  confirmed: 'Подтвердила сделку',
  rejected: 'Отказала',
  closed_not_selected: 'Не выбрана',
}

export const lcStatusTones: Record<LcApplicationStatus, string> = {
  pending_review: 'bg-gray-100 text-gray-700',
  offer_sent: 'bg-blue-100 text-blue-800',
  selected_by_dealer: 'bg-indigo-100 text-indigo-800',
  confirmed: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  closed_not_selected: 'bg-slate-200 text-slate-700',
}

export const lcStatusLabel = (status: string): string => lcStatusLabels[status as LcApplicationStatus] ?? status
export const lcStatusTone = (status: string): string => lcStatusTones[status as LcApplicationStatus] ?? 'bg-gray-100 text-gray-700'

export const sourceLabels: Record<FastDealSource, string> = {
  dealer_to_leasing: 'Дилер → лизинговые компании',
  leasing_to_dealer: 'Лизинговая компания → дилер',
}
export const sourceLabel = (source: string): string => sourceLabels[source as FastDealSource] ?? source

export const partyLabels: Record<FastDealParty, string> = {
  initiator: 'Инициатор сделки',
  leasing: 'Лизинговая компания',
  dealer: 'Дилер',
  distributor: 'Дистрибьютор',
  platform: 'Администратор платформы',
}
export const partyLabel = (party: string): string => partyLabels[party as FastDealParty] ?? party

export const fileKindLabels: Record<FastDealFileKind, string> = {
  deal_main: 'Основной документ',
  deal_additional: 'Дополнительный документ',
  lc_offer_pdf: 'PDF коммерческого предложения',
  vehicle_offer: 'КП по технике',
}
export const fileKindLabel = (kind: string): string => fileKindLabels[kind as FastDealFileKind] ?? kind

export const supportStatusLabels: Record<string, string> = {
  requested: 'Запрошено',
  pre_approved: 'Предварительно согласовано',
  approved: 'Согласовано',
  cancelled: 'Отклонено',
}
export const supportStatusLabel = (status: string): string => supportStatusLabels[status] ?? status

export const supportStatusTones: Record<string, string> = {
  requested: 'bg-blue-100 text-blue-800',
  pre_approved: 'bg-amber-100 text-amber-800',
  approved: 'bg-green-100 text-green-800',
  cancelled: 'bg-red-100 text-red-800',
}

export const historyEventLabels: Record<string, string> = {
  created: 'Сделка создана',
  status_changed: 'Статус изменён',
  vehicle_added: 'Добавлена техника',
  vehicle_changed: 'Изменена техника',
  vehicle_removed: 'Удалена техника',
  vehicle_replaced: 'Заменена техника',
  terms_changed: 'Изменены условия лизинга',
  sent: 'Сделка отправлена',
  lc_invited: 'Приглашена лизинговая компания',
  offer_sent: 'Отправлено КП',
  offer_selected: 'Выбрано КП',
  selection_withdrawn: 'Выбор КП снят',
  lc_rejected: 'Отказ лизинговой компании',
  reset: 'Сделка возвращена в черновик',
  reopened: 'Отклонённая сделка возвращена в работу',
  split: 'Сделка разделена по дилерам',
  changes_sent: 'Изменения отправлены лизинговой компании',
  changes_accepted: 'Изменения приняты',
  changes_rejected: 'Изменения отклонены',
  confirmed: 'Сделка подтверждена',
  rejected: 'Сделка отклонена',
  cancelled: 'Сделка отменена',
  assignees_changed: 'Изменены ответственные',
  support_applied: 'Применена программа поддержки',
  support_removed: 'Снята программа поддержки',
  support_requested: 'Запрошена дополнительная поддержка',
  support_decided: 'Решение по запросу поддержки',
  support_accounted: 'Поддержка учтена в цене',
  file_uploaded: 'Загружены файлы',
}
export const historyEventLabel = (event: string): string => historyEventLabels[event] ?? event

export const vehicleFieldLabels: Record<string, string> = {
  mark_name: 'Марка',
  model_name: 'Модель',
  modification_name: 'Модификация',
  trim_name: 'Комплектация',
  body_color_name: 'Цвет',
  vin: 'VIN',
  base_price: 'Базовая цена',
  adjustment_type: 'Тип корректировки',
  adjustment_amount: 'Размер корректировки',
  support_amount: 'Поддержка',
  options_amount: 'Сумма опций',
  final_price: 'Итоговая цена',
  equipments: 'Оборудование',
  services: 'Услуги',
  purposes: 'Назначения',
  regions: 'Регионы',
  item_status: 'Состояние позиции',
  status: 'Статус',
  lease_term_months: 'Срок лизинга, мес.',
  down_payment: 'Аванс',
  down_payment_percent: 'Аванс, %',
  monthly_payment: 'Ежемесячный платёж',
  buyout_amount: 'Выкупной платёж',
  total_cost: 'Стоимость договора',
  total_amount: 'Сумма финансирования',
  vehicles_total: 'Стоимость техники',
  confirmed_amount: 'Сумма сделки',
  reason: 'Причина',
  primary: 'Основной ответственный',
  additional: 'Дополнительный ответственный',
  positions: 'Позиции',
  comment: 'Комментарий',
  category_name: 'Категория',
  dealer_company_id: 'Дилер',
  leasing_company: 'Лизинговая компания',
  down_payment_mode: 'Способ задания аванса',
  monthly_payment_is_manual: 'Платёж задан вручную',
  group_id: 'Группа сделок',
  kind: 'Вид документа',
  files: 'Файлы',
  support_program: 'Программа поддержки',
  support_request: 'Запрос поддержки',
  support_requested_amount: 'Запрошенная поддержка',
  support_decided_amount: 'Согласованная поддержка',
  support_accounted: 'Учтённая поддержка',
}
export const vehicleFieldLabel = (field: string): string => vehicleFieldLabels[field] ?? field

const MONEY_FIELDS = new Set([
  'base_price', 'adjustment_amount', 'support_amount', 'options_amount', 'final_price', 'down_payment', 'monthly_payment',
  'buyout_amount', 'total_cost', 'total_amount', 'vehicles_total', 'confirmed_amount',
  'support_requested_amount', 'support_decided_amount', 'support_accounted',
])
const PERCENT_FIELDS = new Set(['down_payment_percent'])
const ITEM_STATUS_LABELS: Record<string, string> = { active: 'Активна', removed: 'Удалена', replaced: 'Заменена' }
const ADJUSTMENT_LABELS: Record<string, string> = { discount: 'Скидка', markup: 'Наценка' }

function describeOption(item: unknown): string {
  if (item && typeof item === 'object') {
    const record = item as Record<string, unknown>
    const name = typeof record.name === 'string' && record.name ? record.name : String(record.code ?? '')
    const price = typeof record.price === 'string' ? ` — ${formatMoney(record.price)}` : ''
    const comment = typeof record.comment === 'string' && record.comment ? ` (${record.comment})` : ''
    return `${name}${price}${comment}`
  }
  return String(item)
}

/** Human-readable value of one tracked field in a before/after pair. */
export function formatChangeValue(field: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.map(describeOption).join('; ') : 'Не выбрано'
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет'
  if (typeof value === 'object') return JSON.stringify(value)
  const text = String(value)
  if (MONEY_FIELDS.has(field)) return splitDecimal(text) ? formatMoney(text) : text
  if (PERCENT_FIELDS.has(field)) return splitDecimal(text) ? formatPercent(text) : text
  if (field === 'adjustment_type') return ADJUSTMENT_LABELS[text] ?? text
  if (field === 'item_status') return ITEM_STATUS_LABELS[text] ?? text
  if (field === 'status') return dealStatusLabel(text)
  if (field === 'kind') return fileKindLabel(text)
  if (field === 'support_request') return supportStatusLabel(text)
  if (field === 'down_payment_mode') return text === 'percent' ? 'В процентах' : text === 'amount' ? 'В рублях' : text
  return text
}

// ------------------------------------------------------------------------------ vehicles

export function vehicleTitle(vehicle: Pick<FastDealVehicle, 'mark_name' | 'model_name' | 'modification_name' | 'trim_name'>): string {
  return [vehicle.mark_name, vehicle.model_name, vehicle.modification_name, vehicle.trim_name].filter(Boolean).join(' ')
}

/** Financing amount asked for by the initiator: the server's figure, else vehicles total minus the advance. */
export function requestedFinancingAmount(card: Pick<FastDealCard, 'vehicles_total' | 'requested_terms'>): MoneyString | null {
  return card.requested_terms.financing_amount ?? subtractMoney(card.vehicles_total, card.requested_terms.down_payment)
}

export function termsAreComplete(card: Pick<FastDealCard, 'requested_terms'>): boolean {
  const terms = card.requested_terms
  return terms.lease_term_months != null && terms.down_payment != null && terms.monthly_payment != null
}

// -------------------------------------------------------------------------- lookup items

/** Directory rows come from the server as `{ id, name, ... }`; extra keys differ by directory. */
export function lookupText(item: LookupItem, ...keys: string[]): string {
  for (const key of keys) {
    const value = item[key]
    if (typeof value === 'string' && value) return value
  }
  return ''
}

export const lookupName = (item: LookupItem): string =>
  lookupText(item, 'name', 'display_name', 'title', 'equipment_display_name', 'service_display_name', 'purpose_name', 'region_name') || lookupText(item, 'code', 'id')

/** Value stored in an option row: the directory code, falling back to the row id. */
export const lookupCode = (item: LookupItem): string =>
  lookupText(item, 'code', 'equipment_code', 'service_code') || String(item.id)

// ------------------------------------------------------------------- catalog candidates

export interface VehicleCandidate {
  id: UUID
  vin: string
  /** A listing without VIN or «под заказ»: the user types the VIN, nothing is reserved. */
  requiresManualVin: boolean
  title: string
  warehouseName: string | null
  ownerName: string | null
  /** Agreed price of a fixed-price listing; `null` for «цена по запросу». */
  price: MoneyString | null
  priceOnRequest: boolean
  /** Held by any claim (reserve, purchase, another deal). */
  reserved: boolean
  /** The server's verdict: may this unit become a position now. */
  selectable: boolean
  /** Why it cannot (shown instead of hiding the unit). */
  reason: string | null
}

function asText(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

/** Reader of a catalog unit as `handle_vin_lookup` / `handle_vehicle_candidates` present it. */
export function toVehicleCandidate(raw: Record<string, unknown> | null | undefined): VehicleCandidate | null {
  if (!raw) return null
  const id = asText(raw.id)
  if (!id) return null
  const vin = asText(raw.vin).toUpperCase()
  const title = [raw.mark_name, raw.model_name, raw.modification_name, raw.trim_name].map(asText).filter(Boolean).join(' ')
  const warehouse = [asText(raw.warehouse_name), asText(raw.warehouse_city)].filter(Boolean).join(', ')
  const reserved = raw.reserved === true
  const price = asText(raw.base_price) || asText(raw.special_price) || asText(raw.price)
  return {
    id,
    vin,
    requiresManualVin: raw.requires_manual_vin === true || !vin,
    title: title || 'Техника без названия',
    warehouseName: warehouse || null,
    ownerName: asText(raw.owner_company_name) || null,
    price: price || null,
    priceOnRequest: raw.price_on_request === true,
    reserved,
    selectable: raw.selectable !== false && !reserved,
    reason: asText(raw.reason) || null,
  }
}

// ---------------------------------------------------------------------------- options

/** A checkbox of the purposes / regions lists: the stored directory code and its display name. */
export interface ChecklistEntry {
  value: string
  label: string
}

/** One equipment or service row of the options editor; the price stays a decimal STRING. */
export interface OptionRow {
  code: string
  name: string
  price: string
  comment: string
}

/** Sum of the valid prices of the rows, in kopecks as a decimal string. */
export function sumOptionRows(rows: readonly OptionRow[]): MoneyString {
  let total = BigInt(0)
  for (const row of rows) {
    const price = parseMoneyInput(row.price)
    const minor = price === null ? null : toMinor(price)
    if (minor !== null) total += minor
  }
  return fromMinor(total)
}
