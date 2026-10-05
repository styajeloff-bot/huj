import type { UUID } from '~/types/ids'

export interface BankStatementUploadItem {
  file_name: string
  import_id: UUID
  document_id?: UUID | null
  status: string
  transactions_count: number
  recognized_transactions_count: number
  accounts_count: number
  period_start?: string | null
  period_end?: string | null
}

export interface BankStatementUploadResponse {
  items: BankStatementUploadItem[]
  total_transactions_count: number
  total_recognized_transactions_count: number
}

export const useBankStatementUpload = () => {
  const config = useRuntimeConfig()

  const uploadBankStatements = async (
    files: File[],
    applicationId?: UUID | null,
  ): Promise<BankStatementUploadResponse> => {
    const formData = new FormData()

    for (const file of files) {
      formData.append('files', file)
    }

    if (applicationId) {
      formData.append('application_id', applicationId)
    }

    return await $fetch<BankStatementUploadResponse>('/api/v1/bank-statements/uploads', {
      method: 'POST',
      baseURL: config.public.apiBase,
      body: formData,
      credentials: 'include',
    })
  }

  return {
    uploadBankStatements,
  }
}
