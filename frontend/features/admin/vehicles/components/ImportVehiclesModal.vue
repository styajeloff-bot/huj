<template>
  <Modal :show="isOpen" @close="$emit('close')" size="xl" title="Импорт автомобилей">
    <div class="space-y-6">
      <div class="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors"
        :class="{ 'border-blue-500 bg-blue-50': isDragging }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="handleDrop">
        
        <svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        
        <div class="mt-4">
          <label class="btn-primary cursor-pointer inline-flex px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors">
            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            Выбрать файл
            <input type="file" class="hidden" accept=".xlsx,.xls" @change="handleFileSelect" ref="fileInput">
          </label>
          <p class="mt-2 text-xs text-gray-500">или перетащите файл сюда</p>
        </div>
        
        <p class="mt-2 text-sm text-gray-600">
          Поддерживаемые форматы: XLSX, XLS
        </p>
      </div>

      <div class="bg-blue-50 p-4 rounded-lg">
        <div class="flex items-start">
          <svg class="w-5 h-5 text-blue-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
          </svg>
          <div class="ml-3">
            <h3 class="text-sm font-medium text-blue-800">Шаблон для импорта</h3>
            <div class="text-sm text-blue-700 mt-1">
              Скачайте шаблон Excel файла с правильной структурой данных
            </div>
            <button
              @click="downloadTemplate"
              class="mt-2 text-sm text-blue-600 hover:text-blue-500 underline"
            >
              Скачать шаблон
            </button>
          </div>
        </div>
      </div>

      <div v-if="selectedFile" class="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <svg class="w-8 h-8 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            <div>
              <p class="text-sm font-medium text-gray-900">{{ selectedFile.name }}</p>
              <p class="text-xs text-gray-600">{{ formatFileSize(selectedFile.size) }}</p>
            </div>
          </div>
          <button @click="clearFile" class="text-red-600 hover:text-red-700">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div v-if="previewData" class="space-y-4">
        <div v-if="previewData.errors && previewData.errors.length > 0" class="bg-red-50 border border-red-200 rounded-lg p-4">
          <div class="flex items-start">
            <svg class="w-6 h-6 text-red-600 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div class="flex-1">
              <h4 class="font-semibold text-red-900 mb-2">Ошибки в файле:</h4>
              <ul class="list-disc list-inside space-y-1 text-sm text-red-700">
                <li v-for="(error, index) in previewData.errors" :key="index">{{ error }}</li>
              </ul>
            </div>
          </div>
        </div>

        <div v-if="previewData.warnings && previewData.warnings.length > 0" class="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <div class="flex items-start">
            <svg class="w-6 h-6 text-yellow-600 mr-3 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div class="flex-1">
              <h4 class="font-semibold text-yellow-900 mb-2">Предупреждения:</h4>
              <ul class="list-disc list-inside space-y-1 text-sm text-yellow-700">
                <li v-for="(warning, index) in previewData.warnings" :key="index">{{ warning }}</li>
              </ul>
            </div>
          </div>
        </div>

        <div class="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <h3 class="text-lg font-semibold text-gray-900 mb-3">Предварительный просмотр</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <p class="text-gray-600">Всего строк:</p>
              <p class="font-semibold text-gray-900">{{ previewData.totalRows }}</p>
            </div>
            <div>
              <p class="text-gray-600">Марок:</p>
              <p class="font-semibold text-blue-600">{{ previewData.uniqueMarks }}</p>
            </div>
            <div>
              <p class="text-gray-600">Моделей:</p>
              <p class="font-semibold text-blue-600">{{ previewData.uniqueModels }}</p>
            </div>
            <div>
              <p class="text-gray-600">Авто к загрузке:</p>
              <p class="font-semibold" :class="previewData.vehiclesCount > 0 ? 'text-green-600' : 'text-red-600'">
                {{ previewData.vehiclesCount }}
              </p>
            </div>
          </div>
          <div v-if="previewData.rowsWithoutVin > 0" class="mt-3 pt-3 border-t border-gray-200">
            <p class="text-sm text-red-600">
              <svg class="w-4 h-4 inline mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              Строк без VIN (будут пропущены): {{ previewData.rowsWithoutVin }}
            </p>
          </div>
        </div>

        <div v-if="previewData.sampleData && previewData.sampleData.length > 0" class="overflow-x-auto">
          <h4 class="text-sm font-medium text-gray-900 mb-2">Первые записи:</h4>
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <thead class="bg-gray-50">
              <tr>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">VIN</th>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Марка</th>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Модель</th>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Поколение</th>
                <th class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Цена</th>
              </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
              <tr v-for="(row, index) in previewData.sampleData" :key="index" 
                :class="!row.hasVin ? 'bg-red-50' : ''">
                <td class="px-3 py-2 whitespace-nowrap" :class="!row.hasVin ? 'text-red-600 font-medium' : ''">
                  {{ row.vin }}
                  <svg v-if="!row.hasVin" class="w-4 h-4 inline ml-1 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </td>
                <td class="px-3 py-2 whitespace-nowrap">{{ row.mark }}</td>
                <td class="px-3 py-2 whitespace-nowrap">{{ row.model }}</td>
                <td class="px-3 py-2 whitespace-nowrap">{{ row.generation }}</td>
                <td class="px-3 py-2 whitespace-nowrap">{{ formatPrice(row.price) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="uploading" class="space-y-2">
        <div class="flex justify-between text-sm text-gray-600">
          <span>{{ uploadStatus }}</span>
          <span>{{ uploadProgress }}%</span>
        </div>
        <div class="w-full bg-gray-200 rounded-full h-2">
          <div class="bg-blue-600 h-2 rounded-full transition-all duration-300" 
            :style="{ width: uploadProgress + '%' }"></div>
        </div>
      </div>

      <div v-if="uploadResult" class="rounded-lg p-4"
        :class="uploadResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'">
        <div class="flex items-start">
          <svg v-if="uploadResult.success" class="w-6 h-6 text-green-600 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <svg v-else class="w-6 h-6 text-red-600 mr-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div class="flex-1">
            <h4 class="font-semibold" :class="uploadResult.success ? 'text-green-900' : 'text-red-900'">
              {{ uploadResult.success ? 'Импорт успешно завершен!' : 'Ошибка при импорте' }}
            </h4>
            <p class="mt-1 text-sm" :class="uploadResult.success ? 'text-green-700' : 'text-red-700'">
              {{ uploadResult.message }}
            </p>
            <div v-if="uploadResult.stats" class="mt-3 text-sm space-y-1">
              <p>Добавлено: {{ uploadResult.stats.inserted }}</p>
              <p>Обновлено: {{ uploadResult.stats.updated }}</p>
              <p>Пропущено: {{ uploadResult.stats.skipped }}</p>
            </div>
          </div>
        </div>
      </div>

      <div class="flex items-center justify-between pt-4 border-t border-gray-200">
        <div class="flex-1">
          <p v-if="previewData && previewData.vehiclesCount === 0" class="text-sm text-red-600">
            В файле нет автомобилей с корректными данными для загрузки
          </p>
        </div>
        <div class="flex space-x-3">
          <button 
            @click="$emit('close')"
            class="px-4 py-2 text-gray-700 bg-gray-200 hover:bg-gray-300 rounded-lg transition-colors"
          >
            {{ uploadResult ? 'Закрыть' : 'Отмена' }}
          </button>
          <button 
            v-if="!uploadResult"
            @click="uploadCatalog" 
            :disabled="!canUpload || uploading"
            class="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <svg v-if="uploading" class="animate-spin -ml-1 mr-2 h-5 w-5 text-white inline" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            {{ uploading ? 'Загрузка...' : 'Загрузить' }}
          </button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useToast } from '@/composables/useToast'
import { useFormatPrice } from '@/composables/useFormatPrice'
import Modal from '@/components/ui/Modal.vue'

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  }
})

