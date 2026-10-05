<template>
  <Teleport to="body">
    <div data-storefront-block="shared.toast" class="fixed inset-x-[16px] top-[80px] z-[60] space-y-3 sm:inset-x-auto sm:right-4">
      <TransitionGroup name="toast" tag="div">
        <div
          v-for="toast in toasts"
          :key="toast.id"
          :class="getToastClass(toast.type)"
          class="relative flex max-w-full items-start space-x-3 rounded-lg p-4 shadow-lg [overflow-wrap:anywhere] sm:max-w-sm"
        >
          <!-- Icon -->
          <div class="flex-shrink-0">
            <svg v-if="toast.type === 'success'" class="w-5 h-5 text-[color:var(--storefront-success-icon,#16a34a)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
            </svg>
            <svg v-else-if="toast.type === 'error'" class="w-5 h-5 text-[color:var(--storefront-error-icon,#dc2626)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
            <svg v-else-if="toast.type === 'warning'" class="w-5 h-5 text-[color:var(--storefront-warning-icon,#ca8a04)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z"/>
            </svg>
            <svg v-else class="w-5 h-5 text-[color:var(--storefront-icon,#2563eb)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
          </div>

          <!-- Content -->
          <div class="flex-1 min-w-0">
            <h4 v-if="toast.title" class="text-[color:var(--storefront-title,inherit)] text-sm font-semibold mb-1" :class="getTextClass(toast.type)">
              {{ toast.title }}
            </h4>
            <p class="text-sm" :class="getTextClass(toast.type)">
              {{ toast.message }}
            </p>
            <button
              v-if="toast.actionText && toast.actionCallback"
              @click="toast.actionCallback"
              class="storefront-action-ghost mt-2 text-xs font-medium underline hover:no-underline"
              :class="getActionClass(toast.type)"
            >
              {{ toast.actionText }}
            </button>
          </div>

          <!-- Close Button -->
          <button
            @click="removeToast(toast.id)"
            class="storefront-action-ghost flex-shrink-0 text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)]"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
            </svg>
          </button>

        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
// Используем Pinia store вместо локального состояния
const toastStore = useToastStore()
const toasts = computed(() => toastStore.toasts)

// Methods для UI взаимодействия
const removeToast = (id: number) => {
  toastStore.removeToast(id)
}

const clearAllToasts = () => {
  toastStore.clearAllToasts()
}

// Helper functions for styling
const getToastClass = (type: string) => {
  switch (type) {
    case 'success':
      return 'bg-[color:rgb(var(--storefront-success-rgb,240_253_244)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-success-border,#bbf7d0)]'
    case 'error':
      return 'bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)]'
    case 'warning':
      return 'bg-[color:rgb(var(--storefront-warning-rgb,254_252_232)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-warning-border,#fef08a)]'
    case 'info':
    default:
      return 'bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#bfdbfe)]'
  }
}

const getTextClass = (type: string) => {
  switch (type) {
    case 'success':
      return 'text-[color:var(--storefront-success-text,#166534)]'
    case 'error':
      return 'text-[color:var(--storefront-error-text,#991b1b)]'
    case 'warning':
      return 'text-[color:var(--storefront-warning-text,#854d0e)]'
    case 'info':
    default:
      return 'text-[color:var(--storefront-text,#1e40af)]'
  }
}

const getActionClass = (type: string) => {
  switch (type) {
    case 'success':
      return 'text-[color:var(--storefront-success-text,#15803d)] hover:text-[color:var(--storefront-success-text,#14532d)]'
    case 'error':
      return 'text-[color:var(--storefront-error-text,#b91c1c)] hover:text-[color:var(--storefront-error-text,#7f1d1d)]'
    case 'warning':
      return 'text-[color:var(--storefront-warning-text,#a16207)] hover:text-[color:var(--storefront-warning-text,#713f12)]'
    case 'info':
    default:
      return 'text-[color:var(--storefront-text,#1d4ed8)] hover:text-[color:var(--storefront-text,#1e3a8a)]'
  }
}
</script>

<style scoped>
.toast-enter-active {
  transition: all 0.3s ease-out;
}

.toast-leave-active {
  transition: all 0.3s ease-in;
}

.toast-enter-from {
  transform: translateX(100%);
  opacity: 0;
}

.toast-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

.toast-move {
  transition: transform 0.3s ease;
}
</style>
