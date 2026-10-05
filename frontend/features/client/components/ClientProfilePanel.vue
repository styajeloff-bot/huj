<template>
  <div data-storefront-block="client.cabinet">
    <div class="mb-6">
      <h2 class="text-xl font-semibold text-[color:var(--storefront-title,#111827)]">
        Мой профиль
      </h2>
    </div>

    <div v-if="loading" class="text-center py-8">
      <div class="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-[color:var(--storefront-border,#2563eb)]"></div>
      <p class="mt-2 text-[color:var(--storefront-text-muted,#4b5563)]">Загружаем профиль...</p>
    </div>

    <div v-else-if="error" class="text-center py-8">
      <p class="text-[color:var(--storefront-error-text,#dc2626)] mb-4">{{ error }}</p>
      <button @click="fetchProfile" class="btn-primary">
        Попробовать снова
      </button>
    </div>

    <div v-else class="space-y-6">
      <!-- Основная информация -->
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
        <div class="flex flex-col gap-3 px-6 py-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-b border-[color:var(--storefront-border,#e5e7eb)] sm:flex-row sm:items-center sm:justify-between">
          <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">Основная информация</h3>
          <button
            type="button"
            @click="toggleEditMode"
            class="btn-primary w-fit"
          >
            {{ editMode ? 'Отменить' : 'Редактировать' }}
          </button>
        </div>
        
        <form @submit.prevent="saveProfile" class="p-6 space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Полное имя
              </label>
              <input
                v-model="profileForm.name"
                type="text"
                :disabled="!editMode"
                class="storefront-control input-field"
                :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
              >
            </div>
            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Email
              </label>
              <input
                v-model="profileForm.email"
                type="email"
                :disabled="!editMode"
                class="storefront-control input-field"
                :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
              >
            </div>
            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Телефон
              </label>
              <input
                v-model="profileForm.phone"
                type="tel"
                :disabled="!editMode"
                class="storefront-control input-field"
                :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
              >
            </div>
            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Дата рождения
              </label>
              <input
                v-model="profileForm.birth_date"
                type="date"
                :disabled="!editMode"
                class="storefront-control input-field"
                :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
              >
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
              Тип клиента
            </label>
            <select
              v-model="profileForm.client_type"
              :disabled="!editMode"
              class="storefront-control select-field"
              :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
            >
              <option value="entrepreneur">Индивидуальный предприниматель</option>
              <option value="legal">Юридическое лицо</option>
            </select>
          </div>

          <!-- Данные компании для юр.лиц -->
          <div v-if="profileForm.client_type === 'legal' || profileForm.client_type === 'entrepreneur'" class="space-y-4">
            <h4 class="text-md font-medium text-[color:var(--storefront-title,#111827)]">
              {{ profileForm.client_type === 'legal' ? 'Данные организации' : 'Данные ИП' }}
            </h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                  {{ profileForm.client_type === 'legal' ? 'Название организации' : 'ФИО ИП' }}
                </label>
                <input
                  v-model="profileForm.company_name"
                  type="text"
                  :disabled="!editMode"
                  class="storefront-control input-field"
                  :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
                >
              </div>
              <div>
                <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                  ИНН
                </label>
                <input
                  v-model="profileForm.inn"
                  type="text"
                  :disabled="!editMode"
                  class="storefront-control input-field"
                  :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
                >
              </div>
              <div v-if="profileForm.client_type === 'legal'">
                <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                  КПП
                </label>
                <input
                  v-model="profileForm.kpp"
                  type="text"
                  :disabled="!editMode"
                  class="storefront-control input-field"
                  :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
                >
              </div>
              <div v-if="profileForm.client_type === 'legal'">
                <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                  ОГРН
                </label>
                <input
                  v-model="profileForm.ogrn"
                  type="text"
                  :disabled="!editMode"
                  class="storefront-control input-field"
                  :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
                >
              </div>
            </div>

            <div>
              <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
                Юридический адрес
              </label>
              <textarea
                v-model="profileForm.legal_address"
                rows="3"
                :disabled="!editMode"
                class="storefront-control input-field"
                :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
              ></textarea>
            </div>
          </div>

          <div>
            <label class="block text-sm font-medium text-[color:var(--storefront-label,#374151)] mb-2">
              Адрес проживания/регистрации
            </label>
            <textarea
              v-model="profileForm.address"
              rows="3"
              :disabled="!editMode"
              class="storefront-control input-field"
              :class="{ 'bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))]': !editMode }"
            ></textarea>
          </div>

          <!-- Верификация нового номера телефона -->
          <div v-if="phoneChangeStep === 'awaiting_code'" class="bg-[color:rgb(var(--storefront-selected-rgb,239_246_255)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-border,#bfdbfe)] rounded-lg p-4">
            <p class="text-sm text-[color:var(--storefront-text,#1e40af)] mb-3">
              Код подтверждения отправлен на <strong>{{ profileForm.phone }}</strong>. Введите его для смены номера.
            </p>
            <div class="flex gap-3 items-start">
              <div class="flex-1">
                <input
                  v-model="phoneChangeCode"
                  type="text"
                  placeholder="0000"
                  maxlength="4"
                  class="storefront-control input-field"
                >
                <p v-if="phoneChangeError" class="text-[color:var(--storefront-error-text,#dc2626)] text-sm mt-1">{{ phoneChangeError }}</p>
              </div>
              <button
                type="button"
                @click="verifyPhoneChange"
                :disabled="phoneChangeLoading || phoneChangeCode.length !== 4"
                class="btn-primary"
              >
                <div v-if="phoneChangeLoading" class="flex items-center">
                  <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#ffffff)] mr-2"></div>
                  Проверка...
                </div>
                <span v-else>Подтвердить</span>
              </button>
              <button
                type="button"
                @click="cancelPhoneChange"
                class="btn-secondary"
              >
                Отмена
              </button>
            </div>
          </div>

          <div v-if="editMode" class="flex justify-end space-x-3">
            <button
              type="button"
              @click="toggleEditMode"
              class="btn-secondary"
            >
              Отмена
            </button>
            <button
              type="submit"
              :disabled="saving || phoneChangeStep === 'awaiting_code'"
              class="btn-primary"
            >
              <div v-if="saving" class="flex items-center">
                <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-[color:var(--storefront-border,#ffffff)] mr-2"></div>
                Сохранение...
              </div>
              <span v-else>Сохранить</span>
            </button>
          </div>
        </form>
      </div>

      <UserCompaniesSection />

      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
        <div class="px-6 py-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">Верификация</h3>
        </div>

        <div class="p-6 space-y-4">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">
                Mobile ID
              </div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">
                Подтверждение вашего аккаунта через сервис Mobile ID. Необходимо, для подписания документов.
              </div>
            </div>
            <div class="flex shrink-0 flex-col items-start gap-2 sm:items-end">
              <div v-if="isIdentityVerified" class="text-sm font-semibold text-[color:var(--storefront-success-text,#15803d)]">
                Профиль верифицирован!
              </div>
              <button
                v-else
                type="button"
                class="btn-primary w-fit"
                @click="showIdentityVerificationModal = true"
              >
                Пройти верификацию
              </button>
            </div>
          </div>
        </div>
      </div>

      <SOPDSection
        :signature="sopdSignature"
        :is-loading="isSopdLoading"
        @revoked="fetchSopdSignature"
      />

      <!-- Настройки уведомлений -->
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
        <div class="px-6 py-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">Настройки уведомлений</h3>
        </div>
        
        <div class="p-6 space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">Email уведомления</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Получать уведомления о статусе заявок на email</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="notificationSettings.email_notifications"
                type="checkbox"
                @change="saveNotificationSettings"
                class="storefront-control sr-only peer"
              >
              <div class="w-11 h-6 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-[color:var(--storefront-focus,#93c5fd)] rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-[color:var(--storefront-border,#ffffff)] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] after:border-[color:var(--storefront-border,#d1d5db)] after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))]"></div>
            </label>
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">SMS уведомления</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Получать SMS о важных изменениях</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="notificationSettings.sms_notifications"
                type="checkbox"
                @change="saveNotificationSettings"
                class="storefront-control sr-only peer"
              >
              <div class="w-11 h-6 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-[color:var(--storefront-focus,#93c5fd)] rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-[color:var(--storefront-border,#ffffff)] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] after:border-[color:var(--storefront-border,#d1d5db)] after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))]"></div>
            </label>
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">Маркетинговые рассылки</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Получать информацию о новых предложениях</div>
            </div>
            <label class="relative inline-flex items-center cursor-pointer">
              <input
                v-model="notificationSettings.marketing_emails"
                type="checkbox"
                @change="saveNotificationSettings"
                class="storefront-control sr-only peer"
              >
              <div class="w-11 h-6 bg-[color:rgb(var(--storefront-surface-muted-rgb,229_231_235)/var(--tw-bg-opacity,1))] peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-[color:var(--storefront-focus,#93c5fd)] rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-[color:var(--storefront-border,#ffffff)] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] after:border-[color:var(--storefront-border,#d1d5db)] after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-[color:rgb(var(--storefront-primary-rgb,37_99_235)/var(--tw-bg-opacity,1))]"></div>
            </label>
          </div>
        </div>
      </div>

      <!-- Статистика клиента -->
      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
        <div class="px-6 py-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">Моя статистика</h3>
        </div>
        
        <div class="p-6">
          <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div class="text-center">
              <div class="text-3xl font-bold text-[color:var(--storefront-text-muted,#2563eb)]">{{ stats.total_applications }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Всего заявок</div>
            </div>
            <div class="text-center">
              <div class="text-3xl font-bold text-[color:var(--storefront-success-text,#16a34a)]">{{ stats.approved_applications }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Одобренных заявок</div>
            </div>
            <div class="text-center">
              <div class="text-3xl font-bold text-[color:var(--storefront-info-text,#9333ea)]">{{ formatMoney(stats.total_amount) }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">Общая сумма заявок</div>
            </div>
          </div>

          <div class="mt-6 pt-6 border-t border-[color:var(--storefront-border,#e5e7eb)]">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 text-sm">
              <div>
                <div class="flex justify-between mb-2">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Дата регистрации:</span>
                  <span class="font-medium">{{ formatDate(profile.created_at) }}</span>
                </div>
                <div class="flex justify-between mb-2">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Последняя активность:</span>
                  <span class="font-medium">{{ formatDate(profile.last_activity) }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Статус:</span>
                  <span class="inline-flex px-2 py-1 text-xs font-semibold rounded-full bg-[color:rgb(var(--storefront-success-rgb,220_252_231)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-success-text,#166534)]">
                    Активный
                  </span>
                </div>
              </div>
              <div>
                <div class="flex justify-between mb-2">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Избранных автомобилей:</span>
                  <span class="font-medium">{{ stats.favorites_count }}</span>
                </div>
                <div class="flex justify-between mb-2">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Сохраненных расчетов:</span>
                  <span class="font-medium">{{ stats.saved_calculations }}</span>
                </div>
                <div class="flex justify-between">
                  <span class="text-[color:var(--storefront-text-muted,#4b5563)]">Загруженных документов:</span>
                  <span class="font-medium">{{ stats.documents_count }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Безопасность -->
      <SecurityPanel />

      <div class="bg-[color:rgb(var(--storefront-surface-rgb,255_255_255)/var(--tw-bg-opacity,1))] rounded-lg border border-[color:var(--storefront-border,#e5e7eb)] overflow-hidden">
        <div class="px-6 py-4 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] border-b border-[color:var(--storefront-border,#e5e7eb)]">
          <h3 class="text-lg font-medium text-[color:var(--storefront-title,#111827)]">История входов</h3>
        </div>
        <div class="p-6">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">Просмотр последних входов в систему</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">IP, устройство и время каждого входа</div>
            </div>
            <button class="btn-secondary" @click="showLoginHistory = true">
              Просмотреть
            </button>
          </div>
        </div>
      </div>

      <!-- Удаление аккаунта -->
      <div class="bg-[color:rgb(var(--storefront-error-rgb,254_242_242)/var(--tw-bg-opacity,1))] border border-[color:var(--storefront-error-border,#fecaca)] rounded-lg p-6">
        <h3 class="text-lg font-medium text-[color:var(--storefront-error-text,#7f1d1d)] mb-2">Удаление аккаунта</h3>
        <p class="text-sm text-[color:var(--storefront-error-text,#b91c1c)] mb-4">
          Это действие нельзя отменить. Все ваши данные, заявки и документы будут удалены безвозвратно.
        </p>
        <button @click="deleteAccount" class="storefront-action-destructive bg-[color:rgb(var(--storefront-destructive-rgb,220_38_38)/var(--tw-bg-opacity,1))] text-[color:var(--storefront-destructive-foreground,#ffffff)] px-4 py-2 rounded-lg hover:bg-[color:rgb(var(--storefront-destructive-hover-rgb,185_28_28)/var(--tw-bg-opacity,1))]">
          Удалить аккаунт
        </button>
      </div>
    </div>

    <!-- Модальные окна -->
    <Modal :show="showLoginHistory" @close="showLoginHistory = false">
      <div class="max-w-2xl mx-auto">
        <h3 class="text-lg font-semibold text-[color:var(--storefront-title,#111827)] mb-4">
          История входов
        </h3>
        
        <div class="space-y-3">
          <div v-for="login in loginHistory" :key="login.id" 
               class="flex items-center justify-between p-3 bg-[color:rgb(var(--storefront-surface-muted-rgb,249_250_251)/var(--tw-bg-opacity,1))] rounded-lg">
            <div>
              <div class="text-sm font-medium text-[color:var(--storefront-text,#111827)]">{{ login.ip_address }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ login.user_agent }}</div>
            </div>
            <div class="text-right">
              <div class="text-sm text-[color:var(--storefront-text,#111827)]">{{ formatDate(login.login_at) }}</div>
              <div class="text-sm text-[color:var(--storefront-text-muted,#6b7280)]">{{ login.location }}</div>
            </div>
          </div>
        </div>
      </div>
    </Modal>

    <MobileIdVerificationModal
      :show="showIdentityVerificationModal"
      :phone="profile.phone"
      :birth-date="profile.birth_date"
      @close="showIdentityVerificationModal = false"
      @verified="onIdentityVerified"
    />

  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '~/features/auth/store/auth'
import SecurityPanel from '~/features/auth/components/SecurityPanel.vue'
import SOPDSection from '~/features/client/components/SOPDSection.vue'
import MobileIdVerificationModal from '~/features/identity-verification/components/MobileIdVerificationModal.vue'
import UserCompaniesSection from '~/components/ui/UserCompaniesSection.vue'
import type { ClientProfile, ClientProfileStats, LoginHistoryEntry } from '~/types/features'
import type { SignatureListResponse, SignatureRequest } from '~/types/signature'

const config = useRuntimeConfig()
const { showToast } = useToast()
const logger = useLogger()

const profile = ref<ClientProfile>({})
const stats = ref<Partial<ClientProfileStats>>({})
const loginHistory = ref<LoginHistoryEntry[]>([])
const loading = ref(true)
const error = ref('')
const editMode = ref(false)
const saving = ref(false)
const notificationSettingsSaving = ref(false)
const notificationSettingsSavePending = ref(false)
const showLoginHistory = ref(false)
const sopdSignature = ref<SignatureRequest | null>(null)
const isSopdLoading = ref(false)
const showIdentityVerificationModal = ref(false)

const originalPhone = ref('')
const phoneChangeStep = ref('idle') // 'idle' | 'awaiting_code'
const phoneChangeCode = ref('')
const phoneChangeLoading = ref(false)
const phoneChangeError = ref('')

const profileForm = ref({
  name: '',
  email: '',
  phone: '',
  birth_date: '',
  client_type: 'individual',
  passport_series: '',
  passport_issued_date: '',
  passport_issued_by: '',
  company_name: '',
  inn: '',
  kpp: '',
  ogrn: '',
  legal_address: '',
  address: ''
})

const notificationSettings = ref({
  email_notifications: true,
  sms_notifications: true,
  marketing_emails: false
})

const notificationSettingsBody = () => ({
  email_notifications: notificationSettings.value.email_notifications,
  sms_notifications: notificationSettings.value.sms_notifications,
  marketing_emails: notificationSettings.value.marketing_emails
})

const isIdentityVerified = computed(() => profile.value.identity_verified === true)

const fetchProfile = async () => {
  loading.value = true
  error.value = ''

  try {
    // Phase 13 R13a — unified /users/me response. ``role_specific`` carries
    // the former /client/profile fields.
    const response = await $fetch<{
      id: number
      phone?: string
      email?: string
      name?: string
      role?: string
      role_specific?: Record<string, unknown> | null
    }>('/api/v1/users/me', {
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    const merged: ClientProfile = {
      id: response.id,
      phone: response.phone,
      email: response.email,
      name: response.name,
      ...(response.role_specific || {}),
    } as ClientProfile
    profile.value = merged
    stats.value = {}
    loginHistory.value = []

    // Заполняем форму данными профиля
    const formKeys = Object.keys(profileForm.value) as Array<keyof typeof profileForm.value>
    formKeys.forEach(key => {
      if (merged[key] !== undefined) {
        profileForm.value[key] = merged[key] as string
      }
    })
    originalPhone.value = profileForm.value.phone

    // Загружаем настройки уведомлений
    if (merged.notification_settings) {
      Object.assign(notificationSettings.value, merged.notification_settings)
    }
  } catch (err: unknown) {
    logger.error('Error fetching client profile', err)
    error.value = (err as { data?: { error?: string } }).data?.error || 'Ошибка при загрузке профиля'
  } finally {
    loading.value = false
  }
}

const fetchSopdSignature = async () => {
  isSopdLoading.value = true
  try {
    const response = await $fetch<SignatureListResponse>('/api/v1/signatures', {
      baseURL: config.public.apiBase,
      credentials: 'include',
      params: {
        status: 'pending,signed_electronic,signed_physical,revoked,cancelled',
      },
    })
    sopdSignature.value = response.items.find(
      (item) => item.document_type === 'sopd',
    ) || null
  } catch (err) {
    logger.error('Error fetching SOPD signature', err)
    sopdSignature.value = null
  } finally {
    isSopdLoading.value = false
  }
}

const saveProfile = async () => {
  // If phone changed, trigger SMS verification first — profile saved after code confirmed
  if (profileForm.value.phone !== originalPhone.value) {
    await requestPhoneChange()
    return
  }
  await doSaveProfile()
}

const requestPhoneChange = async () => {
  phoneChangeLoading.value = true
  phoneChangeError.value = ''
  try {
    await $fetch('/api/v1/users/me/phone-change', {
      method: 'POST',
      body: { new_phone: profileForm.value.phone },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    phoneChangeStep.value = 'awaiting_code'
  } catch (err: unknown) {
    logger.error('Error requesting phone change', err)
    showToast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка отправки кода на новый номер')
  } finally {
    phoneChangeLoading.value = false
  }
}

const verifyPhoneChange = async () => {
  phoneChangeLoading.value = true
  phoneChangeError.value = ''
  try {
    await $fetch('/api/v1/users/me/phone-change/verify', {
      method: 'POST',
      body: { new_phone: profileForm.value.phone, code: phoneChangeCode.value },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })
    phoneChangeStep.value = 'idle'
    phoneChangeCode.value = ''
    originalPhone.value = profileForm.value.phone
    await doSaveProfile()
  } catch (err: unknown) {
    logger.error('Error verifying phone change', err)
    phoneChangeError.value = (err as { data?: { error?: string } }).data?.error || 'Неверный код'
  } finally {
    phoneChangeLoading.value = false
  }
}

const cancelPhoneChange = () => {
  phoneChangeStep.value = 'idle'
  phoneChangeCode.value = ''
  phoneChangeError.value = ''
  profileForm.value.phone = originalPhone.value
}

const doSaveProfile = async () => {
  saving.value = true
  try {
    // Exclude phone (managed via phone-change flow) + split the form into
    // base-user fields (name/email) vs role-specific fields. Empty strings
    // are normalized to null.
    const { phone, name, email, ...roleSpecific } = profileForm.value
    void phone

    const coerce = (value: unknown) => (value === '' ? null : value)
    const baseBody: Record<string, unknown> = {}
    if (name !== undefined) baseBody.name = coerce(name)
    if (email !== undefined) baseBody.email = coerce(email)

    const roleSpecificBody: Record<string, unknown> = Object.fromEntries(
      Object.entries(roleSpecific).map(([k, v]) => [k, coerce(v)])
    )

    await $fetch('/api/v1/users/me', {
      method: 'PATCH',
      body: { ...baseBody, role_specific: roleSpecificBody },
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    showToast.success('Профиль обновлен')
    editMode.value = false
    await fetchProfile()
  } catch (err: unknown) {
    logger.error('Error saving client profile', err)
    showToast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка при сохранении профиля')
  } finally {
    saving.value = false
  }
}

const saveNotificationSettings = async () => {
  if (notificationSettingsSaving.value) {
    notificationSettingsSavePending.value = true
    return
  }

  notificationSettingsSaving.value = true
  try {
    do {
      notificationSettingsSavePending.value = false
      await $fetch('/api/v1/users/me', {
        method: 'PATCH',
        body: {
          role_specific: {
            notification_settings: notificationSettingsBody()
          }
        },
        baseURL: config.public.apiBase,
        credentials: 'include'
      })
    } while (notificationSettingsSavePending.value)

    showToast.success('Настройки уведомлений обновлены')
  } catch (err: unknown) {
    logger.error('Error saving notification settings', err)
    notificationSettingsSavePending.value = false
    showToast.error((err as { data?: { error?: string } }).data?.error || 'Ошибка при сохранении настроек уведомлений')
    await fetchProfile()
  } finally {
    notificationSettingsSaving.value = false
  }
}

const toggleEditMode = () => {
  if (editMode.value) {
    // Cancel: reset phone change state and restore phone
    phoneChangeStep.value = 'idle'
    phoneChangeCode.value = ''
    phoneChangeError.value = ''
    profileForm.value.phone = originalPhone.value
  }
  editMode.value = !editMode.value
}

const onIdentityVerified = async () => {
  showIdentityVerificationModal.value = false
  showToast.success('Профиль верифицирован')
  await fetchProfile()
}


const deleteAccount = async () => {
  const confirmation = prompt('Для подтверждения удаления аккаунта введите "УДАЛИТЬ":')
  if (confirmation !== 'УДАЛИТЬ') {
    return
  }

  try {
    // GDPR self-service erasure lives under DELETE /auth/me.
    await $fetch('/api/v1/auth/me', {
      method: 'DELETE',
      baseURL: config.public.apiBase,
      credentials: 'include'
    })

    showToast.success('Аккаунт удален')
    // Выходим из системы
    const authStore = useAuthStore()
    await authStore.logout()
    await navigateTo('/')
  } catch (err) {
    logger.error('Error deleting account', err)
    showToast.error('Ошибка при удалении аккаунта')
  }
}

const { formatPrice: formatSharedPrice } = useFormatPrice()
const { formatDate: formatSharedDate } = useFormatDate()

const formatDate = (dateString: string | undefined | null): string => {
  if (!dateString) return '-'
  return formatSharedDate(dateString)
}

const formatMoney = (amount: number | undefined | null): string => {
  if (!amount) return '0 ₽'
  return formatSharedPrice(amount)
}

onMounted(() => {
  fetchProfile()
  fetchSopdSignature()
})
</script>
