<template>
  <Teleport to="body">
    <div v-if="open" class="se-overlay-root">
      <button type="button" class="se-overlay" tabindex="-1" aria-label="Закрыть панель" @click="requestClose" />
        <aside
        ref="drawer"
        class="se-drawer"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        :aria-describedby="subtitle ? subtitleId : undefined"
        :inert="confirmDiscard || undefined"
        @keydown="handleKeydown"
      >
        <header class="se-drawer__header">
          <div>
            <p class="se-drawer__kicker">{{ mode === 'create' ? 'Создание' : 'Редактирование' }}</p>
            <h2 :id="titleId" class="se-drawer__title">{{ title }}</h2>
            <p v-if="subtitle" :id="subtitleId" class="se-drawer__subtitle">{{ subtitle }}</p>
          </div>
          <button ref="closeButton" type="button" class="se-icon-button" aria-label="Закрыть панель" :disabled="busy" @click="requestClose">
            <XMarkIcon aria-hidden="true" />
          </button>
        </header>
        <form class="se-drawer__form" @submit.prevent="$emit('save')">
          <div class="se-drawer__content" :aria-busy="busy"><slot /></div>
          <footer class="se-drawer__footer">
            <div class="se-drawer__danger-actions">
              <button ref="deleteButton" v-if="mode === 'edit' && canDelete" type="button" class="se-button se-button--ghost-danger" :disabled="busy" @click="requestDelete">
                <TrashIcon aria-hidden="true" />
                Удалить
              </button>
            </div>
            <div class="se-drawer__actions">
              <button type="button" class="se-button se-button--secondary" :disabled="busy" @click="requestClose">Отмена</button>
              <button type="submit" class="se-button se-button--primary" :disabled="busy || saveDisabled">
                <ArrowPathIcon v-if="busy" class="se-spinner" aria-hidden="true" />
                {{ busy ? 'Сохраняем…' : mode === 'create' ? 'Создать' : 'Сохранить' }}
              </button>
            </div>
          </footer>
        </form>
      </aside>

      <div v-if="confirmDiscard" class="se-dialog-wrap" @keydown="handleDiscardKeydown">
        <section ref="discardDialog" class="se-dialog se-dialog--compact" role="alertdialog" aria-modal="true" :aria-labelledby="discardTitleId">
          <div class="se-dialog__body">
            <div class="se-dialog__icon se-dialog__icon--warning"><ExclamationTriangleIcon aria-hidden="true" /></div>
            <h2 :id="discardTitleId" class="se-dialog__title">Закрыть без сохранения?</h2>
            <p>Введённые изменения будут потеряны.</p>
          </div>
          <footer class="se-dialog__footer">
            <button ref="continueButton" type="button" class="se-button se-button--secondary" @click="confirmDiscard = false">Продолжить редактирование</button>
            <button type="button" class="se-button se-button--danger" @click="discard">Закрыть без сохранения</button>
          </footer>
        </section>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import {
  ArrowPathIcon,
  ExclamationTriangleIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline'

const props = defineProps<{
  open: boolean
  mode: 'create' | 'edit'
  title: string
  subtitle?: string
  dirty: boolean
  busy: boolean
  saveDisabled?: boolean
  canDelete?: boolean
}>()
const emit = defineEmits<{ close: []; save: []; delete: [] }>()
const drawer = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const continueButton = ref<HTMLButtonElement | null>(null)
const discardDialog = ref<HTMLElement | null>(null)
const deleteButton = ref<HTMLButtonElement | null>(null)
const confirmDiscard = ref(false)
const id = useId()
const titleId = `catalog-drawer-title-${id}`
const subtitleId = `catalog-drawer-subtitle-${id}`
const discardTitleId = `catalog-discard-title-${id}`
let previousFocus: HTMLElement | null = null
let previousOverflow = ''
let appRoot: HTMLElement | null = null

const requestClose = () => {
  if (props.busy) return
  if (props.dirty) {
    confirmDiscard.value = true
    void nextTick(() => continueButton.value?.focus())
    return
  }
  emit('close')
}
const discard = () => {
  confirmDiscard.value = false
  emit('close')
}
const requestDelete = () => {
  if (props.busy) return
  emit('delete')
}
const controls = (root: HTMLElement | null): HTMLElement[] => root
  ? [...root.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    )]
  : []
const trap = (event: KeyboardEvent, root: HTMLElement | null) => {
  if (event.key !== 'Tab') return
  const items = controls(root)
  const first = items[0]
  const last = items.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}
const handleKeydown = (event: KeyboardEvent) => {
  if (confirmDiscard.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    requestClose()
  } else trap(event, drawer.value)
}
const handleDiscardKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    event.preventDefault()
    confirmDiscard.value = false
    void nextTick(() => continueButton.value?.focus())
  } else trap(event, discardDialog.value)
}
watch(() => props.open, async open => {
  if (!import.meta.client) return
  if (open) {
    appRoot = document.querySelector<HTMLElement>('#__nuxt')
    previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    appRoot?.setAttribute('inert', '')
    appRoot?.setAttribute('aria-hidden', 'true')
    await nextTick()
    closeButton.value?.focus()
  } else {
    document.body.style.overflow = previousOverflow
    appRoot?.removeAttribute('inert')
    appRoot?.removeAttribute('aria-hidden')
    previousFocus?.focus()
  }
})
onBeforeUnmount(() => {
  if (!import.meta.client || !props.open) return
  document.body.style.overflow = previousOverflow
  appRoot?.removeAttribute('inert')
  appRoot?.removeAttribute('aria-hidden')
})
</script>
