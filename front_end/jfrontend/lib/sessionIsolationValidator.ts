/**
 * Session Context Isolation Validator
 * 
 * This module provides validation functions to ensure complete isolation
 * between chat sessions, preventing any cross-contamination of messages
 * or context between different sessions.
 */

import { ChatMessage, ChatSession } from '@/stores/chatHistoryStore'

export interface ValidationResult {
  isValid: boolean
  errors: string[]
  warnings: string[]
}

export interface SessionIsolationState {
  currentSessionId: string | null
  messages: ChatMessage[]
  sessions: ChatSession[]
}

/**
 * Validates that messages belong only to the current session
 */
export function validateMessageSessionIsolation(
  messages: ChatMessage[],
  currentSessionId: string | null
): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (!currentSessionId) {
    if (messages.length > 0) {
      errors.push('Messages exist but no current session is selected')
    }
    return { isValid: errors.length === 0, errors, warnings }
  }

  // Check that all messages belong to the current session
  const invalidMessages = messages.filter(msg => msg.session_id !== currentSessionId)
  
  if (invalidMessages.length > 0) {
    errors.push(
      `Found ${invalidMessages.length} messages that don't belong to current session ${currentSessionId}`
    )
    
    // Log details for debugging
    invalidMessages.forEach((msg, index) => {
      errors.push(
        `Message ${index + 1}: belongs to session ${msg.session_id}, expected ${currentSessionId}`
      )
    })
  }

  // Check for duplicate session IDs in messages (shouldn't happen but good to validate)
  const sessionIds = new Set(messages.map(msg => msg.session_id))
  if (sessionIds.size > 1) {
    errors.push(
      `Messages contain multiple session IDs: ${Array.from(sessionIds).join(', ')}`
    )
  }

  return { isValid: errors.length === 0, errors, warnings }
}

/**
 * Validates that a new session starts with completely blank context
 */
export function validateNewSessionIsolation(
  newSession: ChatSession,
  messages: ChatMessage[],
  previousSessionId: string | null
): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  // New session should have no messages
  if (messages.length > 0) {
    errors.push(`New session ${newSession.id} should start with empty messages but has ${messages.length} messages`)
  }

  // Messages should not contain any from the previous session
  if (previousSessionId) {
    const previousSessionMessages = messages.filter(msg => msg.session_id === previousSessionId)
    if (previousSessionMessages.length > 0) {
      errors.push(
        `New session contains ${previousSessionMessages.length} messages from previous session ${previousSessionId}`
      )
    }
  }

  // New session should be marked as active
  if (!newSession.is_active) {
    warnings.push(`New session ${newSession.id} is not marked as active`)
  }

  // New session should have zero message count
  if (newSession.message_count > 0) {
    errors.push(`New session ${newSession.id} should have 0 messages but reports ${newSession.message_count}`)
  }

  return { isValid: errors.length === 0, errors, warnings }
}

/**
 * Validates that session switching properly isolates contexts
 */
export function validateSessionSwitchIsolation(
  fromSessionId: string | null,
  toSessionId: string,
  messages: ChatMessage[],
  sessions: ChatSession[]
): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  // Target session must exist
  const targetSession = sessions.find(s => s.id === toSessionId)
  if (!targetSession) {
    errors.push(`Target session ${toSessionId} not found in sessions list`)
    return { isValid: false, errors, warnings }
  }

  // Messages should only belong to the target session
  const invalidMessages = messages.filter(msg => msg.session_id !== toSessionId)
  if (invalidMessages.length > 0) {
    errors.push(
      `After switching to session ${toSessionId}, found ${invalidMessages.length} messages from other sessions`
    )
  }

  // If switching from another session, ensure no messages from the previous session remain
  if (fromSessionId && fromSessionId !== toSessionId) {
    const previousSessionMessages = messages.filter(msg => msg.session_id === fromSessionId)
    if (previousSessionMessages.length > 0) {
      errors.push(
        `After switching from session ${fromSessionId} to ${toSessionId}, ` +
        `still have ${previousSessionMessages.length} messages from previous session`
      )
    }
  }

  return { isValid: errors.length === 0, errors, warnings }
}

/**
 * Validates that message persistence maintains session isolation
 */
export function validateMessagePersistenceIsolation(
  message: ChatMessage,
  currentSessionId: string | null,
  allMessages: ChatMessage[]
): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  if (!currentSessionId) {
    errors.push('Cannot persist message without a current session')
    return { isValid: false, errors, warnings }
  }

  // Message must belong to current session
  if (message.session_id !== currentSessionId) {
    errors.push(
      `Message session_id ${message.session_id} doesn't match current session ${currentSessionId}`
    )
  }

  // Message should not duplicate existing messages (basic check)
  const duplicates = allMessages.filter(msg => 
    msg.session_id === message.session_id &&
    msg.content === message.content &&
    msg.role === message.role &&
    msg.created_at === message.created_at
  )

  if (duplicates.length > 1) {
    warnings.push(`Potential duplicate message detected in session ${message.session_id}`)
  }

  return { isValid: errors.length === 0, errors, warnings }
}

/**
 * Comprehensive validation of the entire session isolation state
 */
