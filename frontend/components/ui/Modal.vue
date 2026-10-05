<template>
  <span ref="themeOrigin" hidden aria-hidden="true"></span>
  <Teleport to="body" :disabled="!teleportReady">
    <Transition
      enter-active-class="transition ease-out duration-300"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition ease-in duration-200"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
      @after-leave="restoreFocus"
    >
      <div
        v-if="show"
        ref="modalRoot"
        :style="inheritedColors"
        class="fixed inset-0 z-[230] overflow-y-auto"
        @keydown="handleKeydown"
      >
        <div data-storefront-block="shared.modal" class="contents">
        <!-- Backdrop -->
        <div class="fixed inset-0 bg-[color:rgb(var(--storefront-overlay-rgb,0_0_0)/var(--tw-bg-opacity,1))] bg-opacity-50 transition-opacity"></div>

        <!-- Modal Content -->
        <div
          class="flex min-h-full items-center justify-center p-4"
          @mousedown.self.left="handleOverlayClick"
        >
          <Transition
            enter-active-class="transition ease-out duration-300"
            enter-from-class="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
            enter-to-class="opacity-100 translate-y-0 sm:scale-100"
            leave-active-class="transition ease-in duration-200"
            leave-from-class="opacity-100 translate-y-0 sm:scale-100"
            leave-to-class="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
          >
            <div
              v-if="show"
              ref="dialog"
              role="dialog"
              aria-modal="true"
              tabindex="-1"
              :aria-labelledby="title ? titleId : undefined"
              :aria-label="title ? undefined : 'Диалоговое окно'"
              :class="[
                'relative transform bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg shadow-xl transition-all',
                sizeClasses[size],
                maxHeightClass
              ]"
              @click.stop
            >
              <!-- Header -->
              <div v-if="showHeader" class="px-6 py-4 border-b border-[color:var(--storefront-border,#e5e7eb)]">
                <div class="flex items-center justify-between">
                  <div>
                    <h3 :id="titleId" class="text-lg font-semibold text-[color:var(--storefront-title,#111827)]">
                      {{ title }}
                    </h3>
                    <p v-if="subtitle" class="text-sm text-[color:var(--storefront-text-muted,#4b5563)] mt-1">
                      {{ subtitle }}
                    </p>
                  </div>
                  <button
                    v-if="closable"
                    type="button"
                    aria-label="Закрыть"
                    @click="close"
                    class="storefront-action-ghost text-[color:var(--storefront-ghost-foreground,#9ca3af)] hover:text-[color:var(--storefront-ghost-hover-foreground,#4b5563)] transition-colors"
                  >
                    <XMarkIcon class="h-6 w-6" />
                  </button>
                </div>
              </div>

              <!-- Body -->
              <div :class="['px-6 py-4', bodyClass]">
                <slot />
              </div>

              <!-- Footer -->
              <div v-if="showFooter" class="px-6 py-4 border-t border-[color:var(--storefront-border,#e5e7eb)] bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-b-lg">
                <div class="flex items-center justify-end space-x-3">
                  <slot name="footer">
                    <button
                      v-if="showCancelButton"
                      @click="cancel"
                      class="btn-secondary"
                    >
                      {{ cancelText }}
                    </button>
                    <button
                      v-if="showConfirmButton"
                      @click="confirm"
                      :disabled="confirmDisabled"
                      :class="[
                        'btn-primary',
                        confirmDisabled ? 'opacity-50 cursor-not-allowed' : ''
                      ]"
                    >
                      {{ confirmText }}
                    </button>
                  </slot>
                </div>
              </div>
            </div>
          </Transition>
        </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { XMarkIcon } from '@heroicons/vue/24/outline'
import { acquireBodyScrollLock, registerModalRoot } from './modalIsolation'
import { useStorefrontTeleportContext } from '~/features/storefront'

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String },
  subtitle: { type: String },
  size: { 
    type: String, 
    default: 'md',
    validator: (value: string) => ['xs', 'sm', 'md', 'lg', 'xl', '2xl', '3xl', '4xl', '5xl', '6xl', 'full'].includes(value)
  },
  maxHeight: { type: String, default: 'screen' },
  closable: { type: Boolean, default: true },
  closeOnOverlay: { type: Boolean, default: true },
  showHeader: { type: Boolean, default: true },
  showFooter: { type: Boolean, default: false },
  showCancelButton: { type: Boolean, default: true },
  showConfirmButton: { type: Boolean, default: true },
  cancelText: { type: String, default: 'Отмена' },
  confirmText: { type: String, default: 'Подтвердить' },
  confirmDisabled: { type: Boolean, default: false },
  bodyClass: { type: String, default: '' }
})

