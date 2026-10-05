<template>
  <section class="fulfillment" aria-label="Подбор автомобилей со склада">
    <div class="flex items-center justify-between gap-4">
      <div><h4 class="text-base font-semibold">{{ title || 'Количество и подбор со склада' }}</h4><p class="mt-1 text-sm">Подберите конкретные автомобили для этой позиции заявки.</p></div>
      <button type="button" class="btn-secondary" :disabled="state.pending" @click="state.load">Обновить</button>
    </div>
    <p v-if="state.error" class="mt-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]" role="alert">{{ state.error }}</p>
    <p v-if="state.pending" class="mt-3 text-sm" role="status">Загружаем данные…</p>
    <template v-if="state.current">
      <dl class="mt-4 grid grid-cols-4 gap-4 text-sm">
        <div><dt>Запрошено клиентом</dt><dd class="text-lg font-semibold">{{ state.current.requested_quantity ?? 'Не зафиксировано' }}</dd></div>
        <div><dt>Подтверждено</dt><dd class="text-lg font-semibold">{{ state.current.confirmed_quantity ?? 'Не подтверждено' }}</dd></div>
        <div><dt>Подобрано</dt><dd class="text-lg font-semibold">{{ state.selected.length }}</dd></div>
        <div><dt>Осталось подобрать</dt><dd class="text-lg font-semibold">{{ state.remaining }}</dd></div>
      </dl>
      <fieldset v-if="state.current.editable" :disabled="state.pending" class="mt-4 space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <label class="text-sm font-medium">Подтверждаемое количество, шт.<input v-model.number="state.quantity" class="input-field mt-1" type="number" min="1" step="1" /></label>
          <label class="text-sm font-medium">Бронь до<input v-model="state.expires" class="input-field mt-1" type="date" /></label>
        </div>
        <p class="text-sm">Для замены снимите выбор со старого автомобиля и выберите новый. Текущая бронь сохраняется до успешного сохранения.</p>
        <label class="block text-sm font-medium">Поиск по VIN<input v-model="search" class="input-field mt-1" type="search" placeholder="VIN автомобиля" /></label>
        <div class="max-h-64 overflow-y-auto rounded-lg border border-[color:var(--storefront-border,#e5e7eb)]">
          <table class="w-full text-left text-sm">
            <thead class="bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/1)]"><tr><th class="p-3">Выбор</th><th class="p-3">VIN</th><th class="p-3">Год / цвет</th><th class="p-3">Цена на складе</th></tr></thead>
            <tbody><tr v-for="vehicle in stock" :key="vehicle.id" class="border-t border-[color:var(--storefront-border,#e5e7eb)]">
              <td class="p-3"><input v-model="state.selected" type="checkbox" :value="vehicle.id" :aria-label="`Подобрать ${vehicle.vin || vehicle.id}`" :disabled="!state.selected.includes(vehicle.id) && state.remaining <= 0" /></td>
              <td class="p-3 font-mono">{{ vehicle.vin || 'VIN не указан' }}<span v-if="state.active.some(item => item.vehicle_id === vehicle.id)" class="mt-1 block font-sans text-xs">В текущей брони</span></td>
              <td class="p-3">{{ vehicle.year || '—' }} / {{ vehicle.color || '—' }}</td>
              <td class="p-3 tabular-nums">{{ money(vehicle.discount_price ?? vehicle.base_price) }}</td>
            </tr></tbody>
          </table>
          <p v-if="!stock.length" class="p-4 text-sm">{{ search.trim() ? 'По этому VIN ничего не найдено.' : 'Подходящих автомобилей на складе нет. Можно сохранить частичный подбор.' }}</p>
        </div>
        <p class="text-sm">Замена VIN сохраняет согласованную цену позиции. Итоги пересчитываются по подтверждённому количеству.</p>
        <label class="block text-sm font-medium">{{ state.replacing ? 'Причина замены или исключения (обязательно)' : 'Комментарий' }}<textarea v-model="state.comment" class="input-field mt-1" rows="2" /></label>
      </fieldset>
      <ul v-if="!state.current.editable && state.active.length" class="mt-4 space-y-2 text-sm"><li v-for="allocation in state.active" :key="allocation.id"><span class="font-mono">{{ allocation.vin || allocation.vehicle_id }}</span> — {{ allocation.completed_at ? 'Куплена' : allocation.reservation_fixed ? 'Закреплено за сделкой' : !allocation.reserved_until ? 'Забронирована' : `бронь до ${new Date(allocation.reserved_until).toLocaleDateString('ru-RU')}` }}</li></ul>
      <p v-if="!state.current.editable" class="mt-3 text-sm">Редактирование недоступно на текущем этапе заявки или для вашей компании.</p>
      <p v-if="state.remaining < 0" class="mt-3 text-sm text-[color:var(--storefront-error-text,#b91c1c)]" role="alert">Сначала исключите лишние автомобили из подбора.</p>
      <div v-if="state.preview" class="mt-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] p-4">
        <h5 class="font-semibold">Расчёт заявки: было → станет</h5>
        <dl class="mt-2 space-y-2 text-sm"><div v-for="row in totalRows" :key="row.key" class="flex justify-between gap-4"><dt>{{ row.label }}</dt><dd class="tabular-nums">{{ money(state.current.application_totals[row.key]) }} → {{ money(state.preview.application_totals[row.key]) }}</dd></div></dl>
      </div>
      <div v-if="state.current.editable" class="mt-4 flex gap-3">
        <button type="button" class="btn-secondary" :disabled="state.pending || !state.valid" @click="state.calculate">Пересчитать и проверить</button>
        <button type="button" class="btn-primary" :disabled="state.pending || !state.preview || !state.valid" @click="save">Сохранить подбор</button>
      </div>
      <details v-if="state.current.history.length" class="mt-4 text-sm"><summary class="cursor-pointer">История изменений</summary><ul class="mt-2 space-y-2"><li v-for="event in state.current.history" :key="event.id">{{ new Date(event.created_at).toLocaleString('ru-RU') }} — {{ event.comment || 'Изменён подбор или количество' }}</li></ul></details>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { UUID } from '~/types/ids'
