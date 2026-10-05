import type { SpecialEquipmentProductCard } from './types'

type AttachmentLeasingCandidate = Pick<
  SpecialEquipmentProductCard,
  'code' | 'sale_status'
> & {
  capabilities: Pick<SpecialEquipmentProductCard['capabilities'], 'can_lease' | 'reason'>
}

const leaseableStatuses = new Set<SpecialEquipmentProductCard['sale_status']>([
  'available',
  'on_order',
])

export const specialEquipmentAttachmentLeasingError = (
  attachments: readonly AttachmentLeasingCandidate[],
): string | null => {
  for (const attachment of attachments) {
    if (!leaseableStatuses.has(attachment.sale_status)) {
      return `Надстройка ${attachment.code} недоступна для оформления в лизинг. Обновите состав комплекта.`
    }
    if (!attachment.capabilities.can_lease) {
      const reason = attachment.capabilities.reason?.trim()
      return reason
        ? `Надстройка ${attachment.code}: ${reason}`
        : `Надстройку ${attachment.code} нельзя оформить в лизинг. Обновите состав комплекта.`
    }
  }
  return null
}
