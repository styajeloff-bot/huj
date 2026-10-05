<template>
  <section class="bg-white rounded-lg shadow-sm p-6" aria-labelledby="fast-deal-files-title">
    <div class="flex items-center justify-between gap-3 flex-wrap mb-4">
      <h2 id="fast-deal-files-title" class="text-lg font-semibold text-gray-900">Документы</h2>
      <div class="flex gap-2">
        <button v-if="deal.files.length" type="button" class="btn-outline text-sm px-3 py-1.5" :disabled="archiving" @click="downloadArchive">
          {{ archiving ? 'Готовим архив…' : 'Скачать всё (ZIP)' }}
        </button>
        <button v-if="ctx.can('upload_files')" type="button" class="btn-primary text-sm px-3 py-1.5" @click="uploadOpen = true">
          Загрузить документы
        </button>
      </div>
    </div>

    <p v-if="!deal.files.length" class="text-sm text-gray-500">
      Документы не загружены. Файлы необязательны для отправки и подтверждения сделки.
    </p>
    <div v-else class="space-y-4">
      <section v-for="group in groups" :key="group.kind" :aria-label="group.label">
        <h3 class="text-sm font-semibold text-gray-700 mb-1">{{ group.label }}</h3>
        <ul class="divide-y divide-gray-100 rounded-lg border border-gray-200">
          <li v-for="file in group.files" :key="file.id" class="flex items-center justify-between gap-4 px-3 py-2 text-sm">
            <div class="min-w-0">
              <p class="truncate text-gray-900">{{ file.filename }}</p>
              <p class="text-xs text-gray-500">
                {{ formatFileSize(file.size_bytes) }} · {{ formatDateTime(file.created_at) }}
                <template v-if="ctx.companyName(file.uploaded_by_company_id)"> · от {{ ctx.companyName(file.uploaded_by_company_id) }}</template>
                <template v-if="file.addressee_company_id"> · для {{ ctx.companyName(file.addressee_company_id) || 'контрагента' }}</template>
                <template v-if="vehicleLabel(file.fast_deal_vehicle_id)"> · {{ vehicleLabel(file.fast_deal_vehicle_id) }}</template>
              </p>
            </div>
            <button type="button" class="text-blue-600 hover:text-blue-700 shrink-0" @click="download(file.id, file.filename)">Скачать</button>
          </li>
        </ul>
      </section>
    </div>
    <p v-if="error" role="alert" class="mt-3 text-sm text-red-600">{{ error }}</p>

    <FastDealFilesUploadModal v-if="uploadOpen" :deal="deal" @close="uploadOpen = false" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { parseFastDealError } from '../api/fastDealsApi'
import { useFastDealCardContext } from '../composables/useFastDealCard'
import { fileKindLabel, formatDateTime, formatFileSize } from '../composables/fastDealCardFormat'
import type { FastDealCard, FastDealFile, FastDealFileKind } from '../types'
import FastDealFilesUploadModal from './FastDealFilesUploadModal.vue'

const KIND_ORDER: FastDealFileKind[] = ['deal_main', 'deal_additional', 'lc_offer_pdf', 'vehicle_offer']

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()
const uploadOpen = ref(false)
const archiving = ref(false)
const error = ref('')

const groups = computed(() =>
  KIND_ORDER
    .map(kind => ({ kind, label: fileKindLabel(kind), files: props.deal.files.filter((file: FastDealFile) => file.kind === kind) }))
    .filter(group => group.files.length > 0),
)

const vehicleLabel = (vehicleId: string | null | undefined): string => {
  if (!vehicleId) return ''
  const vehicle = props.deal.vehicles.find(item => item.id === vehicleId)
  return vehicle ? `VIN ${vehicle.vin}` : ''
}

async function download(fileId: string, filename: string) {
  error.value = ''
  try {
    await ctx.api.downloadFile(props.deal.id, fileId, filename)
  } catch (failure) {
    error.value = parseFastDealError(failure).detail
  }
}

async function downloadArchive() {
  error.value = ''
  archiving.value = true
  try {
    await ctx.api.downloadArchive(props.deal.id, `${props.deal.display_number}.zip`)
  } catch (failure) {
    error.value = parseFastDealError(failure).detail
  } finally {
    archiving.value = false
  }
}
</script>
