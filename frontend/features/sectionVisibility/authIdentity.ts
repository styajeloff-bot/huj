export interface SectionVisibilityAuthIdentity {
  id: string | null
  role: string | null
}

const sameIdentity = (
  left: SectionVisibilityAuthIdentity | null,
  right: SectionVisibilityAuthIdentity | null,
): boolean => {
  if (!left || !right) return left === right
  return left.id === right.id && left.role === right.role
}

export const createSectionVisibilityAuthIdentityTracker = (
  reset: () => void,
) => {
  let previous: SectionVisibilityAuthIdentity | null | undefined

  return (identity: SectionVisibilityAuthIdentity | null): boolean => {
    if (previous === undefined) {
      previous = identity ? { ...identity } : null
      return false
    }
    if (sameIdentity(previous, identity)) return false

    previous = identity ? { ...identity } : null
    reset()
    return true
  }
}
