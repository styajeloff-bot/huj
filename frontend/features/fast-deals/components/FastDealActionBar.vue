<template>
  <div
    v-if="buttons.length"
    class="sticky top-0 z-20 rounded-lg border border-gray-200 bg-white/95 p-3 shadow-sm backdrop-blur"
    role="toolbar"
    aria-label="Действия по сделке"
  >
    <div class="flex flex-wrap items-center gap-2">
      <button
        v-for="button in buttons"
        :key="button.key"
        type="button"
        :class="buttonClass(button.tone)"
        :disabled="ctx.busy.value"
        @click="button.run"
      >
        {{ button.label }}
      </button>
    </div>
  </div>

  <FastDealActionSendModal v-if="dialog === 'send_lc'" :deal="deal" @close="closeDialog" />
  <FastDealActionConfirmModal v-if="dialog === 'confirm_lc'" :deal="deal" mode="leasing" @close="closeDialog" />
  <FastDealActionConfirmModal v-if="dialog === 'confirm_dealer'" :deal="deal" mode="dealer" @close="closeDialog" />

  <FastDealActionDialog
    v-if="simple"
    :key="dialog ?? undefined"
    :title="simple.title"
    :message="simple.message"
    :warnings="simple.warnings"
    :confirm-text="simple.confirmText"
    :danger="simple.danger"
    :reason-label="simple.reasonLabel"
    :reason-required="simple.reasonRequired"
    :busy="ctx.busy.value"
    :error="dialogError"
    @confirm="perform"
    @close="closeDialog"
  />

  <Modal
    v-if="splitResult"
    :show="true"
    title="Сделка отправлена дилерам"
    size="2xl"
    :show-footer="true"
    @close="splitResult = null"
  >
    <p class="mb-3 text-sm text-gray-700">
      Позиции разделены по дилерам: для каждого создана отдельная сделка со своим номером. Все сделки группы доступны вам по ссылкам.
    </p>
    <ul class="divide-y divide-gray-100 rounded-lg border border-gray-200">
      <li v-for="item in splitResult" :key="item.id" class="flex items-center justify-between gap-3 px-3 py-2 text-sm">
        <NuxtLink :to="ctx.dealLocation(item.id)" class="font-medium text-blue-600 hover:text-blue-700" @click="splitResult = null">
          {{ item.display_number }}
        </NuxtLink>
        <span class="min-w-0 truncate text-gray-600">{{ item.dealer_company?.name ?? '' }}</span>
        <span class="shrink-0 rounded-full px-2 py-0.5 text-xs" :class="dealStatusTone(item.status)">{{ dealStatusLabel(item.status) }}</span>
      </li>
    </ul>
    <template #footer>
      <button type="button" class="btn-primary" @click="splitResult = null">Понятно</button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import Modal from '~/components/ui/Modal.vue'
import { useFastDealCardContext, type ActionFailure, type ActionResult } from '../composables/useFastDealCard'
import { dealStatusLabel, dealStatusTone } from '../composables/fastDealCardFormat'
import type { FastDealAction, FastDealCard } from '../types'
import FastDealActionConfirmModal from './FastDealActionConfirmModal.vue'
import FastDealActionDialog from './FastDealActionDialog.vue'
import FastDealActionSendModal from './FastDealActionSendModal.vue'

type Dialog =
  | 'send_lc' | 'send_dealers' | 'confirm_lc' | 'confirm_dealer' | 'reject_lc' | 'reject_dealer'
  | 'reject_changes' | 'accept_changes' | 'send_changes' | 'withdraw' | 'cancel' | 'delete'
type Tone = 'primary' | 'success' | 'neutral' | 'danger'

interface ActionButton {
  key: Dialog | 'offer'
  action: FastDealAction
  label: string
  tone: Tone
  run: () => void
}

interface SimpleDialog {
  title: string
  message?: string
  warnings: string[]
  confirmText: string
  danger: boolean
  reasonLabel?: string
  reasonRequired: boolean
}

const props = defineProps<{ deal: FastDealCard }>()

const ctx = useFastDealCardContext()
const dialog = ref<Dialog | null>(null)
const dialogError = ref<ActionFailure | null>(null)
const splitResult = ref<FastDealCard[] | null>(null)

function openDialog(kind: Dialog) {
  dialogError.value = null
  dialog.value = kind
}
const closeDialog = () => {
  dialog.value = null
}

