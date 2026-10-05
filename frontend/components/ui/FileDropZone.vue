<template>
  <div data-storefront-block="shared.form"
    ref="dropZone"
    @dragenter="onDragEnter"
    @dragover="onDragOver"
    @dragleave="onDragLeave"
    @drop="onDrop"
    :class="[
      'relative border-2 border-dashed rounded-xl transition-all duration-200 ease-in-out',
      isDragOver 
        ? 'border-[color:var(--storefront-border,#60a5fa)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] scale-102'
        : selectedFile 
          ? 'border-[color:var(--storefront-success-border,#86efac)] bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))]'
          : 'border-[color:var(--storefront-border,#d1d5db)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] hover:border-[color:var(--storefront-border,#9ca3af)] hover:bg-[color:rgb(var(--storefront-surface-muted-rgb,243_244_246)/var(--tw-bg-opacity,1))]'
    ]"
  >
    <input
      ref="fileInput"
      type="file"
      :accept="accept"
      :multiple="multiple"
      @change="onFileSelect"
      class="storefront-control sr-only"
    >
    
    <div 
      :class="compact ? 'px-4 py-6' : 'px-6 py-10'"
      @click="!selectedFile || multiple ? triggerFileSelect() : null"
      :style="{ cursor: (!selectedFile || multiple) ? 'pointer' : 'default' }"
    >
      <div v-if="!selectedFile || multiple" class="text-center">
        <div :class="compact ? 'mx-auto w-10 h-10 mb-2' : 'mx-auto w-16 h-16 mb-4'">
          <svg
            :class="[
              'w-full h-full transition-colors drop-zone-icon',
              isDragOver ? 'text-[color:var(--storefront-icon,#3b82f6)]' : 'text-[color:var(--storefront-icon,#9ca3af)]'
            ]" 
            fill="none" 
            stroke="currentColor" 
            viewBox="0 0 24 24"
          >
            <path 
              stroke-linecap="round" 
              stroke-linejoin="round" 
              stroke-width="1.5" 
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
        </div>
        
        <div class="space-y-1">
          <p :class="[
            'font-medium transition-colors',
            compact ? 'text-sm' : 'text-lg',
            isDragOver ? 'text-[color:var(--storefront-text-muted,#2563eb)]' : 'text-[color:var(--storefront-text,#374151)]'
          ]">
            {{ isDragOver ? dropText : normalText }}
          </p>
          <p :class="compact ? 'text-xs text-[color:var(--storefront-text-muted,#6b7280)]' : 'text-sm text-[color:var(--storefront-text-muted,#6b7280)]'">
            или 
            <button
              type="button"
              @click.stop="triggerFileSelect"
              class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#2563eb)] hover:text-[color:var(--storefront-ghost-hover-foreground,#1d4ed8)] font-medium underline focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-opacity-50 rounded"
            >
              выберите {{ multiple ? 'файлы' : 'файл' }}
            </button>
          </p>
          <p :class="compact ? 'text-xs text-[color:var(--storefront-text-muted,#9ca3af)]' : 'text-xs text-[color:var(--storefront-text-muted,#9ca3af)]'">
            {{ acceptText }}
          </p>
        </div>
      </div>
      
      <!-- Single File Preview -->
      <div v-if="selectedFile && !multiple" class="text-center file-selected-animation">
        <div 
          @click.stop="triggerFileSelect"
          class="cursor-pointer"
          title="Нажмите для замены файла"
        >
          <div :class="compact ? 'mx-auto w-10 h-10 mb-2' : 'mx-auto w-16 h-16 mb-4'" class="flex items-center justify-center bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] rounded-full hover:bg-[color:rgb(var(--storefront-success-hover-rgb,187_247_208)/var(--tw-bg-opacity,1))] transition-colors">
            <svg :class="compact ? 'w-5 h-5' : 'w-8 h-8'" class="text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
          </div>
          <p :class="compact ? 'text-sm' : 'text-lg'" class="font-medium text-[color:var(--storefront-success-text,#15803d)] mb-1 hover:text-[color:var(--storefront-success-text,#166534)]">Файл выбран</p>
          <p :class="compact ? 'text-xs' : 'text-sm'" class="text-[color:var(--storefront-text-muted,#4b5563)] mb-2 hover:text-[color:var(--storefront-text,#374151)]">{{ selectedFile.name }}</p>
          <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ formatFileSize(selectedFile.size) }}</p>
        </div>
        
        <div class="mt-3 flex justify-center space-x-2">
          <button
            type="button"
            @click.stop="triggerFileSelect"
            :class="compact ? 'px-2 py-1 text-xs' : 'px-3 py-1 text-xs'"
            class="storefront-action-ghost inline-flex items-center font-medium text-[color:var(--storefront-primary-foreground,#2563eb)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-primary-border,#bfdbfe)] rounded-md hover:bg-[color:rgb(var(--storefront-selected-rgb,219_234_254)/var(--tw-bg-opacity,1))] transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-opacity-50"
          >
            <svg :class="compact ? 'w-3 h-3 mr-1' : 'w-3 h-3 mr-1'" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/>
            </svg>
            Заменить
          </button>
          
          <button
            type="button"
            @click.stop="clearFile"
            :class="compact ? 'px-2 py-1 text-xs' : 'px-3 py-1 text-xs'"
            class="storefront-action-ghost inline-flex items-center font-medium text-[color:var(--storefront-destructive-foreground,#dc2626)] bg-[color:rgb(var(--storefront-destructive-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-destructive-border,#fecaca)] rounded-md hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_226_226)/var(--tw-bg-opacity,1))] transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#ef4444)] focus:ring-opacity-50"
          >
            <svg :class="compact ? 'w-3 h-3 mr-1' : 'w-3 h-3 mr-1'" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
            </svg>
            Удалить
          </button>
        </div>
      </div>
      
      <!-- Multiple Files Preview -->
      <div v-if="selectedFiles.length > 0 && multiple" class="space-y-2 file-selected-animation">
        <div class="text-center mb-3">
          <p :class="compact ? 'text-sm' : 'text-lg'" class="font-medium text-[color:var(--storefront-success-text,#15803d)]">
            Выбрано файлов: {{ selectedFiles.length }}
          </p>
        </div>
        
        <div class="max-h-32 overflow-y-auto space-y-1">
          <div 
            v-for="(file, index) in selectedFiles" 
            :key="index"
            class="flex items-center justify-between p-2 bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border"
          >
            <div class="flex items-center space-x-2">
              <svg class="w-4 h-4 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
              </svg>
              <div>
                <p class="text-xs font-medium text-[color:var(--storefront-text,#111827)]">{{ file.name }}</p>
                <p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ formatFileSize(file.size) }}</p>
              </div>
            </div>
            <button
              type="button"
              @click.stop="removeFile(index)"
              class="storefront-action-ghost p-1 text-[color:var(--storefront-destructive-foreground,#ef4444)] hover:text-[color:var(--storefront-destructive-hover-foreground,#b91c1c)] hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_242_242)/var(--tw-bg-opacity,1))] rounded focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#ef4444)] focus:ring-opacity-50 transition-colors"
              title="Удалить файл"
            >
              <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>
        
        <div class="text-center">
          <button
            type="button"
            @click.stop="clearAllFiles"
            class="storefront-action-ghost text-xs font-medium text-[color:var(--storefront-destructive-foreground,#dc2626)] bg-[color:rgb(var(--storefront-destructive-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-destructive-border,#fecaca)] rounded px-2 py-1 hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,254_226_226)/var(--tw-bg-opacity,1))] transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#ef4444)] focus:ring-opacity-50"
          >
            Очистить все
          </button>
          
          <button
            type="button"
            @click.stop="triggerFileSelect"
            class="storefront-action-ghost ml-2 text-xs font-medium text-[color:var(--storefront-primary-foreground,#2563eb)] bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-primary-border,#bfdbfe)] rounded px-2 py-1 hover:bg-[color:rgb(var(--storefront-selected-rgb,219_234_254)/var(--tw-bg-opacity,1))] transition-colors focus:outline-none focus:ring-2 focus:ring-[color:var(--storefront-focus,#3b82f6)] focus:ring-opacity-50"
          >
            Добавить еще
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
const props = defineProps({
  accept: {
    type: String,
  default: '.pdf,.doc,.docx,.pptx,.jpg,.jpeg,.png'
  },
  multiple: {
    type: Boolean,
    default: false
  },
  maxSize: {
    type: Number,
    default: 10 * 1024 * 1024 // 10MB
  },
  compact: {
    type: Boolean,
    default: false
  },
  normalText: {
    type: String,
    default: 'Перетащите файл сюда'
  },
  dropText: {
    type: String,
    default: 'Отпустите файл для загрузки'
  },
  acceptText: {
    type: String,
    default: 'PDF, DOC, DOCX, PPTX, JPG, PNG • до 10 МБ'
  }
})

