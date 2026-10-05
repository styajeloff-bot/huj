const mutationErrorText = (error: unknown): string => error instanceof Error
  ? error.message
  : 'Не удалось изменить корзину спецтехники'

interface AuthoritativeSpecialEquipmentCartMutationOptions {
  mutate: () => Promise<void>
  reload: () => Promise<void>
}

export const runAuthoritativeSpecialEquipmentCartMutation = async ({
  mutate,
  reload,
}: AuthoritativeSpecialEquipmentCartMutationOptions): Promise<void> => {
  let mutationError: unknown = null
  try {
    await mutate()
  } catch (error: unknown) {
    mutationError = error
  }

  let reloadError: unknown = null
  try {
    await reload()
  } catch (error: unknown) {
    reloadError = error
  }

  if (mutationError !== null) {
    if (reloadError !== null) {
      throw new Error(`${mutationErrorText(mutationError)}. Не удалось обновить корзину: ${mutationErrorText(reloadError)}`)
    }
    throw mutationError
  }
  if (reloadError !== null) throw reloadError
}
