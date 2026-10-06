<template>
  <article class="rounded-lg border border-gray-200 p-4" :aria-label="`Позиция ${vehicle.position}: ${title}`">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div class="min-w-0">
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs text-gray-400">№ {{ vehicle.position }}</span>
          <h3 class="text-base font-semibold text-gray-900">{{ title }}</h3>
          <span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-700">
            {{ vehicle.vehicle_source_type === 'product' ? 'Каталог' : 'Вручную' }}
          </span>
          <span v-if="vehicle.vin_entered_manually" class="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">VIN введён вручную</span>
          <span v-if="vehicle.reserved === true" class="rounded-full bg-green-100 px-2 py-0.5 text-xs text-green-800">В резерве</span>
          <span v-else-if="vehicle.is_reservable === true" class="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-800">
            Будет зарезервирована при отправке
          </span>
          <span v-else-if="vehicle.is_reservable === false" class="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">Не резервируется</span>
        </div>
        <p class="mt-1 text-sm text-gray-600">
          VIN <span class="font-mono text-gray-900">{{ vehicle.vin }}</span>
          <span v-if="vehicle.category_name"> · {{ vehicle.category_name }}</span>
          <span v-if="vehicle.body_color_name"> · {{ vehicle.body_color_name }}</span>
          <span v-if="dealerName"> · дилер: {{ dealerName }}</span>
        </p>
      </div>
      <div class="text-right">
        <p class="text-xs text-gray-500">Итоговая цена</p>
        <p class="text-lg font-semibold text-gray-900 tabular-nums">{{ formatMoney(vehicle.final_price) }}</p>
      </div>
    </div>

    <dl v-if="hasBreakdown" class="mt-3 grid grid-cols-[1fr_auto] gap-x-6 gap-y-1 text-sm max-w-md">
      <dt class="text-gray-500">Базовая цена</dt>
      <dd class="text-right tabular-nums">{{ formatMoney(vehicle.base_price) }}</dd>
      <template v-if="vehicle.adjustment_type && vehicle.adjustment_amount">
        <dt class="text-gray-500">{{ vehicle.adjustment_type === 'discount' ? 'Скидка' : 'Наценка' }}</dt>
        <dd class="text-right tabular-nums">{{ vehicle.adjustment_type === 'discount' ? '−' : '+' }}{{ formatMoney(vehicle.adjustment_amount) }}</dd>
      </template>
      <template v-if="isPositiveMoney(vehicle.support_amount)">
        <dt class="text-gray-500">Учтённая поддержка</dt>
        <dd class="text-right tabular-nums">−{{ formatMoney(vehicle.support_amount) }}</dd>
      </template>
      <template v-if="isPositiveMoney(vehicle.options_amount)">
        <dt class="text-gray-500">Оборудование и услуги</dt>
        <dd class="text-right tabular-nums">+{{ formatMoney(vehicle.options_amount) }}</dd>
      </template>
    </dl>

    <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 text-sm">
      <div>
        <p class="text-gray-500">Оборудование</p>
        <ul v-if="vehicle.equipments.length" class="text-gray-900">
          <li v-for="item in vehicle.equipments" :key="item.code">
            {{ item.name || item.code }} — <span class="tabular-nums">{{ formatMoney(item.price) }}</span>
            <span v-if="item.comment" class="text-gray-500"> ({{ item.comment }})</span>
          </li>
        </ul>
        <p v-else class="text-gray-400">Не выбрано</p>
      </div>
      <div>
        <p class="text-gray-500">Услуги</p>
        <ul v-if="vehicle.services.length" class="text-gray-900">
          <li v-for="item in vehicle.services" :key="item.code">
            {{ item.name || item.code }} — <span class="tabular-nums">{{ formatMoney(item.price) }}</span>
            <span v-if="item.comment" class="text-gray-500"> ({{ item.comment }})</span>
          </li>
        </ul>
        <p v-else class="text-gray-400">Не выбрано</p>
      </div>
      <div>
        <p class="text-gray-500">Назначения</p>
        <p v-if="vehicle.purposes.length" class="text-gray-900">{{ vehicle.purposes.map(code => ctx.directoryLabel('purposes', code)).join(', ') }}</p>
        <p v-else class="text-gray-400">Не выбрано</p>
      </div>
      <div>
        <p class="text-gray-500">Регионы</p>
        <p v-if="vehicle.regions.length" class="text-gray-900">{{ vehicle.regions.map(code => ctx.directoryLabel('regions', code)).join(', ') }}</p>
        <p v-else class="text-gray-400">Не выбрано</p>
      </div>
    </div>

    <div v-if="offerFiles.length || canUploadOffer" class="mt-3 rounded-lg bg-gray-50 p-3 text-sm space-y-2">
      <p class="font-medium text-gray-900">КП по технике</p>
      <ul v-if="offerFiles.length" class="space-y-1">
        <li v-for="file in offerFiles" :key="file.id" class="flex items-center justify-between gap-3">
          <span class="truncate">{{ file.filename }} <span class="text-gray-400">· {{ formatFileSize(file.size_bytes) }}</span></span>
          <button type="button" class="text-blue-600 hover:text-blue-700 shrink-0" @click="download(file.id, file.filename)">Скачать</button>
        </li>
      </ul>
      <button v-if="canUploadOffer" type="button" class="btn-outline text-sm px-3 py-1.5" @click="uploadOpen = true">
        Загрузить КП по технике
      </button>
      <p v-if="downloadError" role="alert" class="text-xs text-red-600">{{ downloadError }}</p>
    </div>

    <FastDealSupportPanel v-if="showSupport" :vehicle="vehicle" />

    <div v-if="hasActions" class="mt-4 flex flex-wrap gap-2 border-t border-gray-100 pt-3">
      <button v-if="ctx.canEditPositionData.value" type="button" class="btn-outline text-sm px-3 py-1.5" @click="priceOpen = true">
        {{ ctx.isDD.value ? 'Скидка' : 'Скидка / наценка' }}
      </button>
      <button v-if="canEditData" type="button" class="btn-outline text-sm px-3 py-1.5" @click="editOpen = true">Изменить данные</button>
      <button v-if="ctx.canEditStructure.value" type="button" class="btn-outline text-sm px-3 py-1.5" @click="optionsOpen = true">Опции</button>
      <button v-if="ctx.canEditStructure.value" type="button" class="btn-outline text-sm px-3 py-1.5" @click="replaceOpen = true">Заменить</button>
      <button
        v-if="ctx.canEditStructure.value"
        type="button"
        class="btn-outline text-sm px-3 py-1.5 text-red-700 border-red-200 hover:bg-red-50"
        @click="removeOpen = true"
      >
        Удалить
      </button>
    </div>

    <FastDealVehiclePriceModal v-if="priceOpen" :vehicle="vehicle" @close="priceOpen = false" />
    <FastDealVehicleEditModal v-if="editOpen" :deal="deal" :vehicle="vehicle" @close="editOpen = false" />
    <FastDealVehicleOptionsModal v-if="optionsOpen" :vehicle="vehicle" @close="optionsOpen = false" />
    <FastDealVehicleAddModal v-if="replaceOpen" :deal="deal" :replace-vehicle="vehicle" @close="replaceOpen = false" />
    <FastDealFilesUploadModal v-if="uploadOpen" :deal="deal" initial-kind="vehicle_offer" :vehicle="vehicle" @close="uploadOpen = false" />
    <FastDealActionDialog
      v-if="removeOpen"
      title="Удалить позицию"
      :message="`Позиция «${title}» (VIN ${vehicle.vin}) будет удалена из сделки.`"
      :warnings="removeWarnings"
      confirm-text="Удалить"
      danger
      :busy="ctx.busy.value"
      :error="removeError"
      @confirm="remove"
      @close="removeOpen = false"
    />
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { formatFileSize, formatMoney, isPositiveMoney, vehicleTitle } from '../composables/fastDealCardFormat'
import { parseFastDealError } from '../api/fastDealsApi'
import type { FastDealCard, FastDealVehicle } from '../types'
import FastDealActionDialog from './FastDealActionDialog.vue'
import FastDealFilesUploadModal from './FastDealFilesUploadModal.vue'
import FastDealSupportPanel from './FastDealSupportPanel.vue'
import FastDealVehicleAddModal from './FastDealVehicleAddModal.vue'
import FastDealVehicleEditModal from './FastDealVehicleEditModal.vue'
import FastDealVehicleOptionsModal from './FastDealVehicleOptionsModal.vue'
import FastDealVehiclePriceModal from './FastDealVehiclePriceModal.vue'

