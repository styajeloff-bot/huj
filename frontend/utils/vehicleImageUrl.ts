export const VEHICLE_IMAGE_PLACEHOLDER = '/images/car-placeholder.png'

const VEHICLE_IMAGE_PREFIX = '/api/v1/cars/images/'

export const vehicleImageUrl = (filename: unknown): string => {
  if (typeof filename !== 'string' || filename.length === 0) {
    return VEHICLE_IMAGE_PLACEHOLDER
  }

  if (filename.startsWith(VEHICLE_IMAGE_PREFIX)) return filename

  return `${VEHICLE_IMAGE_PREFIX}${encodeURIComponent(filename)}`
}
