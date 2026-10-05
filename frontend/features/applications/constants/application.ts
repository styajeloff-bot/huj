export const APPLICATION_STATUSES = {
  ACTIVE: 'active',
  REJECTED: 'rejected',
  ISSUED: 'issued'
} as const;

export const APPLICATION_STATUS_LABELS: Record<keyof typeof APPLICATION_STATUSES, string> = {
  ACTIVE: 'Активная',
  REJECTED: 'Отклонена',
  ISSUED: 'Выдана'
} as const;

export const APPLICATION_STATUS_COLORS: Record<keyof typeof APPLICATION_STATUSES, string> = {
  ACTIVE: 'blue',
  REJECTED: 'red',
  ISSUED: 'green'
} as const;

export const APPLICATION_STEPS = {
  VEHICLE_SELECTION: 'vehicle_selection',
  REQUESTED_CONDITIONS: 'requested_conditions',
  DOCUMENTS: 'documents',
  QUESTIONNAIRE: 'questionnaire',
  CONTACT_INFO: 'contact_info',
  CONFIRMATION: 'confirmation'
} as const;

export const APPLICATION_STEP_LABELS: Record<keyof typeof APPLICATION_STEPS, string> = {
  VEHICLE_SELECTION: 'Выбор автомобиля',
  REQUESTED_CONDITIONS: 'Запрашиваемые условия',
  DOCUMENTS: 'Документы',
  QUESTIONNAIRE: 'Анкета',
  CONTACT_INFO: 'Контактная информация',
  CONFIRMATION: 'Подтверждение'
} as const;

export const APPLICATION_STAGES = {
  REQUESTED_CONDITIONS: 'requested_conditions',
  DOCUMENTS: 'documents',
  QUESTIONNAIRE: 'questionnaire',
  CONTACTS: 'contacts',
  COMPLETED: 'completed'
} as const;

export const APPLICATION_STAGE_LABELS: Record<keyof typeof APPLICATION_STAGES, string> = {
  REQUESTED_CONDITIONS: 'Запрашиваемые условия',
  DOCUMENTS: 'Загрузка документов',
  QUESTIONNAIRE: 'Заполнение анкеты',
  CONTACTS: 'Контактные данные',
  COMPLETED: 'Завершено'
} as const;

export const QUESTIONNAIRE_STEPS = [
  {
    number: 1,
    id: 'general_info',
    title: 'Общие сведения',
    description: 'Основная информация о компании'
  },
  {
    number: 2,
    id: 'addresses',
    title: 'Адреса',
    description: 'Юридический и фактический адрес'
  },
  {
    number: 3,
    id: 'bank_details',
    title: 'Банковские реквизиты',
    description: 'Расчетный счет и банк'
  },
  {
    number: 4,
    id: 'director',
    title: 'Руководитель',
    description: 'Информация о генеральном директоре'
  },
  {
    number: 5,
    id: 'founders',
    title: 'Учредители',
    description: 'Список учредителей компании'
  },
  {
    number: 6,
    id: 'beneficiaries',
    title: 'Бенефициары',
    description: 'Бенефициарные владельцы'
  },
  {
    number: 7,
    id: 'management',
    title: 'Органы управления',
    description: 'Структура управления'
  },
  {
    number: 8,
    id: 'financial',
    title: 'Финансовые показатели',
    description: 'Выручка и прибыль компании'
  }
] as const;