export function validateCompleteSessionIsolation(state: SessionIsolationState): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  // Validate message isolation
  const messageValidation = validateMessageSessionIsolation(state.messages, state.currentSessionId)
  errors.push(...messageValidation.errors)
  warnings.push(...messageValidation.warnings)

  // Validate session consistency
  if (state.currentSessionId) {
    const currentSession = state.sessions.find(s => s.id === state.currentSessionId)
    if (!currentSession) {
      errors.push(`Current session ${state.currentSessionId} not found in sessions list`)
    } else {
      // Validate message count consistency
      const actualMessageCount = state.messages.filter(m => m.session_id === state.currentSessionId).length
      if (currentSession.message_count !== actualMessageCount) {
        warnings.push(
          `Session ${state.currentSessionId} reports ${currentSession.message_count} messages ` +
          `but actually has ${actualMessageCount} messages loaded`
        )
      }
    }
  }

  // Validate no orphaned messages (messages without corresponding sessions)
  const sessionIds = new Set(state.sessions.map(s => s.id))
  const orphanedMessages = state.messages.filter(msg => !sessionIds.has(msg.session_id))
  if (orphanedMessages.length > 0) {
    errors.push(`Found ${orphanedMessages.length} messages with no corresponding session`)
  }

  return { isValid: errors.length === 0, errors, warnings }
}

/**
 * Validates that UI state is synchronized with session state
 */
export function validateUISessionSynchronization(
  currentSessionId: string | null,
  highlightedSessionId: string | undefined,
  displayedMessages: ChatMessage[],
  storeMessages: ChatMessage[]
): ValidationResult {
  const errors: string[] = []
  const warnings: string[] = []

  // Current session should match highlighted session
  if (currentSessionId !== (highlightedSessionId || null)) {
    errors.push(
      `UI highlighting mismatch: current session is ${currentSessionId} ` +
      `but highlighted session is ${highlightedSessionId}`
    )
  }

  // Displayed messages should match store messages for current session
  if (currentSessionId) {
    const expectedMessages = storeMessages.filter(msg => msg.session_id === currentSessionId)
    const actualDisplayedMessages = displayedMessages.filter(msg => msg.session_id === currentSessionId)

    if (expectedMessages.length !== actualDisplayedMessages.length) {
      errors.push(
        `Message display mismatch: store has ${expectedMessages.length} messages ` +
        `for session ${currentSessionId} but UI displays ${actualDisplayedMessages.length}`
      )
    }

    // Check message content consistency (basic check)
    const contentMismatch = expectedMessages.some((expected, index) => {
      const actual = actualDisplayedMessages[index]
      return !actual || actual.content !== expected.content || actual.role !== expected.role
    })

    if (contentMismatch) {
      warnings.push(`Message content mismatch detected between store and UI for session ${currentSessionId}`)
    }
  }

  return { isValid: errors.length === 0, errors, warnings }
}

/**
 * Creates a validation report for debugging
 */
export function createValidationReport(
  state: SessionIsolationState,
  highlightedSessionId?: string,
  displayedMessages?: ChatMessage[]
): string {
  const report: string[] = []
  
  report.push('=== Session Isolation Validation Report ===')
  report.push(`Timestamp: ${new Date().toISOString()}`)
  report.push(`Current Session: ${state.currentSessionId || 'None'}`)
  report.push(`Total Sessions: ${state.sessions.length}`)
  report.push(`Total Messages: ${state.messages.length}`)
  report.push('')

  // Complete isolation validation
  const completeValidation = validateCompleteSessionIsolation(state)
  report.push('Complete Session Isolation:')
  report.push(`  Valid: ${completeValidation.isValid}`)
  if (completeValidation.errors.length > 0) {
    report.push('  Errors:')
    completeValidation.errors.forEach(error => report.push(`    - ${error}`))
  }
  if (completeValidation.warnings.length > 0) {
    report.push('  Warnings:')
    completeValidation.warnings.forEach(warning => report.push(`    - ${warning}`))
  }
  report.push('')

  // UI synchronization validation if data provided
  if (highlightedSessionId !== undefined && displayedMessages) {
    const uiValidation = validateUISessionSynchronization(
      state.currentSessionId,
      highlightedSessionId,
      displayedMessages,
      state.messages
    )
    report.push('UI Synchronization:')
    report.push(`  Valid: ${uiValidation.isValid}`)
    if (uiValidation.errors.length > 0) {
      report.push('  Errors:')
      uiValidation.errors.forEach(error => report.push(`    - ${error}`))
    }
    if (uiValidation.warnings.length > 0) {
      report.push('  Warnings:')
      uiValidation.warnings.forEach(warning => report.push(`    - ${warning}`))
    }
  }

  return report.join('\n')
}

/**
 * Development helper to log validation results
 */
export function logValidationResults(
  context: string,
  validation: ValidationResult,
  logLevel: 'error' | 'warn' | 'info' = 'info'
): void {
  if (!validation.isValid || validation.warnings.length > 0) {
    const prefix = `[Session Isolation - ${context}]`
    
    if (validation.errors.length > 0) {
      console.error(`${prefix} Validation failed:`, validation.errors)
    }
    
    if (validation.warnings.length > 0) {
      console.warn(`${prefix} Validation warnings:`, validation.warnings)
    }
  } else if (logLevel === 'info') {
    console.log(`[Session Isolation - ${context}] Validation passed`)
  }
}