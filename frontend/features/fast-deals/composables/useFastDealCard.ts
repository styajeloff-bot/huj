import { computed, inject, provide, ref, type InjectionKey } from 'vue'
import type { UUID } from '~/types/ids'
import { createFastDealsApi, parseFastDealError, type CardResponse, type FastDealsApi } from '../api/fastDealsApi'
import type { FastDealAction, FastDealCard, FastDealLcApplication, FastDealParty, FastDealVehicle } from '../types'

export type CardLoadState = 'loading' | 'ready' | 'not_found' | 'forbidden' | 'error'

/** A failed request in the shape the forms need: message, offending field, VIN of a reserve conflict. */
export interface ActionFailure {
  status?: number
  detail: string
  field?: string
  vin?: string
  sourceNumber?: string
  code?: string
}

export type ActionResult<T> = { ok: true; value: T } | { ok: false; error: ActionFailure }

/** Statuses of a DD in which any business change of the dealer resets the deal to a draft. */
const RESETTING_STATUSES = new Set(['pending_lc_confirmation', 'pending_lc_final_confirmation'])

/**
 * State and server-driven rules of one fast deal card.
 *
 * Every mutation is sent with the card's current `etag` (`If-Match`) and the answer replaces the
 * local card, so the next mutation always carries the fresh version. A 412 raises `stale`: the
 * page then asks to reload the card instead of retrying blindly.
 */