import { useNotificationCompanyRequest } from '~/features/notifications'
import { useVehicleFulfillment } from '~/features/applications/composables/useVehicleFulfillment'
const props = defineProps<{ applicationVehicleId: UUID; title?: string }>()
const emit = defineEmits<{ updated: [] }>()
const { request } = useNotificationCompanyRequest()
const state = reactive(useVehicleFulfillment(() => props.applicationVehicleId, (path, options) => request(path, { ...options, credentials: 'include' })))
const search = ref('')
const stock = computed(() => state.current?.available_vehicles.filter(vehicle => !search.value.trim() || (vehicle.vin || '').toLowerCase().includes(search.value.trim().toLowerCase())) ?? [])
const money = (value: number | null | undefined) => value == null ? '—' : new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 2 }).format(value)
const totalRows = [{ key: 'total_amount', label: 'Стоимость заявки' }, { key: 'down_payment', label: 'Аванс' }, { key: 'monthly_payment', label: 'Ежемесячный платёж' }, { key: 'total_cost', label: 'Итог по лизингу' }]
const save = async () => { if (await state.save()) emit('updated') }
onMounted(state.load)
</script>
<style scoped>
.fulfillment { border: 1px solid var(--storefront-border, #e5e7eb); border-radius: 0.5rem; padding: 1rem; color: var(--storefront-text, #111827); background: rgb(var(--storefront-surface-rgb, 255 255 255)); }
button:focus-visible, input:focus-visible, textarea:focus-visible { outline: 2px solid var(--storefront-focus, #2563eb); outline-offset: 2px; }
button:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