const emit = defineEmits(['close', 'cancel', 'confirm', 'after-close'])
const titleId = useId()
const themeOrigin = ref<HTMLElement | null>(null)
const { inheritedColors, teleportReady } = useStorefrontTeleportContext(themeOrigin)
const modalRoot = ref<HTMLElement | null>(null)
const dialog = ref<HTMLElement | null>(null)

let releaseBodyScroll: (() => void) | null = null
let releaseModalIsolation: (() => void) | null = null
let previousFocus: HTMLElement | null = null
let activeModalRoot: HTMLElement | null = null
let pendingPreviousFocus: HTMLElement | null = null
let pendingModalRoot: HTMLElement | null = null
let focusRestoreTimer: number | null = null
let active = false

const sizeClasses: Record<string, string> = {
  xs: 'max-w-xs w-full',
  sm: 'max-w-sm w-full',
  md: 'max-w-md w-full',
  lg: 'max-w-lg w-full',
  xl: 'max-w-xl w-full',
  '2xl': 'max-w-2xl w-full',
  '3xl': 'max-w-3xl w-full',
  '4xl': 'max-w-4xl w-full',
  '5xl': 'max-w-5xl w-full',
  '6xl': 'max-w-6xl w-full',
  full: 'max-w-[1920px] w-full mx-4'
}

const maxHeightClass = computed(() => {
  return props.maxHeight === 'screen'
    ? 'max-h-[calc(100dvh-2rem)] overflow-y-auto'
    : `max-h-${props.maxHeight}`
})

const handleOverlayClick = () => {
  if (props.closeOnOverlay) {
    close()
  }
}

const close = () => {
  emit('close')
}

const cancel = () => {
  emit('cancel')
  close()
}

const confirm = () => {
  emit('confirm')
}

const focusableElements = (root: HTMLElement | null): HTMLElement[] => root
  ? [...root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )].filter(element => element.getClientRects().length > 0)
  : []

const underlyingDialog = (excludedRoot: HTMLElement | null): HTMLElement | null =>
  [...document.querySelectorAll<HTMLElement>('[role="dialog"], [role="alertdialog"]')]
    .find(candidate => !excludedRoot?.contains(candidate) && !candidate.closest('[inert]')) ?? null

const activateModal = async () => {
  if (!import.meta.client || active) return
  if (focusRestoreTimer !== null) clearTimeout(focusRestoreTimer)
  focusRestoreTimer = null
  pendingPreviousFocus = null
  pendingModalRoot = null
  active = true
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  releaseBodyScroll = acquireBodyScrollLock()
  await nextTick()
  const root = modalRoot.value
  if (!root || !props.show) {
    deactivateModal()
    return
  }
  activeModalRoot = root
  releaseModalIsolation = registerModalRoot(root)
  await nextTick()
  ;(focusableElements(dialog.value)[0] ?? dialog.value)?.focus()
}

const deactivateModal = () => {
  if (!active) return
  active = false
  releaseModalIsolation?.()
  releaseModalIsolation = null
  releaseBodyScroll?.()
  releaseBodyScroll = null
  pendingPreviousFocus = previousFocus
  pendingModalRoot = activeModalRoot
  previousFocus = null
  activeModalRoot = null
  focusRestoreTimer = window.setTimeout(() => {
    focusRestoreTimer = null
    restoreFocus()
  }, 250)
}

const restoreFocus = () => {
  if (active) return
  if (focusRestoreTimer !== null) clearTimeout(focusRestoreTimer)
  focusRestoreTimer = null
  const previousFocusTarget = pendingPreviousFocus
  const modalRootTarget = pendingModalRoot
  pendingPreviousFocus = null
  pendingModalRoot = null
  const parentDialog = underlyingDialog(modalRootTarget)
  const previousDialog = previousFocusTarget?.closest<HTMLElement>('[role="dialog"], [role="alertdialog"]')
  const focusTarget = previousFocusTarget?.isConnected
      && !previousFocusTarget.closest('[inert]')
      && previousFocusTarget.getClientRects().length > 0
      && (!previousDialog || previousDialog === parentDialog)
    ? previousFocusTarget
    : focusableElements(parentDialog)[0] ?? parentDialog
  focusTarget?.focus()
  emit('after-close')
}

const handleKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && props.closable) {
    event.preventDefault()
    close()
    return
  }
  if (event.key !== 'Tab') return
  const controls = focusableElements(dialog.value)
  const first = controls[0]
  const last = controls.at(-1)
  if (!first || !last) {
    event.preventDefault()
    dialog.value?.focus()
  } else if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.show, (isShown) => {
  if (isShown) void activateModal()
  else deactivateModal()
}, { immediate: true, flush: 'post' })

onBeforeUnmount(() => {
  deactivateModal()
  restoreFocus()
})
</script>
