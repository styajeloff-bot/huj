<template>
  <div data-storefront-block="client.checkout" class="space-y-4">
    <div v-if="sopdLoading" class="py-4 text-center text-sm">Загружаем статусы СОПД…</div>
    <p v-else-if="signers.length === 0" class="rounded-lg border p-4 text-sm">Подписанты СОПД не найдены.</p>
    <SignerCard
      v-for="signer in signers"
      :key="signer.key"
      :signer="signer"
      :person-flags="personFlags(signer)"
      :name-mismatch="passportState[signer.key]?.manualMode ? false : passportState[signer.key]?.nameMismatch"
      @person-flags="updatePersonFlags(signer, $event)"
      :already-signed="isAlreadySigned(signer)"
      :invite-state="inviteState[signer.key]"
      :passport-files="passportFiles[signer.key]"
      :has-passport-file="hasPassportFile(signer.key)"
      :recognition-loading="passportState[signer.key]?.recognitionLoading || false"
      :passport-error="passportState[signer.key]?.loadError || ''"
      :passport="cardState(signer.key)"
      :citizenships="citizenships"
      :citizenships-loading="citizenshipsLoading"
      :downloading-sopd="downloadingSopd"
      :sopd-download-message="sopdDownloadMessage"
      :sopd-uploaded="Boolean(sopdFiles[signer.key])"
      :sopd-file-name="sopdFiles[signer.key]?.name || ''"
      @passport-file-change="onPassportFile"
      @passport-manual="openManualPassport"
      @passport-edit="onPassportEdit"
      @passport-save="confirmPassport"
      @invite="onInviteSigner"
      @download-sopd="downloadSopd"
      @cancel-sopd-download="cancelSopdDownload"
      @upload-sopd="(event) => handleSopdUpload(signer.key, event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { UUID } from '~/types/ids'
import SignerCard, { type InviteStatus, type PassportCardState, type Signer, type PersonFlags } from './SignerCard.vue'
import type { Citizenship, PassportFieldKey, PassportFields } from './PassportRecognitionForm.vue'
import { useSopdStatus } from '~/features/checkout/composables/useSopdStatus'
import type { QuestionnaireData } from '~/features/applications/constants/application'
import type { QuestionnairePerson } from '~/features/questionnaire/types'
import type { SopdSignerCandidate } from '~/features/checkout/types/sopdSigners'

const props = defineProps<{ applicationId?: UUID | null; sopdSignerCandidates: SopdSignerCandidate[]; runPassportConfirmation: (confirm: () => Promise<void>) => Promise<void> }>()
const emit = defineEmits<{ (e: 'update', data: Record<string, unknown>): void }>()
const config = useRuntimeConfig()
const checkoutStore = useCheckoutStore()
const toast = useToast()
const { statuses: sopdStatuses, loading: sopdLoading, fetch: fetchSopdStatus } = useSopdStatus(props.applicationId ?? null)

type Snapshot = {
  applicationId: UUID
  signerKey: string
  signatureRequestId: UUID | null
  fields: Record<PassportFieldKey, string | null>
  confidence?: Partial<Record<PassportFieldKey, number | null>> | null
  showConfidence: boolean
  editedFields: PassportFieldKey[]
  nameMismatch?: boolean
  hasUnsavedChanges: boolean
  actionsAllowed: boolean
  passportFiles?: Array<{ page: 'main' | 'registration'; fileName: string }>
}
type PassportFile = { name: string; file?: File; persisted?: boolean }
type State = {
  fields: PassportFields
  confirmedFields: PassportFields | null
  confidence: Partial<Record<PassportFieldKey, number | null>>
  showConfidence: boolean
  editedFields: PassportFieldKey[]
  nameMismatch?: boolean
  hasUnsavedChanges: boolean
  actionsAllowed: boolean
  formVisible: boolean
  manualMode: boolean
  snapshotLoading: boolean
  recognitionLoading: boolean
  saving: boolean
  loadError: string
  error: string
  fieldErrors: Partial<Record<PassportFieldKey, string>>
  signatureRequestId?: UUID
  version: number
  timer?: ReturnType<typeof setTimeout>
  recognitionController?: AbortController
  snapshotController?: AbortController
  draftController?: AbortController
  confirmController?: AbortController
  draftQueue: Promise<void>
}