export function useFastDealCard(dealId: UUID, companyContext: () => string | undefined = () => undefined) {
  const config = useRuntimeConfig()
  const api: FastDealsApi = createFastDealsApi(config, companyContext)

  const card = ref<FastDealCard | null>(null)
  const loadState = ref<CardLoadState>('loading')
  const loadError = ref('')
  const busy = ref(false)
  const stale = ref(false)
  const refreshError = ref('')
  const extraCompanyNames = ref<Record<string, string>>({})
  const directoryLabels = ref<{ purposes: Record<string, string>; regions: Record<string, string> }>({ purposes: {}, regions: {} })
  const offerDialog = ref<{ prefill: boolean } | null>(null)
  const resetPrompt = ref<{ resolve: (accepted: boolean) => void } | null>(null)

  // ---------------------------------------------------------------------------- loading

  async function load(options: { silent?: boolean } = {}): Promise<void> {
    const silent = options.silent === true && card.value !== null
    if (!silent) loadState.value = 'loading'
    refreshError.value = ''
    try {
      const response = await api.get(dealId)
      card.value = response.deal
      loadState.value = 'ready'
      stale.value = false
    } catch (error) {
      const parsed = parseFastDealError(error)
      if (silent) {
        refreshError.value = parsed.detail
        return
      }
      loadError.value = parsed.detail
      loadState.value = parsed.status === 404 ? 'not_found' : parsed.status === 403 ? 'forbidden' : 'error'
    }
  }

  /** Reload keeping the card on screen; used by the «Обновить карточку» prompts. */
  const reload = () => load({ silent: true })

  // ------------------------------------------------------------------------- mutations

  const fail = (detail: string): ActionResult<never> => ({ ok: false, error: { detail } })

  async function guard<T>(operation: () => Promise<T>): Promise<ActionResult<T>> {
    if (busy.value) return fail('Дождитесь завершения предыдущей операции')
    busy.value = true
    try {
      return { ok: true, value: await operation() }
    } catch (error) {
      const parsed = parseFastDealError(error)
      if (parsed.status === 412) stale.value = true
      if (parsed.status === 404) loadState.value = 'not_found'
      return {
        ok: false,
        error: {
          status: parsed.status,
          detail: parsed.detail,
          field: parsed.field,
          vin: parsed.vin,
          sourceNumber: parsed.source_number,
          code: parsed.code,
        },
      }
    } finally {
      busy.value = false
    }
  }

  /** Run a mutation with the current etag; on success the returned card replaces the local one. */
  async function run<T extends CardResponse>(
    action: (etag: string, current: FastDealCard) => Promise<T>,
  ): Promise<ActionResult<T>> {
    const current = card.value
    if (!current) return fail('Карточка ещё не загружена')
    const outcome = await guard(() => action(current.etag, current))
    if (outcome.ok) {
      card.value = outcome.value.deal
      stale.value = false
    }
    return outcome
  }

  const replaceCard = (next: FastDealCard) => {
    card.value = next
    stale.value = false
  }

  /** Purposes and regions are stored by directory code; this loads their display names (best effort). */
  async function loadDirectoryLabels(): Promise<void> {
    try {
      const [purposes, regions] = await Promise.all([api.lookup('purposes'), api.lookup('regions')])
      const toMap = (items: { code?: unknown; name?: unknown; id: unknown }[]) =>
        Object.fromEntries(items.map(item => [String(item.code ?? item.id), String(item.name ?? item.code ?? item.id)]))
      directoryLabels.value = { purposes: toMap(purposes.items), regions: toMap(regions.items) }
    } catch {
      // Codes stay readable without the display names.
    }
  }

  /** Display name of a stored purpose / region code; the code itself while the directory is not loaded. */
  const directoryLabel = (kind: 'purposes' | 'regions', code: string): string => directoryLabels.value[kind][code] ?? code

  // ---------------------------------------------------------------------- derived rules

  const allowed = computed<Set<FastDealAction>>(() => new Set(card.value?.allowed_actions ?? []))
  const can = (action: FastDealAction): boolean => allowed.value.has(action)
  const party = computed<FastDealParty | null>(() => card.value?.party ?? null)
  const isDD = computed(() => card.value?.source_type === 'dealer_to_leasing')
  const isDL = computed(() => card.value?.source_type === 'leasing_to_dealer')
  const isInitiator = computed(() => party.value === 'initiator')
  const status = computed(() => card.value?.status ?? null)
  const isFinal = computed(() => status.value === 'confirmed' || status.value === 'cancelled')

  const activeVehicles = computed<FastDealVehicle[]>(() => (card.value?.vehicles ?? []).filter(item => item.item_status === 'active'))
  const inactiveVehicles = computed<FastDealVehicle[]>(() => (card.value?.vehicles ?? []).filter(item => item.item_status !== 'active'))

  /** Positions, options and terms are edited by the initiator only. */
  const canEditStructure = computed(() => can('edit') && party.value === 'initiator')
  /** Price adjustment and allowed data of a position: the initiator and (DL) the dealer. */
  const canEditPositionData = computed(() => can('edit') && (party.value === 'initiator' || party.value === 'dealer'))
  /** DD offers a discount only; DL a discount or a markup. */
  const adjustmentTypes = computed<('discount' | 'markup')[]>(() => (isDD.value ? ['discount'] : ['discount', 'markup']))
  /** Support belongs to the dealer side; a leasing company never gets support data at all. */
  const dealerSide = computed(() => (isDD.value ? party.value === 'initiator' : party.value === 'dealer'))
  const supportVisible = computed(() => dealerSide.value || party.value === 'platform' || party.value === 'distributor')

  /** DD: a business change after sending drops the deal back to a draft. */
  const editWillReset = computed(() => isDD.value && party.value === 'initiator' && status.value !== null && RESETTING_STATUSES.has(status.value))
  /** A rejected deal returns to a draft with the first change of its initiator. */
  const editWillReopen = computed(() => status.value === 'rejected' && can('edit'))

  /** The invitation of the leasing company itself (the server never returns another party's). */
  const ownApplication = computed<FastDealLcApplication | null>(() => (party.value === 'leasing' ? card.value?.lc_applications[0] ?? null : null))

  /** Company of the caller's own party, for the assignees editor. */
  const partyCompanyId = computed<UUID | null>(() => {
    const current = card.value
    if (!current) return null
    if (current.party === 'initiator') return current.initiator_company.id
    if (current.party === 'dealer') return current.dealer_company?.id ?? null
    if (current.party === 'leasing') return ownApplication.value?.leasing_company.id ?? null
    return null
  })

  const companyNames = computed<Record<string, string>>(() => {
    const names: Record<string, string> = { ...extraCompanyNames.value }
    const current = card.value
    if (!current) return names
    for (const brief of [current.client, current.initiator_company, current.dealer_company, current.leasing_company]) {
      if (brief) names[brief.id] = brief.name
    }
    for (const application of current.lc_applications) names[application.leasing_company.id] = application.leasing_company.name
    for (const sibling of current.group_deals) {
      if (sibling.dealer_company) names[sibling.dealer_company.id] = sibling.dealer_company.name
    }
    return names
  })

  const companyName = (id: UUID | null | undefined): string => (id ? companyNames.value[id] ?? '' : '')
  const rememberCompany = (id: UUID, name: string) => {
    if (id && name) extraCompanyNames.value = { ...extraCompanyNames.value, [id]: name }
  }

  /** Link to another deal of the group, keeping the company context of the current screen. */
  const dealLocation = (id: UUID) => {
    const company = companyContext()
    const path = `/workspace/fast-deals/${id}`
    return company ? { path, query: { notification_company_id: company } } : { path }
  }

  // ----------------------------------------------------------------- shared UI requests

  /** Ask before a change that resets a sent deal to a draft; resolves `true` when nothing needs asking. */
  function confirmEdit(): Promise<boolean> {
    if (!editWillReset.value) return Promise.resolve(true)
    resetPrompt.value?.resolve(false)
    return new Promise<boolean>(resolve => {
      resetPrompt.value = { resolve }
    })
  }

  function answerResetPrompt(accepted: boolean): void {
    resetPrompt.value?.resolve(accepted)
    resetPrompt.value = null
  }

  const openOfferDialog = (prefill: boolean) => {
    offerDialog.value = { prefill }
  }
  const closeOfferDialog = () => {
    offerDialog.value = null
  }

  return {
    api,
    dealId,
    card,
    loadState,
    loadError,
    busy,
    stale,
    refreshError,
    offerDialog,
    resetPrompt,
    load,
    reload,
    loadDirectoryLabels,
    directoryLabel,
    guard,
    run,
    replaceCard,
    can,
    party,
    isDD,
    isDL,
    isInitiator,
    status,
    isFinal,
    activeVehicles,
    inactiveVehicles,
    canEditStructure,
    canEditPositionData,
    adjustmentTypes,
    dealerSide,
    supportVisible,
    editWillReset,
    editWillReopen,
    ownApplication,
    partyCompanyId,
    companyNames,
    companyName,
    rememberCompany,
    dealLocation,
    confirmEdit,
    answerResetPrompt,
    openOfferDialog,
    closeOfferDialog,
  }
}

export type FastDealCardController = ReturnType<typeof useFastDealCard>

const CARD_KEY: InjectionKey<FastDealCardController> = Symbol('fast-deal-card')

export const provideFastDealCard = (controller: FastDealCardController): void => provide(CARD_KEY, controller)

/** The controller of the surrounding card page; card components never create their own. */
export function useFastDealCardContext(): FastDealCardController {
  const controller = inject(CARD_KEY, null)
  if (!controller) throw new Error('useFastDealCardContext() requires FastDealCardPage above it')
  return controller
}

