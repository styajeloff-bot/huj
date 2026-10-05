<template>
  <Modal
    :show="true"
    title="Загрузить документы"
    size="2xl"
    :show-footer="true"
    :closable="!ctx.busy.value"
    :close-on-overlay="!ctx.busy.value"
    @close="emit('close')"
  >
    <form id="fast-deal-upload-form" class="space-y-4" novalidate @submit.prevent="submit">
      <FastDealCardField label="Вид документа" required for-id="fast-deal-upload-kind" :error="errorOf('kind')">
        <select id="fast-deal-upload-kind" v-model="kind" class="select-field" :disabled="ctx.busy.value">
          <option v-for="option in kindOptions" :key="option.value" :value="option.value" :disabled="!!option.disabledReason">
            {{ option.label }}{{ option.disabledReason ? ` — ${option.disabledReason}` : '' }}
          </option>
        </select>
      </FastDealCardField>
      <p v-if="kindHint" class="text-xs text-gray-500">{{ kindHint }}</p>

      <FastDealCardField
        v-if="kind === 'deal_additional' && needsAddressees"
        label="Адресаты (лизинговые компании)"
        required
        :error="errorOf('addressee_company_ids') || local.addressees"
      >
        <ul class="space-y-1 rounded-lg border border-gray-200 p-3">
          <li v-for="application in openApplications" :key="application.id">
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                class="rounded text-blue-600"
                :checked="addressees.includes(application.leasing_company.id)"
                :disabled="ctx.busy.value"
                @change="toggleAddressee(application.leasing_company.id)"
              />
              {{ application.leasing_company.name }}
            </label>
          </li>
        </ul>
      </FastDealCardField>

      <FastDealCardField
        v-if="kind === 'vehicle_offer'"
        label="Позиция"
        required
        for-id="fast-deal-upload-vehicle"
        :error="errorOf('fast_deal_vehicle_id') || local.vehicle"
      >
        <select id="fast-deal-upload-vehicle" v-model="vehicleId" class="select-field" :disabled="ctx.busy.value || !!vehicle">
          <option value="">Выберите позицию</option>
          <option v-for="item in ctx.activeVehicles.value" :key="item.id" :value="item.id">
            {{ vehicleTitle(item) }} · {{ item.vin }}
          </option>
        </select>
      </FastDealCardField>

      <FastDealCardField label="Файлы" required for-id="fast-deal-upload-files" :error="errorOf('files') || local.files" :hint="limitsHint">
        <input
          id="fast-deal-upload-files"
          type="file"
          multiple
          class="block w-full text-sm text-gray-700 file:mr-3 file:rounded-lg file:border-0 file:bg-gray-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-gray-200"
          :disabled="ctx.busy.value"
          @change="onFiles"
        />
      </FastDealCardField>
      <ul v-if="files.length" class="space-y-1 text-sm">
        <li v-for="(file, index) in files" :key="`${file.name}-${index}`" class="flex items-center justify-between gap-3">
          <span class="truncate">{{ file.name }} <span class="text-gray-400">· {{ formatFileSize(file.size) }}</span></span>
          <button type="button" class="text-red-600 hover:text-red-700 shrink-0" :disabled="ctx.busy.value" @click="removeFile(index)">Убрать</button>
        </li>
      </ul>

      <FastDealCardError :error="generalError" />
    </form>
    <template #footer>
      <button type="button" class="btn-secondary" :disabled="ctx.busy.value" @click="emit('close')">Отмена</button>
      <button type="submit" form="fast-deal-upload-form" class="btn-primary" :disabled="ctx.busy.value || !kindOptions.some(o => !o.disabledReason)" :aria-busy="ctx.busy.value">
        {{ ctx.busy.value ? 'Загружаем…' : 'Загрузить' }}
      </button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure } from '../composables/useFastDealCard'
import { fileKindLabel, formatFileSize, vehicleTitle } from '../composables/fastDealCardFormat'
import type { FastDealCard, FastDealFileKind, FastDealLcApplication, FastDealVehicle } from '../types'
import FastDealCardError from './FastDealCardError.vue'
import FastDealCardField from './FastDealCardField.vue'

const MAX_FILES = 20
const MAX_BYTES = 50 * 1024 * 1024
const OPEN_STATUSES = ['pending_review', 'offer_sent', 'selected_by_dealer']

interface KindOption {
  value: FastDealFileKind
  label: string
  disabledReason?: string
}

const props = defineProps<{ deal: FastDealCard; initialKind?: FastDealFileKind; vehicle?: FastDealVehicle }>()
const emit = defineEmits<{ close: [] }>()

const ctx = useFastDealCardContext()

const openApplications = computed<FastDealLcApplication[]>(() => props.deal.lc_applications.filter(item => OPEN_STATUSES.includes(item.status)))
/** DD: the dealer addresses an additional document to chosen invited leasing companies. */
const needsAddressees = computed(() => ctx.isDD.value && ctx.party.value === 'initiator')

/**
 * Only kinds the server accepts for this party are offered:
 * deal_main — the initiator and the DL dealer (never a DD leasing company: competitors would see it);
 * deal_additional — everyone who uploads (the DD dealer must address open invitations);
 * vehicle_offer / lc_offer_pdf — DD, invited leasing company only.
 */
