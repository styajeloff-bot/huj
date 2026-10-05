import type { AssignedDealer, DealerDistributionPayload, DealerDistributionPosition } from './api/applicationsApi'

export function groupDealerDistribution(positions: DealerDistributionPosition[]) {
  const groups = new Map<string, { dealer: AssignedDealer; items: { id: string; title: string; quantity: number }[] }>()
  for (const position of positions) {
    const allocations = position.stock_dealer
      ? [{ dealer: position.stock_dealer, quantity: position.quantity }]
      : position.dealer_allocations
    for (const allocation of allocations) {
      let group = groups.get(allocation.dealer.id)
      if (!group) {
        group = { dealer: allocation.dealer, items: [] }
        groups.set(allocation.dealer.id, group)
      }
      group.items.push({ id: position.application_vehicle_id, title: position.title, quantity: allocation.quantity })
    }
  }
  return [...groups.values()]
}

export function distributablePositions(positions: DealerDistributionPosition[]) {
  return positions.filter(position => position.can_assign_dealer && !position.stock_dealer && position.unassigned_quantity > 0)
}

export function distributionItems(
  positions: DealerDistributionPosition[],
  selectedIds: string[],
  quantities: Record<string, number | string>,
): DealerDistributionPayload['items'] {
  if (!selectedIds.length) throw new Error('Выберите хотя бы один автомобиль.')
  const eligible = new Map(distributablePositions(positions).map(position => [position.application_vehicle_id, position]))
  return [...new Set(selectedIds)].map(id => {
    const position = eligible.get(id)
    if (!position) throw new Error('Выбранная позиция больше недоступна для распределения. Обновите остатки.')
    const quantity = quantities[id]
    if (typeof quantity !== 'number' || !Number.isInteger(quantity) || quantity < 1 || quantity > position.unassigned_quantity) {
      throw new Error(`«${position.title}»: укажите целое количество от 1 до ${position.unassigned_quantity}.`)
    }
    return { application_vehicle_id: id, quantity, expected_unassigned_quantity: position.unassigned_quantity }
  })
}

/** A retry of the same intent must reuse its key, even after an uncertain network failure. */
export function createDistributionRequest(createId: () => string) {
  let signature = ''
  let requestId = ''
  return (dealerId: string, items: DealerDistributionPayload['items']): DealerDistributionPayload => {
    const nextSignature = JSON.stringify({ dealerId, items })
    if (nextSignature !== signature) {
      requestId = createId()
      signature = nextSignature
    }
    return { request_id: requestId, dealer_id: dealerId, items }
  }
}
