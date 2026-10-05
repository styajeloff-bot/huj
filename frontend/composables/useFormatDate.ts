export const useFormatDate = () => {
  const numericDateOptions: Intl.DateTimeFormatOptions = {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  }

  const formatDate = (dateString: string | Date | null | undefined, options?: Intl.DateTimeFormatOptions): string => {
    if (!dateString) return 'Не указано'
    
    try {
      const date = typeof dateString === 'string' ? new Date(dateString) : dateString
      
      if (isNaN(date.getTime())) {
        return 'Неверная дата'
      }
      
      return date.toLocaleDateString('ru-RU', { ...numericDateOptions, ...options })
    } catch (error) {
      return 'Ошибка формата'
    }
  }

  const formatDateTime = (dateString: string | Date | null | undefined): string => {
    if (!dateString) return 'Не указано'
    
    try {
      const date = typeof dateString === 'string' ? new Date(dateString) : dateString
      
      if (isNaN(date.getTime())) {
        return 'Неверная дата'
      }
      
      return date.toLocaleString('ru-RU', {
        ...numericDateOptions,
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch (error) {
      return 'Ошибка формата'
    }
  }

  const formatTime = (dateString: string | Date | null | undefined): string => {
    if (!dateString) return 'Не указано'
    
    try {
      const date = typeof dateString === 'string' ? new Date(dateString) : dateString
      
      if (isNaN(date.getTime())) {
        return 'Неверная дата'
      }
      
      return date.toLocaleTimeString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch (error) {
      return 'Ошибка формата'
    }
  }

  const formatRelativeTime = (dateString: string | Date | null | undefined): string => {
    if (!dateString) return 'Не указано'
    
    try {
      const date = typeof dateString === 'string' ? new Date(dateString) : dateString
      
      if (isNaN(date.getTime())) {
        return 'Неверная дата'
      }
      
      const now = new Date()
      const diffMs = now.getTime() - date.getTime()
      const diffSec = Math.floor(diffMs / 1000)
      const diffMin = Math.floor(diffSec / 60)
      const diffHour = Math.floor(diffMin / 60)
      const diffDay = Math.floor(diffHour / 24)
      
      if (diffSec < 60) {
        return 'только что'
      } else if (diffMin < 60) {
        return `${diffMin} ${diffMin === 1 ? 'минуту' : diffMin < 5 ? 'минуты' : 'минут'} назад`
      } else if (diffHour < 24) {
        return `${diffHour} ${diffHour === 1 ? 'час' : diffHour < 5 ? 'часа' : 'часов'} назад`
      } else if (diffDay < 7) {
        return `${diffDay} ${diffDay === 1 ? 'день' : diffDay < 5 ? 'дня' : 'дней'} назад`
      } else {
        return formatDate(date)
      }
    } catch (error) {
      return 'Ошибка формата'
    }
  }

  const formatDateToDDMMYYYY = (date: string | Date | null | undefined): string => {
    if (!date) return ''
    try {
      const dateObj = typeof date === 'string' ? new Date(date) : date
      if (isNaN(dateObj.getTime())) return ''
      const day = String(dateObj.getDate()).padStart(2, '0')
      const month = String(dateObj.getMonth() + 1).padStart(2, '0')
      const year = dateObj.getFullYear()
      return `${day}.${month}.${year}`
    } catch {
      return ''
    }
  }

  const formatDateToYYYYMMDD = (date: string | null | undefined): string => {
    if (!date) return ''
    const parts = date.split('.')
    if (parts.length === 3) {
      const [day, month, year] = parts
      return `${year}-${month.padStart(2, '0')}-${day.padStart(2, '0')}`
    }
    return date
  }

  return {
    formatDate,
    formatDateTime,
    formatTime,
    formatRelativeTime,
    formatDateToDDMMYYYY,
    formatDateToYYYYMMDD
  }
}