const emptyFields = (): PassportFields => ({ surname: '', name: '', patronymic: '', nationality: '', gender: '', birthDate: '', birthPlace: '', passportSeries: '', passportNumber: '', givenDate: '', code: '', givenWhom: '' })
const passportState = ref<Record<string, State>>({})
const passportFiles = ref<Record<string, { main?: PassportFile; registration?: PassportFile }>>({})
const citizenships = ref<Citizenship[]>([])
const citizenshipsLoading = ref(false)
const inviteState = ref<Record<string, InviteStatus>>({})
const sopdFiles = ref<Record<string, File>>({})
const downloadingSopd = ref(false)
const sopdDownloadMessage = ref('')
let sopdDownloadController: AbortController | undefined
const sleep = (milliseconds: number, signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  const timer = window.setTimeout(resolve, milliseconds)
  signal.addEventListener('abort', () => { window.clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')) }, { once: true })
})

const signers = computed<Signer[]>(() => props.sopdSignerCandidates.map(candidate => ({ key: candidate.key, name: candidate.full_name, role: candidate.role, roleLabel: candidate.role_label, inn: candidate.inn ?? null, signingMethod: candidate.signing_method })))
const current = (key: string): State => passportState.value[key] ||= {
  fields: emptyFields(), confirmedFields: null, confidence: {}, showConfidence: false, editedFields: [], hasUnsavedChanges: false,
  actionsAllowed: false, formVisible: false, manualMode: false, snapshotLoading: false, recognitionLoading: false, saving: false, loadError: '', error: '', fieldErrors: {},
  version: 0, draftQueue: Promise.resolve(),
}
const apiDateToUi = (value: string | null) => value && /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value.slice(8, 10)}.${value.slice(5, 7)}.${value.slice(0, 4)}` : value || ''
const uiDateToApi = (value: string) => /^\d{2}\.\d{2}\.\d{4}$/.test(value) ? `${value.slice(6, 10)}-${value.slice(3, 5)}-${value.slice(0, 2)}` : value
const fieldsToApi = (fields: PassportFields) => ({ ...fields, birthDate: uiDateToApi(fields.birthDate), givenDate: uiDateToApi(fields.givenDate) })
const snapshotFields = (snapshot: Snapshot): PassportFields => Object.fromEntries(Object.entries(snapshot.fields).map(([field, value]) => [field, field === 'birthDate' || field === 'givenDate' ? apiDateToUi(value) : value || ''])) as PassportFields
const applySnapshot = (key: string, snapshot: Snapshot) => {
  const state = current(key)
  state.fields = snapshotFields(snapshot)
  state.confidence = snapshot.confidence || {}
  state.showConfidence = snapshot.showConfidence
  state.formVisible = true
  state.manualMode = !snapshot.showConfidence
  state.editedFields = snapshot.editedFields || []
  state.nameMismatch = snapshot.nameMismatch
  state.hasUnsavedChanges = snapshot.hasUnsavedChanges
  state.actionsAllowed = snapshot.actionsAllowed
  if (snapshot.actionsAllowed && !snapshot.hasUnsavedChanges) state.confirmedFields = { ...state.fields }
  state.signatureRequestId = snapshot.signatureRequestId || undefined
  state.error = ''
  state.fieldErrors = {}
  if (snapshot.passportFiles) {
    const localFiles = passportFiles.value[key] || {}
    const persistedFiles = Object.fromEntries(snapshot.passportFiles.map(file => [file.page, { name: file.fileName, persisted: true }]))
    passportFiles.value[key] = { ...persistedFiles, ...Object.fromEntries(Object.entries(localFiles).filter(([, file]) => file?.file)) }
  }
}
const isAbort = (error: unknown) => (error as { name?: string })?.name === 'AbortError'
const errorMessage = (error: unknown, fallback: string) => {
  const detail = (error as { data?: { detail?: unknown } })?.data?.detail
  return typeof detail === 'object' && detail && 'message' in detail ? String((detail as { message: unknown }).message) : typeof detail === 'string' ? detail : fallback
}
const passportErrorMessage = (error: unknown, fallback: string): string => {
  const message = (error as { data?: { detail?: { message?: unknown } } })?.data?.detail?.message
  return typeof message === 'string' && message.trim() ? message : fallback
}
const endpoint = (key: string, suffix = '') => {
  const state = current(key)
  return state.signatureRequestId
    ? `/api/v1/signatures/${state.signatureRequestId}/passport${suffix}`
    : `/api/v1/applications/${props.applicationId}/sopd-signers/${encodeURIComponent(key)}/passport${suffix}`
}

const fetchSnapshot = async (key: string) => {
  if (!props.applicationId) return
  const state = current(key)
  state.snapshotController?.abort()
  const controller = new AbortController()
  state.snapshotController = controller
  const version = state.version
  state.snapshotLoading = true
  state.loadError = ''
  try {
    const snapshot = await $fetch<Snapshot>(endpoint(key), { baseURL: config.public.apiBase, credentials: 'include', signal: controller.signal })
    if (state.version === version && state.snapshotController === controller) applySnapshot(key, snapshot)
  } catch (error: unknown) {
    const status = (error as { response?: { status?: number } })?.response?.status
    if (!isAbort(error) && status !== 404 && state.snapshotController === controller) state.loadError = passportErrorMessage(error, 'Не удалось загрузить паспортные данные')
  } finally {
    if (state.snapshotController === controller) state.snapshotLoading = false
  }
}

type CitizenshipResponse = Citizenship[] | { items: Citizenship[] }
const fetchCitizenships = async () => {
  citizenshipsLoading.value = true
  try {
    const response = await $fetch<CitizenshipResponse>('/api/v1/citizenship', { baseURL: config.public.apiBase, credentials: 'include' })
    citizenships.value = Array.isArray(response) ? response : response.items
  } catch {
    citizenships.value = []
  } finally {
    citizenshipsLoading.value = false
  }
}

const syncInviteStates = () => {
  for (const signer of signers.value) {
    const status = sopdStatuses.value[signer.key]
    if (!status) continue
    const invite = inviteState.value[signer.key] ||= { mode: signer.signingMethod === 'file' ? 'physical' : 'sms', phone: '', sending: false, sent: false, error: '' }
    if (status.signatureRequestId) {
      invite.signatureRequestId = status.signatureRequestId
      current(signer.key).signatureRequestId = status.signatureRequestId
    }
    if ((invite.mode === 'physical' && status.status === 'signed_physical')
      || (invite.mode === 'sms' && ['pending', 'signed_electronic'].includes(status.status))) invite.sent = true
  }
  emit('update', getData())
}
const cancelPassportState = (state: State) => {
  state.version += 1
  if (state.timer) clearTimeout(state.timer)
  state.snapshotController?.abort()
  state.recognitionController?.abort()
  state.draftController?.abort()
  state.confirmController?.abort()
}
let snapshotApplicationId: UUID | null | undefined
watch(() => JSON.stringify([props.applicationId, signers.value.map(signer => signer.key)]), () => {
  if (snapshotApplicationId !== props.applicationId) {
    Object.values(passportState.value).forEach(cancelPassportState)
    passportState.value = {}
    passportFiles.value = {}
    inviteState.value = {}
    sopdFiles.value = {}
    snapshotApplicationId = props.applicationId
  }
  const keys = new Set(signers.value.map(signer => signer.key))
  for (const key of Object.keys(passportState.value)) {
    if (!keys.has(key)) { cancelPassportState(passportState.value[key]); delete passportState.value[key] }
  }
  for (const signer of signers.value) {
    const newSigner = !passportState.value[signer.key]
    inviteState.value[signer.key] ||= { mode: signer.signingMethod === 'file' ? 'physical' : 'sms', phone: '', sending: false, sent: false, error: '' }
    if (newSigner) void fetchSnapshot(signer.key)
  }
}, { immediate: true })
watch(sopdStatuses, syncInviteStates, { deep: true })

const cardState = (key: string): PassportCardState => {
  const state = current(key)
  const pendingConfirmation = state.confirmedFields === null
  const draftDiffersFromConfirmed = !pendingConfirmation && Object.keys(state.fields).some(field => state.fields[field as PassportFieldKey] !== state.confirmedFields?.[field as PassportFieldKey])
  return { visible: state.formVisible, fields: state.fields, confidence: state.confidence, showConfidence: state.showConfidence, canSave: pendingConfirmation || draftDiffersFromConfirmed, saving: state.saving, actionsAllowed: state.actionsAllowed, error: state.error, fieldErrors: state.fieldErrors }
}
// A persisted file has no browser File object after a reload, but it still
// makes the manual path unavailable for this signer.
const hasPassportFile = (key: string) => Object.values(passportFiles.value[key] || {}).some(Boolean)
const onPassportFile = ({ signerKey, kind, file }: { signerKey: string; kind: 'main' | 'registration'; file: File | null }) => {
  const state = current(signerKey)
  state.version += 1
  state.recognitionController?.abort()
  const files = { ...passportFiles.value[signerKey] }
  if (file) files[kind] = { name: file.name, file }
  else if (files[kind]?.file) delete files[kind]
  passportFiles.value[signerKey] = files
  if (files.main?.file && files.registration?.file) void recognize(signerKey, files.main.file, files.registration.file)
}
const openManualPassport = (key: string) => {
  const state = current(key)
  state.version += 1
  state.recognitionController?.abort()
  state.formVisible = true
  state.manualMode = true
  state.showConfidence = false
  state.confidence = {}
  state.nameMismatch = false
  state.error = ''
  state.fieldErrors = {}
}
const recognize = async (key: string, main: File, registration: File) => {
  if (!props.applicationId) return
  const state = current(key)
  state.recognitionController?.abort()
  // OCR replaces a manual passport. Do this synchronously, before creating
  // the request, so neither the UI nor a delayed draft save can compare OCR
  // names with names entered manually.
  const nationality = state.fields.nationality
  if (state.timer) {
    clearTimeout(state.timer)
    state.timer = undefined
  }
  state.draftController?.abort()
  state.fields = { ...emptyFields(), nationality }
  state.confirmedFields = null
  state.confidence = {}
  state.showConfidence = false
  state.editedFields = nationality ? ['nationality'] : []
  state.nameMismatch = false
  state.hasUnsavedChanges = true
  state.actionsAllowed = false
  state.error = ''
  state.fieldErrors = {}
  const controller = new AbortController()
  state.recognitionController = controller
  const version = state.version
  state.recognitionLoading = true
  state.loadError = ''
  const body = new FormData()
  body.append('passport_main', main)
  body.append('passport_registration', registration)
  try {
    const snapshot = await $fetch<Snapshot>(endpoint(key, '-recognition'), { method: 'POST', baseURL: config.public.apiBase, credentials: 'include', body, signal: controller.signal })
    if (state.version === version && state.recognitionController === controller) applySnapshot(key, snapshot)
  } catch (error: unknown) {
    if (!isAbort(error) && state.recognitionController === controller) {
      state.loadError = passportErrorMessage(error, 'Не удалось распознать паспорт')
      toast.error(state.loadError)
    }
  } finally {
    if (state.recognitionController === controller) state.recognitionLoading = false
    emit('update', getData())
  }
}

const queueDraftSave = (key: string, version: number): Promise<void> => {
  const state = current(key)
  const fields = fieldsToApi(state.fields)
  const editedFields = [...state.editedFields]
  const draftEndpoint = endpoint(key, '/draft')
  const job = async () => {
    if (passportState.value[key] !== state || state.version !== version) return
    state.draftController?.abort()
    const controller = new AbortController()
    state.draftController = controller
    try {
      const snapshot = await $fetch<Snapshot>(draftEndpoint, { method: 'PATCH', baseURL: config.public.apiBase, credentials: 'include', body: { fields, editedFields }, signal: controller.signal })
      if (state.version === version && state.draftController === controller) applySnapshot(key, snapshot)
    } catch (error: unknown) {
      if (!isAbort(error) && state.version === version && state.draftController === controller) {
        state.actionsAllowed = false
        state.error = passportErrorMessage(error, 'Не удалось сохранить черновик')
        toast.error(state.error)
      }
    }
  }
  state.draftQueue = state.draftQueue.catch(() => undefined).then(job)
  return state.draftQueue
}
const onPassportEdit = ({ signerKey, key, value }: { signerKey: string; key: PassportFieldKey; value: string }) => {
  const state = current(signerKey)
  if (state.fields[key] === value) return
  state.version += 1
  // Keep awaiting a submitted confirmation; the version guard preserves this edit.
  state.snapshotController?.abort()
  state.fields = { ...state.fields, [key]: value }
  state.editedFields = [...new Set([...state.editedFields, key])]
  state.confidence = { ...state.confidence, [key]: null }
  state.hasUnsavedChanges = true
  state.actionsAllowed = false
  state.error = ''
  state.fieldErrors = {}
  if (state.timer) clearTimeout(state.timer)
  const version = state.version
  state.timer = setTimeout(() => { state.timer = undefined; void queueDraftSave(signerKey, version) }, 500)
  emit('update', getData())
}
const confirmPassport = async (key: string) => {
  const state = current(key)
  if (state.saving) return
  state.saving = true
  state.error = ''
  let version = state.version
  let controller: AbortController | undefined
  try {
    if (state.timer) {
      clearTimeout(state.timer)
      state.timer = undefined
      await queueDraftSave(key, state.version)
    } else await state.draftQueue
    version = state.version
    const confirmationEndpoint = endpoint(key)
    const body = { fields: fieldsToApi(state.fields), editedFields: [...state.editedFields] }
    state.confirmController?.abort()
    controller = new AbortController()
    state.confirmController = controller
    const signal = controller.signal
    await props.runPassportConfirmation(async () => {
      const snapshot = await $fetch<Snapshot>(confirmationEndpoint, { method: 'PATCH', baseURL: config.public.apiBase, credentials: 'include', body, signal })
      if (state.version === version && state.confirmController === controller) {
        applySnapshot(key, snapshot)
        toast.success('Паспортные данные сохранены')
      }
    })
  } catch (error: unknown) {
    if (!isAbort(error) && state.version === version && (!controller || state.confirmController === controller)) {
      const detail = (error as { data?: { detail?: { fields?: Partial<Record<PassportFieldKey, string>> } } })?.data?.detail
      state.fieldErrors = detail && typeof detail === 'object' ? detail.fields || {} : {}
      state.error = passportErrorMessage(error, 'Не удалось сохранить паспортные данные')
      toast.error(state.error)
    }
  } finally {
    if (!controller || state.confirmController === controller) state.saving = false
    emit('update', getData())
  }
}

const personGroup = (signer: Signer): 'founders' | 'beneficiaries' | 'other_representatives' => signer.role === 'founder' ? 'founders' : signer.role === 'beneficiary' ? 'beneficiaries' : 'other_representatives'
const matchesPerson = (person: QuestionnairePerson, signer: Signer) => person.signer_key === signer.key || (signer.role === 'beneficiary' && person.id === signer.key.slice('beneficiary:'.length)) || (!person.signer_key && signer.role === 'founder' && Boolean(signer.inn) && person.inn === signer.inn)
const personFlags = (signer: Signer): PersonFlags => {
  const q = checkoutStore.questionnaireData
  if (signer.role === 'director_applicant') return { is_pdl: q.director_is_pdl === true, pdl_related_person_name: q.director_pdl_related_person || '', name_changed: q.director_name_changed === true }
  const person = q[personGroup(signer)]?.find(row => matchesPerson(row, signer))
  return { is_pdl: person?.is_pdl === true, pdl_related_person_name: person?.pdl_related_person_name || '', name_changed: person?.name_changed === true }
}
const updatePersonFlags = (signer: Signer, patch: Partial<PersonFlags>) => {
  const flags = { ...personFlags(signer), ...patch }
  if (!flags.is_pdl) flags.pdl_related_person_name = ''
  let values: Partial<QuestionnaireData>
  if (signer.role === 'director_applicant') values = { director_is_pdl: flags.is_pdl, director_pdl_related_person: flags.pdl_related_person_name, director_name_changed: flags.name_changed }
  else {
    const group = personGroup(signer)
    const people = checkoutStore.questionnaireData[group] || []
    const exists = people.some(row => matchesPerson(row, signer))
    const next = exists ? people.map(row => matchesPerson(row, signer) ? { ...row, signer_key: signer.key, ...flags } : row) : [...people, { signer_key: signer.key, full_name: signer.name, inn: signer.inn || undefined, ...flags }]
    values = { [group]: next }
  }
  emit('update', values as Record<string, unknown>)
}

const isAlreadySigned = (signer: Signer) => sopdStatuses.value[signer.key]?.hasSignedSopd || false
const normalizePhone = (phone: string) => { const digits = phone.replace(/\D/g, ''); return digits.startsWith('8') ? `+7${digits.slice(1)}` : digits.startsWith('7') ? `+${digits}` : phone }
const createSignatureRequest = async (key: string) => {
  const invite = inviteState.value[key]
  const signer = signers.value.find(item => item.key === key)
  if (!invite || !signer || !current(key).actionsAllowed) throw new Error('Сначала сохраните актуальные паспортные данные')
  if (invite.signatureRequestId) return invite.signatureRequestId
  const companyId = checkoutStore.selectedCompanyId || checkoutStore.selectedApplicationCompany?.id
  if (!companyId) throw new Error('Не выбрана компания')
  const phone = invite.mode === 'sms' ? normalizePhone(invite.phone) : undefined
  if (invite.mode === 'sms' && !phone) throw new Error('Введите телефон в формате +7XXXXXXXXXX')
  const response = await $fetch<{ results?: Array<{ signature_request_ids?: UUID[] }> }>('/api/v1/signatures/invite', {
    method: 'POST', baseURL: config.public.apiBase, credentials: 'include',
    body: { company_id: companyId, application_id: props.applicationId, signers: [{ signerKey: signer.key, full_name: signer.name, inn: signer.inn, ...(phone ? { phone } : {}) }] },
  })
  const signatureRequestId = response.results?.[0]?.signature_request_ids?.[0]
  if (!signatureRequestId) throw new Error('Не удалось создать запрос СОПД')
  invite.signatureRequestId = signatureRequestId
  current(key).signatureRequestId = signatureRequestId
  if (phone) invite.phone = phone
  await fetchSopdStatus()
  syncInviteStates()
  return signatureRequestId
}
const onInviteSigner = async (key: string) => {
  const invite = inviteState.value[key]
  if (!invite) return
  if (invite.mode === 'sms' && !/^\+7\d{10}$/.test(normalizePhone(invite.phone))) { invite.error = 'Введите телефон в формате +7XXXXXXXXXX'; return }
  invite.sending = true
  invite.error = ''
  try {
    await createSignatureRequest(key)
    if (!invite.sent) throw new Error('Не удалось подтвердить статус отправленного приглашения')
    toast.success(`Приглашение отправлено на ${invite.phone}`)
  } catch (error: unknown) {
    invite.error = errorMessage(error, error instanceof Error ? error.message : 'Не удалось отправить приглашение')
    toast.error(invite.error)
  } finally {
    invite.sending = false
    emit('update', getData())
  }
}
const retryAfterMilliseconds = (value: string | null) => {
  const seconds = value ? Number.parseInt(value, 10) : 3
  return Number.isFinite(seconds) ? Math.min(Math.max(seconds, 1), 10) * 1000 : 3000
}
const cancelSopdDownload = () => sopdDownloadController?.abort()
const downloadSopd = async (key: string) => {
  const state = current(key)
  if (!state.actionsAllowed) { toast.error('Сначала сохраните актуальные паспортные данные'); return }
  sopdDownloadController?.abort()
  const controller = new AbortController()
  sopdDownloadController = controller
  downloadingSopd.value = true
  try {
    await createSignatureRequest(key)
    for (let attempt = 1; attempt <= 5; attempt += 1) {
      sopdDownloadMessage.value = attempt === 1 ? 'Формируем СОПД…' : `Формируем СОПД, попытка ${attempt} из 5…`
      const response = await $fetch.raw(`/api/v1/applications/${props.applicationId}/sopd-signers/${encodeURIComponent(key)}/paper-sopd`, {
        baseURL: config.public.apiBase, credentials: 'include', responseType: 'blob', ignoreResponseError: true, signal: controller.signal,
      })
      if (response.status === 200 && response._data instanceof Blob && response._data.type === 'application/pdf') {
        const url = window.URL.createObjectURL(response._data)
        const link = document.createElement('a')
        link.href = url
        link.download = 'СОПД.pdf'
        link.click()
        window.URL.revokeObjectURL(url)
        toast.success('СОПД скачан')
        return
      }
      if (response.status === 202 && attempt < 5) {
        await sleep(retryAfterMilliseconds(response.headers.get('retry-after')), controller.signal)
        continue
      }
      throw new Error(response.status === 202 ? 'Формирование СОПД заняло слишком много времени. Попробуйте скачать файл позднее.' : 'Не удалось скачать СОПД')
    }
  } catch (error: unknown) {
    if (isAbort(error)) toast.info('Формирование СОПД отменено')
    else toast.error(error instanceof Error ? error.message : 'Не удалось скачать СОПД')
  } finally {
    if (sopdDownloadController === controller) {
      sopdDownloadController = undefined
      downloadingSopd.value = false
      sopdDownloadMessage.value = ''
    }
  }
}
const handleSopdUpload = async (key: string, event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (file.size > 10 * 1024 * 1024) { toast.error('Размер файла не должен превышать 10 МБ'); return }
  if (!['application/pdf', 'image/jpeg', 'image/jpg', 'image/png'].includes(file.type)) { toast.error('Допустимые форматы: PDF, JPG, PNG'); return }
  try {
    const requestId = await createSignatureRequest(key)
    const body = new FormData()
    body.append('file', file)
    await $fetch(`/api/v1/signatures/${requestId}/upload-physical`, { method: 'POST', baseURL: config.public.apiBase, credentials: 'include', body })
    sopdFiles.value[key] = file
    await fetchSopdStatus()
    syncInviteStates()
    toast.success('Скан СОПД загружен')
  } catch {
    toast.error('Не удалось загрузить скан СОПД')
  } finally {
    ;(event.target as HTMLInputElement).value = ''
    emit('update', getData())
  }
}
const getData = (): Record<string, unknown> => ({ inviteState: { ...inviteState.value }, passport: Object.fromEntries(Object.entries(passportState.value).map(([key, state]) => [key, { hasUnsavedChanges: state.hasUnsavedChanges, actionsAllowed: state.actionsAllowed }])) })
const validate = () => signers.value.every(signer => current(signer.key).actionsAllowed || isAlreadySigned(signer))
const isComplete = () => signers.value.every(signer => inviteState.value[signer.key]?.sent || isAlreadySigned(signer))
onMounted(async () => { await Promise.all([fetchSopdStatus(), fetchCitizenships()]); syncInviteStates() })
onBeforeUnmount(() => { sopdDownloadController?.abort(); Object.values(passportState.value).forEach(cancelPassportState) })
defineExpose({ validate, getData, isComplete })
</script>
