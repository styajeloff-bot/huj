interface TooltipHorizontalPosition {
  triggerCenterX: number
  tooltipWidth: number
  viewportWidth: number
  viewportPadding: number
}

interface TooltipVerticalPosition {
  triggerTop: number
  triggerBottom: number
  tooltipHeight: number
  viewportHeight: number
  viewportPadding: number
  gap: number
}

export const calculateTooltipLeft = ({
  triggerCenterX,
  tooltipWidth,
  viewportWidth,
  viewportPadding,
}: TooltipHorizontalPosition): number => {
  const minimumLeft = viewportPadding
  const maximumLeft = Math.max(
    minimumLeft,
    viewportWidth - viewportPadding - tooltipWidth,
  )
  const centeredLeft = triggerCenterX - tooltipWidth / 2

  return Math.min(Math.max(centeredLeft, minimumLeft), maximumLeft)
}

export const calculateTooltipTop = ({
  triggerTop,
  triggerBottom,
  tooltipHeight,
  viewportHeight,
  viewportPadding,
  gap,
}: TooltipVerticalPosition): number => {
  const minimumTop = viewportPadding
  const maximumTop = Math.max(
    minimumTop,
    viewportHeight - viewportPadding - tooltipHeight,
  )
  const below = triggerBottom + gap
  if (below >= minimumTop && below <= maximumTop) return below

  const above = triggerTop - gap - tooltipHeight
  if (above >= minimumTop && above <= maximumTop) return above

  return Math.min(Math.max(below, minimumTop), maximumTop)
}