/** Server-driven: a button exists only when `allowed_actions` contains its action. */
const buttons = computed<ActionButton[]>(() => {
  const all: ActionButton[] = [
    { key: 'send_lc', action: 'send_to_leasing_companies', label: 'Отправить в лизинговые компании', tone: 'primary', run: () => openDialog('send_lc') },
    { key: 'send_dealers', action: 'send_to_dealers', label: 'Отправить дилерам', tone: 'primary', run: () => openDialog('send_dealers') },
    { key: 'offer', action: 'submit_offer', label: 'Сделать КП', tone: 'primary', run: () => ctx.openOfferDialog(false) },
    { key: 'confirm_lc', action: 'confirm_as_leasing', label: 'Подтвердить сделку', tone: 'success', run: () => openDialog('confirm_lc') },
    { key: 'confirm_dealer', action: 'confirm_as_dealer', label: 'Подтвердить сделку', tone: 'success', run: () => openDialog('confirm_dealer') },
    { key: 'send_changes', action: 'send_changes', label: 'Отправить изменения', tone: 'primary', run: () => openDialog('send_changes') },
    { key: 'accept_changes', action: 'accept_changes', label: 'Принять изменения', tone: 'success', run: () => openDialog('accept_changes') },
    { key: 'withdraw', action: 'withdraw_selection', label: 'Снять выбор КП', tone: 'neutral', run: () => openDialog('withdraw') },
    { key: 'reject_changes', action: 'reject_changes', label: 'Отклонить изменения', tone: 'danger', run: () => openDialog('reject_changes') },
    { key: 'reject_lc', action: 'reject_as_leasing', label: 'Отказаться', tone: 'danger', run: () => openDialog('reject_lc') },
    { key: 'reject_dealer', action: 'reject_as_dealer', label: 'Отказаться от сделки', tone: 'danger', run: () => openDialog('reject_dealer') },
    { key: 'cancel', action: 'cancel', label: 'Отменить сделку', tone: 'danger', run: () => openDialog('cancel') },
    { key: 'delete', action: 'delete', label: 'Удалить черновик', tone: 'danger', run: () => openDialog('delete') },
  ]
  return all.filter(button => ctx.can(button.action))
})

const buttonClass = (tone: Tone): string => {
  switch (tone) {
    case 'primary':
      return 'btn-primary text-sm'
    case 'success':
      return 'btn-success text-sm'
    case 'danger':
      return 'btn-outline text-sm text-red-700 border-red-200 hover:bg-red-50'
    default:
      return 'btn-outline text-sm'
  }
}

const distinctDealers = computed(() => new Set(ctx.activeVehicles.value.map(item => item.dealer_company_id ?? '')).size)
const withoutDealer = computed(() => ctx.activeVehicles.value.filter(item => !item.dealer_company_id).length)

