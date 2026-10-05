import type {
  CommerceCreateOrderResult,
  CommerceOrder,
  CommerceOrderSnapshot,
  CommercePayment,
} from '~/features/commerce/types'
import type {
  SpecialEquipmentCreateOrderResponse,
  SpecialEquipmentOrder,
  SpecialEquipmentPayment,
} from '../types'

const snapshotText = (
  snapshot: Record<string, unknown>,
  key: keyof CommerceOrderSnapshot,
): string | null => {
  const value = snapshot[key]
  return typeof value === 'string' && value.trim() ? value : null
}

const orderSnapshot = (order: SpecialEquipmentOrder): CommerceOrderSnapshot => {
  const snapshot = order.item_snapshot
  return {
    title: snapshotText(snapshot, 'title') ?? 'Спецтехника',
    subtitle: snapshotText(snapshot, 'subtitle'),
    image_url: snapshotText(snapshot, 'image_url'),
    manufacturer: snapshotText(snapshot, 'manufacturer'),
    model: snapshotText(snapshot, 'model'),
    modification: snapshotText(snapshot, 'modification'),
    year: typeof snapshot.year === 'number' ? snapshot.year : null,
  }
}

const commerceOrder = (order: SpecialEquipmentOrder): CommerceOrder => ({
  id: order.id,
  item: { type: 'special_equipment', id: order.product_id },
  item_snapshot: orderSnapshot(order),
  purchase_type: order.purchase_type,
  status: order.status,
  total_price: String(order.total_price),
  paid_amount: String(order.paid_amount),
  remaining_amount: String(order.remaining_amount),
  currency_code: order.currency_code,
  leasing_application_id: order.leasing_application_id,
  down_payment_percent: order.down_payment_percent === null
    ? null
    : String(order.down_payment_percent),
  hold_expires_at: order.hold_expires_at,
  cancellation_reason: order.cancellation_reason,
  cancellation_requested_at: order.cancellation_requested_at,
  cancelled_at: order.cancelled_at,
  created_at: order.created_at,
  updated_at: order.updated_at,
})

const commercePayment = (
  payment: SpecialEquipmentPayment,
  order: SpecialEquipmentOrder,
): CommercePayment => ({
  id: payment.id,
  order: { type: 'special_equipment', id: order.id },
  payment_type: payment.payment_type,
  amount: String(payment.amount),
  status: payment.status,
  payment_method: payment.payment_method,
  error_message: payment.error_message,
  fiscal_status: payment.fiscal_status,
  expires_at: payment.expires_at,
  paid_at: payment.paid_at,
  created_at: payment.created_at,
  updated_at: payment.updated_at,
  receipt_content_url: payment.receipt_content_url,
})

export const specialEquipmentCreateOrderResult = (
  response: SpecialEquipmentCreateOrderResponse,
): CommerceCreateOrderResult => ({
  orders: [commerceOrder(response.order)],
  payments: response.payment ? [commercePayment(response.payment, response.order)] : [],
  replayed: response.replayed,
  widgetData: response.widgetData
    ? { ...response.widgetData, amount: String(response.widgetData.amount) }
    : null,
  sbpData: response.sbpData
    ? { ...response.sbpData, amount: String(response.sbpData.amount) }
    : null,
})
