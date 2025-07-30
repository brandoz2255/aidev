/**
 * Hook for session isolation validation in React components
 */

import { useEffect, useCallback } from 'react'
import { useChatHistoryStore } from '@/stores/chatHistoryStore'
import { 
  validateUISessionSynchronization,
  createValidationReport,
  logValidationResults,
  type ValidationResult
} from '@/lib/sessionIsolationValidator'

interface UseSessionIsolationValidationOptions {
  enableAutoValidation?: boolean
  validationInterval?: number
  logLevel?: 'error' | 'warn' | 'info'
}

interface SessionIsolationValidationHook {
  validateCurrentState: () => ValidationResult
  validateUISync: (highlightedSessionId?: string, displayedMessages?: any[]) => ValidationResult
  generateValidationReport: () => string
  isValidationEnabled: boolean
}

export function useSessionIsolationValidation(
  options: UseSessionIsolationValidationOptions = {}
): SessionIsolationValidationHook {
  const {
    enableAutoValidation = process.env.NODE_ENV === 'development',
    validationInterval = 30000, // Increased to 30 seconds to reduce overhead
    logLevel = 'warn'
  } = options

  const { 
    currentSession, 
    messages, 
    sessions, 
    validateSessionIsolation 
  } = useChatHistoryStore()

  // Validate current session isolation state
  const validateCurrentState = useCallback((): ValidationResult => {
    return validateSessionIsolation()
  }, [validateSessionIsolation])

  // Validate UI synchronization
  const validateUISync = useCallback((
    highlightedSessionId?: string,
    displayedMessages?: any[]
  ): ValidationResult => {
    const validation = validateUISessionSynchronization(
      currentSession?.id || null,
      highlightedSessionId,
      displayedMessages || [],
      messages
    )
    
    logValidationResults('UI Synchronization', validation, logLevel)
    return validation
  }, [currentSession?.id, messages, logLevel])

  // Generate comprehensive validation report
  const generateValidationReport = useCallback((): string => {
    const isolationState = {
      currentSessionId: currentSession?.id || null,
      messages,
      sessions
    }
    
    return createValidationReport(isolationState)
  }, [currentSession?.id, messages, sessions])

  // Auto-validation effect
  useEffect(() => {
    if (!enableAutoValidation) return

    const intervalId = setInterval(() => {
      const validation = validateCurrentState()
      
      if (!validation.isValid) {
        console.error('Automatic session isolation validation failed:', validation.errors)
        
        // In development, also log the full report
        if (process.env.NODE_ENV === 'development') {
          console.log('Full validation report:', generateValidationReport())
        }
      }
    }, validationInterval)

    return () => clearInterval(intervalId)
  }, [enableAutoValidation, validationInterval, validateCurrentState, generateValidationReport])

  // Validate on session changes
  useEffect(() => {
    if (enableAutoValidation && currentSession) {
      // Small delay to allow state to settle
      const timeoutId = setTimeout(() => {
        const validation = validateCurrentState()
        if (!validation.isValid) {
          console.error('Session change validation failed:', validation.errors)
        }
      }, 100)

      return () => clearTimeout(timeoutId)
    }
  }, [currentSession?.id, enableAutoValidation, validateCurrentState])

  // Validate on message changes
  useEffect(() => {
    if (enableAutoValidation && messages.length > 0) {
      // Small delay to allow state to settle
      const timeoutId = setTimeout(() => {
        const validation = validateCurrentState()
        if (!validation.isValid) {
          console.error('Message change validation failed:', validation.errors)
        }
      }, 100)

      return () => clearTimeout(timeoutId)
    }
  }, [messages.length, enableAutoValidation, validateCurrentState])

  return {
    validateCurrentState,
    validateUISync,
    generateValidationReport,
    isValidationEnabled: enableAutoValidation
  }
}

/**
 * Development helper hook for debugging session isolation
 */
export function useSessionIsolationDebugger() {
  const { 
    currentSession, 
    messages, 
    sessions,
    isLoadingMessages,
    messageError,
    sessionError
  } = useChatHistoryStore()

  const { generateValidationReport, validateCurrentState } = useSessionIsolationValidation({
    enableAutoValidation: false
  })

  // Expose debugging functions to window in development
  useEffect(() => {
    if (process.env.NODE_ENV === 'development') {
      (window as any).sessionIsolationDebug = {
        getCurrentState: () => ({
          currentSession,
          messages,
          sessions,
          isLoadingMessages,
          messageError,
          sessionError
        }),
        validateState: validateCurrentState,
        getReport: generateValidationReport,
        logState: () => {
          console.log('=== Session Isolation Debug State ===')
          console.log('Current Session:', currentSession)
          console.log('Messages:', messages)
          console.log('Sessions:', sessions)
          console.log('Loading:', isLoadingMessages)
          console.log('Errors:', { messageError, sessionError })
          console.log('Validation Report:', generateValidationReport())
        }
      }
    }

    return () => {
      if (process.env.NODE_ENV === 'development') {
        delete (window as any).sessionIsolationDebug
      }
    }
  }, [
    currentSession, 
    messages, 
    sessions, 
    isLoadingMessages, 
    messageError, 
    sessionError,
    validateCurrentState,
    generateValidationReport
  ])

  return {
    debugState: {
      currentSession,
      messages,
      sessions,
      isLoadingMessages,
      messageError,
      sessionError
    },
    validateState: validateCurrentState,
    getReport: generateValidationReport
  }
}