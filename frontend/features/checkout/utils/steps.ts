export const CHECKOUT_MAX_STEP = 7

export const CHECKOUT_LCA_STATUS_BUCKETS = {
  sent: {
    label: 'Выбранные ЛК',
    statuses: [
      'submitted',
      'under_review',
      'pending_distribution',
      'closed',
      'rejected_prescoring',
      'rejected_approved',
    ],
  },
  preliminary: {
    label: 'Предварительные',
    statuses: ['approved_scoring', 'approved_scoring_another_cond'],
  },
  documents: {
    label: 'Доп. документы',
    statuses: ['documents_required', 'under_review_with_docs'],
  },
  final: {
    label: 'Итоговое',
    statuses: ['approved_final', 'approved_final_another_cond'],
  },
  selected: {
    label: 'Выбор ЛК',
    statuses: ['selected_lc'],
  },
  deal: {
    label: 'Сделка',
    statuses: ['deal'],
  },
} as const

export type CheckoutStatusBucket = keyof typeof CHECKOUT_LCA_STATUS_BUCKETS
export type CheckoutSection = 'questionnaire' | 'company' | CheckoutStatusBucket

export const CHECKOUT_STATUS_SECTIONS = [
  { section: 'sent', num: 3, label: 'Выбранные ЛК', bucket: 'sent' },
  { section: 'preliminary', num: 4, label: 'Предварительные', bucket: 'preliminary' },
  { section: 'documents', label: 'Доп. документы', bucket: 'documents' },
  { section: 'final', num: 5, label: 'Итоговое', bucket: 'final' },
  { section: 'selected', num: 6, label: 'Выбор ЛК', bucket: 'selected' },
  { section: 'deal', num: 7, label: 'Сделка', bucket: 'deal' },
] as const satisfies readonly {
  section: CheckoutStatusBucket
  num?: number
  label: string
  bucket: CheckoutStatusBucket
}[]

/** Permanent, numbered desktop steps. Documents is inserted only when available. */
export const CHECKOUT_STEPS = [
  { section: 'questionnaire', num: 1, label: 'Анкета' },
  { section: 'company', num: 2, label: 'О компании' },
  { section: 'sent', num: 3, label: 'Выбранные ЛК', bucket: 'sent' },
  { section: 'preliminary', num: 4, label: 'Предварительные', bucket: 'preliminary' },
  { section: 'final', num: 5, label: 'Итоговое', bucket: 'final' },
  { section: 'selected', num: 6, label: 'Выбор ЛК', bucket: 'selected' },
  { section: 'deal', num: 7, label: 'Сделка', bucket: 'deal' },
] as const

export const normalizeCheckoutStep = (step: unknown) => {
  const parsedStep = Number(step)
  if (!Number.isFinite(parsedStep)) return 1

  const integerStep = Math.trunc(parsedStep)
  if (integerStep < 1) return 1
  if (integerStep > CHECKOUT_MAX_STEP) return CHECKOUT_MAX_STEP
  return integerStep
}

export const checkoutSectionForStep = (step: unknown): Exclude<CheckoutSection, 'documents'> => {
  const normalized = normalizeCheckoutStep(step)
  return CHECKOUT_STEPS.find(candidate => candidate.num === normalized)?.section ?? 'questionnaire'
}

export const checkoutStepForSection = (section: Exclude<CheckoutSection, 'documents'>) =>
  CHECKOUT_STEPS.find(candidate => candidate.section === section)?.num ?? 1

export const isCheckoutStatusSection = (section: CheckoutSection): section is CheckoutStatusBucket =>
  section !== 'questionnaire' && section !== 'company'

export const getLatestStatusSection = (availableSections: Iterable<CheckoutStatusBucket>): CheckoutStatusBucket | null => {
  const available = new Set(availableSections)
  for (const step of [...CHECKOUT_STATUS_SECTIONS].reverse()) {
    if (available.has(step.section)) return step.section
  }
  return null
}