const emit = defineEmits(['file-selected', 'files-selected', 'file-removed', 'error'])

// State
const isDragOver = ref(false)
const dragCounter = ref(0)
const selectedFile = ref<File | null>(null)
const selectedFiles = ref<File[]>([])
const dropZone = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)

// Methods
const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

const validateFile = (file: File) => {
  // Check file size
  if (file.size > props.maxSize) {
    emit('error', `Размер файла "${file.name}" превышает ${formatFileSize(props.maxSize)}`)
    return false
  }
  
  // Check file type if accept is specified
  if (props.accept) {
    const allowedTypes = props.accept.split(',').map(type => type.trim().toLowerCase())
    const extension = '.' + (file.name.split('.').pop() || '').toLowerCase()
    
    if (!allowedTypes.includes(extension)) {
      emit('error', `Неподдерживаемый тип файла "${file.name}"`)
      return false
    }
  }
  
  return true
}

const triggerFileSelect = () => {
  if (fileInput.value) {
    fileInput.value.click()
  }
}

const onFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  handleFiles(files)
}

const handleFiles = (files: File[]) => {
  const validFiles = files.filter(validateFile)
  
  if (validFiles.length === 0) return
  
  if (props.multiple) {
    selectedFiles.value = [...selectedFiles.value, ...validFiles]
    emit('files-selected', selectedFiles.value)
  } else {
    selectedFile.value = validFiles[0]
    emit('file-selected', validFiles[0])
  }
}

