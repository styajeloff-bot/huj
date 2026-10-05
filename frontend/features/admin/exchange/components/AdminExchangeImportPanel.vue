<template>
  <div class="space-y-8">
    <div>
      <h2 class="text-xl font-semibold text-gray-900">Биржа ТС — импорт</h2>
      <p class="mt-1 text-sm text-gray-600">
        Асинхронная загрузка заявок и ставок биржи из CSV-файлов
      </p>
    </div>

    <!-- Exchange requests -->
    <div class="card">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h3 class="text-lg font-medium text-gray-900">Заявки биржи</h3>
          <p class="text-sm text-gray-500">Импорт заявок лизинговых компаний</p>
        </div>
        <label class="btn-secondary text-sm cursor-pointer">
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0l-4 4m4-4v12"></path>
          </svg>
          Загрузить CSV
          <input type="file" accept=".csv" class="hidden" @change="importRequestsCsv">
        </label>
      </div>
      <ImportProgress
        :uploading="requestsImport.uploading.value"
        :finished="requestsImport.finished.value"
        :status="requestsImport.status.value"
        :filename="requestsImport.filename.value"
        :progress="requestsImport.progress.value"
        :rows-total="requestsImport.rowsTotal.value"
        :rows-done="requestsImport.rowsDone.value"
        :errors-count="requestsImport.errorsCount.value"
        :error-sample="requestsImport.errorSample.value"
        :error-message="requestsImport.errorMessage.value"
      />
    </div>

    <!-- Exchange bids -->
    <div class="card">
      <div class="flex items-center justify-between mb-4">
        <div>
          <h3 class="text-lg font-medium text-gray-900">Ставки биржи</h3>
          <p class="text-sm text-gray-500">Импорт ставок дилеров по заявкам</p>
        </div>
        <label class="btn-secondary text-sm cursor-pointer">
          <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0l-4 4m4-4v12"></path>
          </svg>
          Загрузить CSV
          <input type="file" accept=".csv" class="hidden" @change="importBidsCsv">
        </label>
      </div>
      <ImportProgress
        :uploading="bidsImport.uploading.value"
        :finished="bidsImport.finished.value"
        :status="bidsImport.status.value"
        :filename="bidsImport.filename.value"
        :progress="bidsImport.progress.value"
        :rows-total="bidsImport.rowsTotal.value"
        :rows-done="bidsImport.rowsDone.value"
        :errors-count="bidsImport.errorsCount.value"
        :error-sample="bidsImport.errorSample.value"
        :error-message="bidsImport.errorMessage.value"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import ImportProgress from '~/features/admin/shared/components/ImportProgress.vue'
import { useCsvImport } from '~/features/admin/shared/composables/useCsvImport'

const requestsImport = useCsvImport()
const bidsImport = useCsvImport()

const importRequestsCsv = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await requestsImport.upload('/api/v1/exchange/requests/import', file)
  input.value = ''
}

const importBidsCsv = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await bidsImport.upload('/api/v1/exchange/bids/import', file)
  input.value = ''
}
</script>
