<template>
  <article class="space-y-4 rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] bg-[color:var(--storefront-surface,#ffffff)] p-4">
    <header class="flex items-center justify-between gap-3">
      <div><p class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">{{ signer.roleLabel }}</p><h5 class="text-sm font-semibold text-[color:var(--storefront-title,#111827)]">{{ signer.name }}</h5></div>
      <span v-if="signer.inn" class="text-xs text-[color:var(--storefront-text-muted,#6b7280)]">ИНН {{ signer.inn }}</span>
    </header>
    <section class="space-y-2 border-t pt-3">
      <label class="flex items-center gap-2 text-sm"><input :checked="personFlags.is_pdl" type="checkbox" @change="$emit('person-flags', { is_pdl: ($event.target as HTMLInputElement).checked, pdl_related_person_name: ($event.target as HTMLInputElement).checked ? personFlags.pdl_related_person_name : '' })">Является ПДЛ или родственником ПДЛ</label>
      <label v-if="personFlags.is_pdl" class="block text-sm">ФИО ПДЛ или родственника ПДЛ <span class="text-red-700">*</span><input :value="personFlags.pdl_related_person_name" class="storefront-control mt-1 w-full rounded-md border px-3 py-2" @input="$emit('person-flags', { pdl_related_person_name: ($event.target as HTMLInputElement).value })"></label>
      <p v-if="personFlags.is_pdl && !personFlags.pdl_related_person_name.trim()" role="alert" class="text-sm text-red-700">Укажите ФИО ПДЛ или родственника ПДЛ</p>
      <label class="flex items-center gap-2 text-sm"><input :checked="personFlags.name_changed" type="checkbox" @change="$emit('person-flags', { name_changed: ($event.target as HTMLInputElement).checked })">Имеется ли отметка о смене ФИО</label>
    </section>
    <p v-if="nameMismatch" role="alert" class="rounded border border-amber-300 bg-amber-50 p-3 text-sm">ФИО в паспорте не совпадает с указанным ФИО бенефициара. Проверьте данные или загрузите паспорт повторно.</p>
    <template v-if="alreadySigned"><p class="rounded-md bg-[color:var(--storefront-success,#f0fdf4)] p-3 text-sm text-[color:var(--storefront-success-text,#166534)]">СОПД уже подписан</p></template>
    <template v-else>
      <div v-if="signer.signingMethod === 'sms'" class="space-y-2 border-t pt-3">
        <p class="text-xs font-medium">Способ подписания СОПД</p>
        <label class="mr-4 text-sm"><input v-model="state.mode" type="radio" value="sms"> Отправить SMS</label>
        <label class="text-sm"><input v-model="state.mode" type="radio" value="physical"> Подпишу на бумаге</label>
      </div>
      <section class="space-y-2 rounded-md border border-dashed border-[color:var(--storefront-border,#d1d5db)] p-3">
        <p class="text-xs font-medium">Загрузите скан паспорта - мы автоматически распознаем и сохраним данные. Или введите данные вручную</p>
        <div class="space-y-2">
          <div v-for="kind in passportKinds" :key="kind.key" class="flex items-center gap-2 text-xs">
            <label class="cursor-pointer rounded border px-3 py-1.5" :class="recognitionLoading ? 'pointer-events-none opacity-60' : ''">{{ passportFiles?.[kind.key] ? 'Заменить' : kind.label }}<input class="hidden" type="file" accept="image/jpeg,image/jpg,image/png" :disabled="recognitionLoading" @change="onPassportFile(kind.key, $event)"></label>
            <span v-if="passportFiles?.[kind.key]" class="min-w-0 truncate">{{ passportFiles[kind.key]?.name }}</span>
            <button v-if="passportFiles?.[kind.key]?.file" type="button" class="text-[color:var(--storefront-error-text,#dc2626)]" @click="$emit('passport-file-change', { signerKey: signer.key, kind: kind.key, file: null })">Убрать</button>
          </div>
          <button v-if="!hasPassportFile" type="button" class="mt-3 rounded border px-3 py-1.5 text-xs" @click="$emit('passport-manual', signer.key)">Ввести паспорт вручную</button>
        </div>
        <p v-if="recognitionLoading" class="text-xs">Распознаём паспорт…</p><p v-if="passportError" class="text-xs text-[color:var(--storefront-error-text,#dc2626)]">{{ passportError }}</p>
      </section>
      <PassportRecognitionForm v-bind="passport" :citizenships="citizenships" :citizenships-loading="citizenshipsLoading" @edit="(key, value) => $emit('passport-edit', { signerKey: signer.key, key, value })" @save="$emit('passport-save', signer.key)" />
      <section v-if="showSms" class="space-y-2">
        <div class="flex gap-2"><input v-model="state.phone" class="storefront-control flex-1 rounded-md border px-3 py-2 text-sm" placeholder="+7XXXXXXXXXX" :disabled="state.sending || state.sent"><button type="button" class="storefront-action-primary rounded-md px-4 py-2 text-sm disabled:opacity-50" :title="blockedReason" :disabled="state.sending || state.sent || !state.phone.trim() || !passport.actionsAllowed" @click="$emit('invite', signer.key)">{{ state.sent ? '✓ Отправлено' : 'Отправить приглашение' }}</button></div>
        <p v-if="!passport.actionsAllowed" class="text-xs text-[color:var(--storefront-warning-text,#a16207)]">{{ blockedReason }}</p><p v-if="state.error" class="text-xs text-[color:var(--storefront-error-text,#dc2626)]">{{ state.error }}</p>
      </section>
      <section v-else class="space-y-3 rounded-md bg-[color:var(--storefront-surface-muted,#f9fafb)] p-3">
        <div class="flex items-center justify-between"><h6 class="text-sm font-medium">СОПД (для бумажной подписи)</h6><button type="button" class="btn-secondary text-sm disabled:opacity-50" :title="blockedReason" :disabled="!downloadingSopd && !passport.actionsAllowed" @click="downloadingSopd ? $emit('cancel-sopd-download') : $emit('download-sopd', signer.key)">{{ downloadingSopd ? 'Отменить формирование' : 'Скачать шаблон СОПД' }}</button></div>
        <p v-if="downloadingSopd && sopdDownloadMessage" class="text-xs text-[color:var(--storefront-text-muted,#4b5563)]">{{ sopdDownloadMessage }}</p>
        <p v-if="!passport.actionsAllowed" class="text-xs text-[color:var(--storefront-warning-text,#a16207)]">{{ blockedReason }}</p>
        <label class="inline-flex cursor-pointer rounded border px-3 py-2 text-sm" :class="passport.actionsAllowed ? '' : 'pointer-events-none opacity-60'">Загрузить скан СОПД<input class="hidden" type="file" accept="application/pdf,image/*" :disabled="!passport.actionsAllowed" @change="$emit('upload-sopd', $event)"></label>
        <p v-if="sopdUploaded" class="text-xs text-[color:var(--storefront-text-muted,#4b5563)]">Скан загружен: {{ sopdFileName }}.</p>
      </section>
    </template>
  </article>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import type { UUID } from '~/types/ids'
import type { SopdSigningMethod } from '~/features/checkout/types/sopdSigners'
import PassportRecognitionForm, { type Citizenship, type PassportFields, type PassportFieldKey } from './PassportRecognitionForm.vue'
export interface PersonFlags { is_pdl: boolean; pdl_related_person_name: string; name_changed: boolean }
export interface Signer { key: string; name: string; role: string; roleLabel: string; inn: string | null; signingMethod: SopdSigningMethod }
export interface InviteStatus { mode: 'sms' | 'physical'; phone: string; sending: boolean; sent: boolean; error: string; signatureRequestId?: UUID }
export interface PassportCardState { visible: boolean; fields: PassportFields; confidence: Partial<Record<PassportFieldKey, number | null>>; showConfidence: boolean; canSave: boolean; saving: boolean; actionsAllowed: boolean; error: string; fieldErrors: Partial<Record<PassportFieldKey, string>> }
const props = defineProps<{ signer: Signer; personFlags: PersonFlags; nameMismatch?: boolean; alreadySigned: boolean; inviteState: InviteStatus; passportFiles?: { main?: { name: string; file?: File }; registration?: { name: string; file?: File } }; hasPassportFile: boolean; recognitionLoading: boolean; passportError: string; passport: PassportCardState; citizenships: Citizenship[]; citizenshipsLoading: boolean; downloadingSopd: boolean; sopdDownloadMessage: string; sopdUploaded: boolean; sopdFileName: string }>()
const emit = defineEmits<{ (e: 'person-flags', value: Partial<PersonFlags>): void; (e: 'invite', signerKey: string): void; (e: 'passport-file-change', value: { signerKey: string; kind: 'main' | 'registration'; file: File | null }): void; (e: 'passport-manual', signerKey: string): void; (e: 'passport-edit', value: { signerKey: string; key: PassportFieldKey; value: string }): void; (e: 'passport-save', signerKey: string): void; (e: 'download-sopd', signerKey: string): void; (e: 'cancel-sopd-download'): void; (e: 'upload-sopd', event: Event): void }>()
const state = computed(() => props.inviteState)
const showSms = computed(() => props.signer.signingMethod === 'sms' && state.value.mode === 'sms')
const blockedReason = computed(() => props.passport.actionsAllowed ? '' : 'Сначала сохраните актуальные паспортные данные')
const passportKinds: Array<{ key: 'main' | 'registration'; label: string }> = [{ key: 'main', label: 'Паспорт: страницы 2–3' }, { key: 'registration', label: 'Паспорт: страница с пропиской' }]
const hasPassportFile = computed(() => props.hasPassportFile)
const onPassportFile = (kind: 'main' | 'registration', event: Event) => { const file = (event.target as HTMLInputElement).files?.[0] || null; if (file) emit('passport-file-change', { signerKey: props.signer.key, kind, file }) }
</script>
<style scoped>.btn-secondary { @apply rounded-md border border-[color:var(--storefront-border,#d1d5db)] bg-white px-3 py-2; }</style>