const kindOptions = computed<KindOption[]>(() => {
  const party = ctx.party.value
  const options: KindOption[] = []
  if (party === 'initiator' || (party === 'dealer' && ctx.isDL.value)) {
    options.push({ value: 'deal_main', label: fileKindLabel('deal_main') })
  }
  if (party === 'initiator' || party === 'dealer' || party === 'leasing') {
    options.push({
      value: 'deal_additional',
      label: fileKindLabel('deal_additional'),
      disabledReason: needsAddressees.value && !openApplications.value.length ? 'Доступно после отправки' : undefined,
    })
  }
  if (party === 'leasing' && ctx.isDD.value) {
    const own = ctx.ownApplication.value
    options.push({
      value: 'vehicle_offer',
      label: fileKindLabel('vehicle_offer'),
      disabledReason: !own || !OPEN_STATUSES.includes(own.status) || !ctx.activeVehicles.value.length ? 'Недоступно для вашего приглашения' : undefined,
    })
    options.push({
      value: 'lc_offer_pdf',
      label: fileKindLabel('lc_offer_pdf'),
      disabledReason: own?.status === 'pending_review' ? undefined : 'Только до отправки КП',
    })
  }
  return options
})

const firstEnabled = () => kindOptions.value.find(option => !option.disabledReason)?.value ?? 'deal_additional'
const kind = ref<FastDealFileKind>(
  props.initialKind && kindOptions.value.some(option => option.value === props.initialKind && !option.disabledReason)
    ? props.initialKind
    : firstEnabled(),
)
const vehicleId = ref(props.vehicle?.id ?? '')
const addressees = ref<string[]>([])
const files = ref<File[]>([])
const local = reactive<Record<string, string>>({})
const serverError = ref<ActionFailure | null>(null)

const limitsHint = `До ${MAX_FILES} файлов за раз, каждый не более 50 МБ, пустые файлы не принимаются`
const kindHint = computed(() => {
  switch (kind.value) {
    case 'deal_main':
      return 'Основные документы видны дилеру и допущенным сторонам сделки.'
    case 'deal_additional':
      if (needsAddressees.value) return 'Дополнительные документы видят только вы, дилер-инициатор и выбранные лизинговые компании.'
      return ctx.party.value === 'leasing' ? 'Документ получит дилер сделки.' : 'Дополнительные документы видны только вам и вашему контрагенту.'
    case 'vehicle_offer':
      return 'Коммерческое предложение по конкретной единице. Видно дилеру и вам; загружать его не обязательно.'
    case 'lc_offer_pdf':
      return 'PDF привязывается к вашему приглашению. Чтобы приложить его к КП, загрузите файл в форме «Сделать КП».'
    default:
      return ''
  }
})

const errorOf = (field: string): string => (serverError.value?.field === field ? serverError.value.detail : '')
// Only the fields that are on screen for the chosen kind are shown at their input.
const renderedFields = computed(() => {
  const fields = ['kind', 'files']
  if (kind.value === 'deal_additional' && needsAddressees.value) fields.push('addressee_company_ids')
  if (kind.value === 'vehicle_offer') fields.push('fast_deal_vehicle_id')
  return fields
})
const generalError = computed(() =>
  serverError.value && !(serverError.value.field && renderedFields.value.includes(serverError.value.field)) ? serverError.value : null,
)

function onFiles(event: Event) {
  const input = event.target as HTMLInputElement
  files.value = [...files.value, ...Array.from(input.files ?? [])]
  input.value = ''
  local.files = ''
}

function removeFile(index: number) {
  files.value = files.value.filter((_, position) => position !== index)
}

function toggleAddressee(id: string) {
  addressees.value = addressees.value.includes(id) ? addressees.value.filter(value => value !== id) : [...addressees.value, id]
}

function validate(): boolean {
  for (const key of Object.keys(local)) delete local[key]
  if (!files.value.length) local.files = 'Выберите файлы для загрузки'
  else if (files.value.length > MAX_FILES) local.files = `За один раз можно загрузить не более ${MAX_FILES} файлов`
  else if (files.value.some(file => file.size === 0)) local.files = 'Пустые файлы не принимаются'
  else if (files.value.some(file => file.size > MAX_BYTES)) local.files = 'Размер файла не должен превышать 50 МБ'
  if (kind.value === 'deal_additional' && needsAddressees.value && !addressees.value.length) local.addressees = 'Выберите хотя бы одну лизинговую компанию'
  if (kind.value === 'vehicle_offer' && !vehicleId.value) local.vehicle = 'Выберите позицию'
  return Object.keys(local).length === 0
}

async function submit() {
  serverError.value = null
  if (!validate()) return
  // Only the fields the kind uses are sent: the server refuses extras.
  const payload: Parameters<typeof ctx.api.uploadFiles>[2] = { kind: kind.value, files: files.value }
  if (kind.value === 'deal_additional' && needsAddressees.value) payload.addresseeCompanyIds = addressees.value
  if (kind.value === 'vehicle_offer') payload.fastDealVehicleId = vehicleId.value
  if (kind.value === 'lc_offer_pdf' && ctx.ownApplication.value) payload.leasingApplicationId = ctx.ownApplication.value.id
  const result = await ctx.run((etag, card) => ctx.api.uploadFiles(card.id, etag, payload))
  if (result.ok) emit('close')
  else serverError.value = result.error
}
</script>
