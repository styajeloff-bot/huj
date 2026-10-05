interface LogLevel {
  DEBUG: number
  INFO: number
  WARN: number
  ERROR: number
}

interface Logger {
  debug: (message: string, data?: any) => void
  info: (message: string, data?: any) => void
  warn: (message: string, data?: any) => void
  error: (message: string, error?: any) => void
}

export const useLogger = (): Logger => {
  const config = useRuntimeConfig()
  
  const levels: LogLevel = {
    DEBUG: 0,
    INFO: 1,
    WARN: 2,
    ERROR: 3
  }
  
  const currentLevel = process.env.NODE_ENV === 'development' ? levels.DEBUG : levels.WARN
  
  const formatMessage = (level: string, message: string, data?: any): string => {
    const timestamp = new Date().toISOString()
    const baseMessage = `[${timestamp}] ${level}: ${message}`
    
    if (data) {
      return `${baseMessage}\nData: ${JSON.stringify(data, null, 2)}`
    }
    
    return baseMessage
  }
  
  const shouldLog = (level: number): boolean => {
    return level >= currentLevel
  }
  
  return {
    debug: (message: string, data?: any) => {
      if (shouldLog(levels.DEBUG)) {
        console.debug(formatMessage('DEBUG', message, data))
      }
    },
    
    info: (message: string, data?: any) => {
      if (shouldLog(levels.INFO)) {
        console.info(formatMessage('INFO', message, data))
      }
    },
    
    warn: (message: string, data?: any) => {
      if (shouldLog(levels.WARN)) {
        console.warn(formatMessage('WARN', message, data))
      }
    },
    
    error: (message: string, error?: any) => {
      if (shouldLog(levels.ERROR)) {
        const errorData = error ? {
          message: error.message,
          stack: error.stack,
          status: error.status || error.statusCode,
          data: error.data
        } : undefined
        
        console.error(formatMessage('ERROR', message, errorData))
        
        if (process.env.NODE_ENV === 'production' && error) {
          // TODO: Интеграция с сервисом мониторинга ошибок
        }
      }
    }
  }
}