export const VALIDATION_RULES = {
  NAME: {
    MIN_LENGTH: 2,
    MAX_LENGTH: 100,
    PATTERN: /^[а-яёА-ЯЁa-zA-Z\s-']+$/
  },
  EMAIL: {
    PATTERN: /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  },
  PHONE: {
    PATTERN: /^[\+]?[1-9][\d]{0,15}$/
  },
  INN: {
    INDIVIDUAL_LENGTH: 12,
    COMPANY_LENGTH: 10,
    PATTERN: /^\d+$/
  }
} as const;

export interface QuestionnaireData {
  company_phone?: string;
  company_email?: string;
  company_website?: string;
  website_in_blocked_domains_registry?: boolean;
  contact_person?: import('~/features/questionnaire/types').QuestionnaireContact;
  postal_address_matches_legal?: boolean;
  registration_date?: string;
  registration_authority_name?: string;
  correspondent_account?: string;
  director_inn?: string;
  director_snils?: string;
  director_is_pdl?: boolean;
  director_pdl_related_person?: string;
  director_name_changed?: boolean;
  no_beneficial_owner_reason?: string | null;
  no_beneficial_owner_reason_details?: string | null;
  employee_count?: number | null;
  electronic_document_management_systems?: import('~/features/questionnaire/types').ElectronicDocumentSystems;
  full_company_name?: string;
  short_company_name?: string;
  foreign_company_name?: string | null;
  inn?: string;
  ogrn?: string;
  kpp?: string;
  okpo?: string;
  okato?: string;
  okved_main?: string;
  okved_additional?: string;
  tax_system?: string;
  tax_system_auto?: boolean;
  company_docs_uploaded?: boolean;
  legal_form?: string;
  legal_address?: string;
  legal_address_matches_registration?: boolean;
  actual_address_same_as_legal?: boolean;
  actual_address?: string;
  actual_address_details?: string;
  postal_address?: string;
  phone?: string;
  fax?: string;
  email?: string;
  website?: string;
  bank_name?: string;
  bik?: string;
  settlement_account?: string;
  director_full_name?: string;
  director_surname?: string;
  director_first_name?: string;
  director_patronymic?: string;
  director_no_patronymic?: boolean;
  director_position?: string;
  director_share_percentage?: number;
  director_passport_series?: string;
  director_passport_number?: string;
  director_passport_issued_by?: string;
  director_passport_issue_date?: string;
  director_passport_department_code?: string;
  director_birth_date?: string;
  director_birth_place?: string;
  director_birth_country?: string;
  director_citizenship?: string;
  director_sex?: string;
  director_registration_address?: string;
  director_registration_country?: string;
  director_registration_postal_code?: string;
  director_registration_house?: string;
  director_registration_apartment?: string;
  director_registration_date?: string;
  director_actual_address?: string;
  director_actual_country?: string;
  director_actual_postal_code?: string;
  director_actual_house?: string;
  director_actual_apartment?: string;
  director_actual_same_as_registration?: boolean;
  director_phone?: string;
  director_email?: string;
  founders?: Array<import('~/features/questionnaire/types').QuestionnairePerson & {
    type?: 'individual' | 'legal';
    share_encumbrance?: string;
    citizenship?: string;
    surname?: string;
    first_name?: string;
    patronymic?: string;
    no_patronymic?: boolean;
    inn?: string;
    snils?: string;
    birth_date?: string;
    birth_place?: string;
    passport_series?: string;
    passport_number?: string;
    passport_issue_date?: string;
    passport_department_code?: string;
    passport_issued_by?: string;
    registration_country?: string;
    registration_postal_code?: string;
    registration_address?: string;
    registration_house?: string;
    registration_apartment?: string;
    registration_date?: string;
    actual_country?: string;
    actual_postal_code?: string;
    actual_address?: string;
    actual_house?: string;
    actual_apartment?: string;
    phone?: string;
    email?: string;
    share_percentage?: number;
    share_nominal_value?: number;
    share_paid_part?: number;
    full_name?: string;
    passport_data?: string;
  }>;
  beneficiaries?: import('~/features/questionnaire/types').QuestionnairePerson[];
  has_beneficiary?: boolean;
  other_representatives?: import('~/features/questionnaire/types').QuestionnairePerson[];
  representatives?: Array<{
    power_of_attorney_date?: string;
    power_of_attorney_expiry?: string;
    full_name?: string;
    surname?: string;
    first_name?: string;
    patronymic?: string;
    position?: string;
    birth_date?: string;
    birth_country?: string;
    birth_place?: string;
    phone?: string;
    email?: string;
    inn?: string;
    passport_series?: string;
    passport_number?: string;
    passport_issue_date?: string;
    passport_department_code?: string;
    passport_issued_by?: string;
  }>;
  beneficiary_info?: string;
  management_bodies?: Array<{
    name: string;
    members: string;
  }>;
  revenue_last_period_basis?: string;
  revenue_last_period_amount?: number;
  money_sources?: string;
  business_reputation?: string;
  employees_count?: number;
  questionnaire_date?: string;
  registration_department?: string;
  registration_country?: string;
  registration_city?: string;
  no_licensing_activity?: boolean;
  has_license?: boolean;
  license_series_number?: string;
  license_issue_date?: string;
  license_registry_number?: string;
  license_activity_types?: string;
  license_start_date?: string;
  license_end_date?: string;
  license_issued_by?: string;
  license_type?: string;
  contacts?: Array<{
    name?: string;
    position?: string;
    phone?: string;
    email?: string;
  }>;
}

export const QUESTIONNAIRE_REQUIRED_FIELDS = [
  'full_company_name',
  'short_company_name',
  'inn',
  'ogrn',
  'kpp',
  'okved_main',
  'legal_form',
  'legal_address',
  'actual_address',
  'phone',
  'email',
  'bank_name',
  'bik',
  'settlement_account',
  'director_full_name',
  'director_position',
  'director_passport_series',
  'director_passport_number',
  'director_birth_date',
  'director_phone',
  'director_email'
] as const;