const clearFile = () => {
  selectedFile.value = null
  if (fileInput.value) {
    fileInput.value.value = ''
  }
  emit('file-selected', null)
}

const clearAllFiles = () => {
  selectedFiles.value = []
  if (fileInput.value) {
    fileInput.value.value = ''
  }
  emit('files-selected', [])
}

const removeFile = (index: number) => {
  selectedFiles.value.splice(index, 1)
  emit('file-removed', index)
  emit('files-selected', selectedFiles.value)
}

// Drag and drop handlers
const onDragEnter = (event: DragEvent) => {
  event.preventDefault()
  event.stopPropagation()
  dragCounter.value++
  isDragOver.value = true
}

const onDragOver = (event: DragEvent) => {
  event.preventDefault()
  event.stopPropagation()
}

const onDragLeave = (event: DragEvent) => {
  event.preventDefault()
  event.stopPropagation()
  dragCounter.value--
  if (dragCounter.value === 0) {
    isDragOver.value = false
  }
}

const onDrop = (event: DragEvent) => {
  event.preventDefault()
  event.stopPropagation()
  isDragOver.value = false
  dragCounter.value = 0
  
  const files = Array.from(event.dataTransfer?.files || [])
  handleFiles(files)
}

// Expose methods for parent components
defineExpose({
  clearFile,
  clearAllFiles,
  triggerFileSelect
})
</script>
