import type { CommerceApplicationItem } from './types'

export const specialEquipmentApplicationItemRoleLabel = (
  role: CommerceApplicationItem['item_role'],
): string => ({
  offer: 'Основная позиция',
  attachment: 'Надстройка',
  component: 'Компонент',
})[role ?? 'offer']