const emit = defineEmits(['close', 'success'])

const { showToast } = useToast()
const { formatPrice } = useFormatPrice()

import type { ImportUploadResult, CatalogPreviewData } from '~/types/admin'

const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const isDragging = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadStatus = ref('')
const uploadResult = ref<ImportUploadResult | null>(null)
const previewData = ref<CatalogPreviewData | null>(null)

const canUpload = computed(() => {
  if (!selectedFile.value || !previewData.value) return false
  if (previewData.value.vehiclesCount === 0) return false
  return true
})

const handleFileSelect = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) {
    processFile(file)
  }
}

const handleDrop = (event: DragEvent) => {
  isDragging.value = false
  const file = event.dataTransfer?.files[0]
  if (file) {
    if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
      processFile(file)
    } else {
      showToast.error('Пожалуйста, выберите Excel файл (.xlsx или .xls)')
    }
  }
}

const processFile = async (file: File) => {
  selectedFile.value = file
  uploadResult.value = null
  
  try {
    const formData = new FormData()
    formData.append('file', file)
    
    const response = await $fetch('/api/v1/distributor/vehicles/import-preview', {
      method: 'POST',
      body: formData
    })
    
    previewData.value = response as CatalogPreviewData
  } catch (error: unknown) {
    console.error('Ошибка при создании превью:', error)
    showToast.error('Не удалось загрузить превью файла')
  }
}

const clearFile = () => {
  selectedFile.value = null
  previewData.value = null
  uploadResult.value = null
  uploadProgress.value = 0
  if (fileInput.value) {
    fileInput.value.value = ''
  }
}

const downloadTemplate = async () => {
  try {
    const response = await fetch('/api/v1/distributor/vehicles/import-template', {
      credentials: 'include'
    })
    
    if (!response.ok) throw new Error('Ошибка загрузки шаблона')
    
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'vehicle_import_template.xlsx'
    link.click()
    URL.revokeObjectURL(url)
    
  } catch (error: unknown) {
    console.error('Ошибка при скачивании шаблона:', error)
    showToast.error('Ошибка при скачивании шаблона')
  }
}

const uploadCatalog = async () => {
  if (!selectedFile.value) return
  
  uploading.value = true
  uploadProgress.value = 0
  uploadStatus.value = 'Загрузка файла...'
  uploadResult.value = null
  
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    
    const progressInterval = setInterval(() => {
      if (uploadProgress.value < 90) {
        uploadProgress.value += 5
      }
    }, 500)
    
    uploadStatus.value = 'Обработка данных...'
    
    const response = await $fetch('/api/v1/distributor/vehicles/import', {
      method: 'POST',
      body: formData
    })
    
    clearInterval(progressInterval)
    uploadProgress.value = 100
    uploadStatus.value = 'Завершено!'
    
    const data = response as { message?: string; stats?: { inserted: number; updated: number; skipped: number } }
    uploadResult.value = {
      success: true,
      message: data.message || 'Импорт успешно завершен',
      stats: data.stats
    }
    
    showToast.success('Импорт успешно завершен')
    emit('success')
    
  } catch (error: unknown) {
    console.error('Ошибка при загрузке:', error)
    const e = error as { data?: { error?: string } }
    uploadResult.value = {
      success: false,
      message: e.data?.error || 'Произошла ошибка при импорте'
    }
    showToast.error('Ошибка при импорте')
  } finally {
    uploading.value = false
  }
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}
</script>