const props = defineProps<{ deal: FastDealCard; vehicle: FastDealVehicle }>()

const ctx = useFastDealCardContext()
const priceOpen = ref(false)
const editOpen = ref(false)
const optionsOpen = ref(false)
const replaceOpen = ref(false)
const removeOpen = ref(false)
const uploadOpen = ref(false)
const removeError = ref<ActionFailure | null>(null)
const downloadError = ref('')

const title = computed(() => vehicleTitle(props.vehicle))
/** After the split every position belongs to the deal's dealer, so the name is shown only before it. */
const dealerName = computed(() => (!ctx.isDD.value && !props.deal.dealer_company ? ctx.companyName(props.vehicle.dealer_company_id) : ''))
/** The breakdown is absent for a leasing company when it would disclose support. */
const hasBreakdown = computed(() => props.vehicle.base_price != null)
const offerFiles = computed(() => props.deal.files.filter(file => file.kind === 'vehicle_offer' && file.fast_deal_vehicle_id === props.vehicle.id))
/** `vehicle_offer` exists in DD and is uploaded by a leasing company whose invitation is still open. */
const OPEN_INVITATION_STATUSES = ['pending_review', 'offer_sent', 'selected_by_dealer']
const canUploadOffer = computed(
  () => ctx.isDD.value
    && ctx.party.value === 'leasing'
    && ctx.can('upload_files')
    && OPEN_INVITATION_STATUSES.includes(ctx.ownApplication.value?.status ?? ''),
)
const showSupport = computed(
  () => ctx.supportVisible.value
    && (props.vehicle.applied_supports != null || props.vehicle.support_request != null || !!props.vehicle.support_hint),
)
const canEditData = computed(
  () => ctx.canEditPositionData.value && Object.values(ctx.editableFields(props.vehicle)).some(Boolean),
)
const hasActions = computed(() => ctx.canEditPositionData.value || ctx.canEditStructure.value)

const removeWarnings = computed(() => {
  const warnings: string[] = []
  if (ctx.editWillReset.value) {
    warnings.push('Сделка вернётся в черновик: коммерческие предложения лизинговых компаний будут аннулированы, резервы сняты.')
  }
  if (ctx.card.value?.sent_at) warnings.push('Резерв этой единицы будет освобождён; позиция останется в истории сделки.')
  return warnings
})

async function remove() {
  removeError.value = null
  const result = await ctx.run((etag, card) => ctx.api.removeVehicle(card.id, props.vehicle.id, etag))
  if (result.ok) removeOpen.value = false
  else removeError.value = result.error
}

async function download(fileId: string, filename: string) {
  downloadError.value = ''
  try {
    await ctx.api.downloadFile(props.deal.id, fileId, filename)
  } catch (error) {
    downloadError.value = parseFastDealError(error).detail
  }
}
</script>