/** Dialogs that only ask for confirmation (and a reason where the server requires one). */
const simple = computed<SimpleDialog | null>(() => {
  switch (dialog.value) {
    case 'send_dealers': {
      const first = props.deal.group_id === null || props.deal.group_id === undefined
      const warnings: string[] = []
      if (first && distinctDealers.value > 1) warnings.push(`Позиции будут разделены по дилерам: создаётся ${distinctDealers.value} сделок, у каждой свой номер и свои суммы.`)
      if (first && withoutDealer.value > 0) warnings.push('У части позиций не определён дилер: отправка невозможна, пока он не указан.')
      warnings.push('Единицы каталога будут зарезервированы; при конфликте отправка не произойдёт и ошибка покажет VIN.')
      return {
        title: 'Отправить дилерам',
        message: first ? 'Сделка будет отправлена дилерам на подтверждение.' : 'Исправленная сделка будет повторно отправлена тому же дилеру без нового разделения.',
        warnings,
        confirmText: 'Отправить',
        danger: false,
        reasonRequired: false,
      }
    }
    case 'reject_lc':
      return {
        title: 'Отказаться от сделки',
        message: 'Вы отказываетесь от участия в этой сделке. Если не останется лизинговых компаний, способных ответить, сделка будет отклонена, а резервы освобождены.',
        warnings: [],
        confirmText: 'Отказаться',
        danger: true,
        reasonLabel: 'Причина отказа',
        reasonRequired: true,
      }
    case 'reject_dealer':
      return {
        title: 'Отказаться от сделки',
        message: 'Сделка будет отклонена, резервы освобождены. Лизинговая компания сможет исправить сделку и отправить её снова.',
        warnings: [],
        confirmText: 'Отказаться',
        danger: true,
        reasonLabel: 'Причина отказа',
        reasonRequired: true,
      }
    case 'reject_changes':
      return {
        title: 'Отклонить изменения дилера',
        message: 'Сделка будет отклонена, резервы освобождены. Затем вы сможете скорректировать её и отправить тому же дилеру.',
        warnings: [],
        confirmText: 'Отклонить',
        danger: true,
        reasonLabel: 'Причина',
        reasonRequired: true,
      }
    case 'accept_changes':
      return {
        title: 'Принять изменения дилера',
        message: 'Изменения принимаются целиком. Сделка будет подтверждена без дополнительного подтверждения дилером.',
        warnings: ['После подтверждения сделка станет неизменяемой.'],
        confirmText: 'Принять и подтвердить',
        danger: false,
        reasonRequired: false,
      }
    case 'send_changes':
      return {
        title: 'Отправить изменения',
        message: 'Изменения будут отправлены лизинговой компании. До её решения вы не сможете менять согласуемые данные.',
        warnings: [],
        confirmText: 'Отправить изменения',
        danger: false,
        reasonLabel: 'Комментарий для лизинговой компании (необязательно)',
        reasonRequired: false,
      }
    case 'withdraw':
      return {
        title: 'Снять выбор КП',
        message: 'Выбор будет снят: предложения других лизинговых компаний снова станут доступны, а выбранная компания выйдет из финального подтверждения.',
        warnings: [],
        confirmText: 'Снять выбор',
        danger: false,
        reasonRequired: false,
      }
    case 'cancel':
      return {
        title: 'Отменить сделку',
        message: 'Отмена необратима: сделку нельзя будет изменить, подтвердить или отправить повторно.',
        warnings: [
          'Все резервы техники будут освобождены, участники получат уведомление.',
          ...(props.deal.status === 'draft' ? [] : ['Полученные предложения и согласования будут закрыты.']),
        ],
        confirmText: 'Отменить сделку',
        danger: true,
        reasonLabel: 'Причина отмены (необязательно)',
        reasonRequired: false,
      }
    case 'delete':
      return {
        title: 'Удалить черновик',
        message: 'Черновик будет удалён вместе с загруженными файлами. Восстановить его нельзя.',
        warnings: [],
        confirmText: 'Удалить',
        danger: true,
        reasonRequired: false,
      }
    default:
      return null
  }
})

function finish(result: ActionResult<unknown>) {
  if (result.ok) closeDialog()
  else dialogError.value = result.error
}

async function sendToDealers() {
  const result = await ctx.guard(() => ctx.api.sendToDealers(props.deal.id, props.deal.etag))
  if (!result.ok) {
    dialogError.value = result.error
    return
  }
  const { deals } = result.value
  const current = deals.find(item => item.id === props.deal.id)
  if (current) ctx.replaceCard(current)
  else await ctx.reload()
  closeDialog()
  if (deals.length > 1) splitResult.value = deals
}

async function perform(reason: string) {
  const kind = dialog.value
  if (!kind) return
  dialogError.value = null
  const application = ctx.ownApplication.value
  switch (kind) {
    case 'send_dealers':
      await sendToDealers()
      return
    case 'delete': {
      const result = await ctx.guard(() => ctx.api.remove(props.deal.id, props.deal.etag))
      if (result.ok) {
        closeDialog()
        await navigateTo('/workspace/fast-deals')
      } else {
        dialogError.value = result.error
      }
      return
    }
    case 'reject_lc':
      if (!application) {
        dialogError.value = { detail: 'Приглашение вашей компании не найдено' }
        return
      }
      finish(await ctx.run((etag) => ctx.api.rejectAsLeasing(application.id, etag, reason)))
      return
    case 'reject_dealer':
      finish(await ctx.run((etag, card) => ctx.api.rejectAsDealer(card.id, etag, reason)))
      return
    case 'reject_changes':
      finish(await ctx.run((etag, card) => ctx.api.rejectChanges(card.id, etag, reason)))
      return
    case 'accept_changes':
      finish(await ctx.run((etag, card) => ctx.api.acceptChanges(card.id, etag)))
      return
    case 'send_changes':
      finish(await ctx.run((etag, card) => ctx.api.sendChanges(card.id, etag, reason || undefined)))
      return
    case 'withdraw':
      finish(await ctx.run((etag, card) => ctx.api.withdrawSelection(card.id, etag)))
      return
    case 'cancel':
      finish(await ctx.run((etag, card) => ctx.api.cancel(card.id, etag, reason || undefined)))
      return
    default:
      return
  }
}
</script>
