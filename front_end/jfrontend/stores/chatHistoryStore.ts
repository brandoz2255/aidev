import { create } from 'zustand'
import { 
  validateMessageSessionIsolation,
  validateNewSessionIsolation,
  validateSessionSwitchIsolation,
  validateMessagePersistenceIsolation,
  validateCompleteSessionIsolation,
  logValidationResults,
  type ValidationResult,
  type SessionIsolationState
} from '@/lib/sessionIsolationValidator'

export interface ChatSession {
  id: string
  user_id: number
  title: string
  created_at: string
  updated_at: string
  last_message_at: string
  message_count: number
  model_used?: string
  is_active: boolean
}

export interface ChatMessage {
  id?: number
  session_id: string
  user_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  reasoning?: string
  model_used?: string
  input_type: 'text' | 'voice' | 'screen'
  metadata: Record<string, any>
  created_at?: string
}

export interface MessageHistoryResponse {
  messages: ChatMessage[]
  session: ChatSession
  total_count: number
}

interface ChatHistoryState {
  // Sessions
  sessions: ChatSession[]
  currentSession: ChatSession | null
  isLoadingSessions: boolean
  isCreatingSession: boolean
  
  // Messages
  messages: ChatMessage[]
  isLoadingMessages: boolean
  
  // UI State
  isHistoryVisible: boolean
  
  // Error handling
  error: string | null
  sessionError: string | null
  messageError: string | null
  
  // Actions
  fetchSessions: () => Promise<void>
  createSession: (title?: string, modelUsed?: string) => Promise<ChatSession | null>
  createNewSession: (title?: string, modelUsed?: string) => Promise<ChatSession | null>
  createInstantNewChat: (title?: string, modelUsed?: string) => void
  selectSession: (sessionId: string) => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>
  updateSessionTitle: (sessionId: string, title: string) => Promise<void>
  
  fetchSessionMessages: (sessionId: string) => Promise<void>
  clearMessages: () => void
  clearCurrentMessages: () => void
  
  // Error management
  setError: (error: string | null) => void
  setSessionError: (error: string | null) => void
  setMessageError: (error: string | null) => void
  clearErrors: () => void
  
  toggleHistoryVisibility: () => void
  setCurrentSession: (session: ChatSession | null) => void
  
  // Session isolation validation
  validateSessionIsolation: () => ValidationResult
}

const getAuthHeaders = (): Record<string, string> => {
  const token = localStorage.getItem('token')
  return token ? { 'Authorization': `Bearer ${token}` } : {}
}

export const useChatHistoryStore = create<ChatHistoryState>((set, get) => ({
  // Initial state
  sessions: [],
  currentSession: null,
  isLoadingSessions: false,
  isCreatingSession: false,
  messages: [],
  isLoadingMessages: false,
  isHistoryVisible: false,
  
  // Error state
  error: null,
  sessionError: null,
  messageError: null,
  
  // Session actions
  fetchSessions: async () => {
    set({ isLoadingSessions: true, sessionError: null })
    try {
      const response = await fetch('/api/chat-history/sessions', {
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
      })
      
      if (response.ok) {
        const sessions = await response.json()
        set({ sessions, isLoadingSessions: false, sessionError: null })
      } else {
        console.error('Failed to fetch sessions:', response.statusText)
        set({ 
          sessionError: 'Could not load chat sessions',
          isLoadingSessions: false 
        })
      }
    } catch (error) {
      console.error('Error fetching sessions:', error)
      set({ 
        sessionError: 'Could not load chat sessions',
        isLoadingSessions: false 
      })
    }
  },
  
  createSession: async (title = 'New Chat', modelUsed) => {
    set({ isCreatingSession: true, sessionError: null })
    
    try {
      const response = await fetch('/api/chat-history/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          title,
          model_used: modelUsed,
        }),
        signal: AbortSignal.timeout(5000), // Reduced to 5 second timeout
      })
      
      if (response.ok) {
        const newSession = await response.json()
        set(state => ({
          sessions: [newSession, ...state.sessions],
          currentSession: newSession,
          isCreatingSession: false,
        }))
        return newSession
      } else {
        console.error('Failed to create session:', response.statusText)
        set({ 
          sessionError: 'Could not start new chat',
          isCreatingSession: false 
        })
        return null
      }
    } catch (error) {
      console.error('Error creating session:', error)
      set({ 
        sessionError: 'Could not start new chat',
        isCreatingSession: false 
      })
      return null
    }
  },

  createNewSession: async (title = 'New Chat', modelUsed) => {
    const currentState = get()
    const previousSessionId = currentState.currentSession?.id || null
    
    // Clear current messages immediately for new session isolation
    set({ messages: [], messageError: null, isCreatingSession: true })
    
    try {
      // Call createSession directly instead of using get().createSession to avoid potential issues
      const response = await fetch('/api/chat-history/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          title,
          model_used: modelUsed,
        }),
        signal: AbortSignal.timeout(5000), // 5 second timeout
      })
      
      if (response.ok) {
        const newSession = await response.json()
        
        // Update state with new session
        set(state => ({
          sessions: [newSession, ...state.sessions],
          currentSession: newSession,
          messages: [],
          messageError: null,
          isCreatingSession: false,
          sessionError: null
        }))
        
        // Only validate in development mode to reduce production overhead
        if (process.env.NODE_ENV === 'development') {
          const validation = validateNewSessionIsolation(newSession, [], previousSessionId)
          logValidationResults('createNewSession', validation)
          
          if (!validation.isValid) {
            console.error('New session isolation validation failed:', validation.errors)
            set({ sessionError: 'Session isolation error - please refresh' })
          }
        }
        
        return newSession
      } else {
        console.error('Failed to create session:', response.statusText)
        
        // Fallback: Create a temporary local session if API fails
        const tempSession: ChatSession = {
          id: `temp-${Date.now()}`,
          user_id: 0,
          title: title,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          last_message_at: new Date().toISOString(),
          message_count: 0,
          model_used: modelUsed,
          is_active: true
        }
        
        set(state => ({
          sessions: [tempSession, ...state.sessions],
          currentSession: tempSession,
          messages: [],
          messageError: null,
          isCreatingSession: false,
          sessionError: null // Clear error since we have a fallback
        }))
        
        // Only validate in development mode
        if (process.env.NODE_ENV === 'development') {
          const validation = validateNewSessionIsolation(tempSession, [], previousSessionId)
          logValidationResults('createNewSession (fallback)', validation)
        }
        
        return tempSession
      }
    } catch (error) {
      console.error('Error creating session:', error)
      
      // Fallback: Create a temporary local session if API fails
      const tempSession: ChatSession = {
        id: `temp-${Date.now()}`,
        user_id: 0,
        title: title,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        last_message_at: new Date().toISOString(),
        message_count: 0,
        model_used: modelUsed,
        is_active: true
      }
      
      set(state => ({
        sessions: [tempSession, ...state.sessions],
        currentSession: tempSession,
        messages: [],
        messageError: null,
        isCreatingSession: false,
        sessionError: null // Clear error since we have a fallback
      }))
      
      // Only validate in development mode
      if (process.env.NODE_ENV === 'development') {
        const validation = validateNewSessionIsolation(tempSession, [], previousSessionId)
        logValidationResults('createNewSession (fallback)', validation)
      }
      
      return tempSession
    }
  },

  // 🚀 INSTANT NEW CHAT - ChatGPT-like performance
  createInstantNewChat: (title = 'New Chat', modelUsed) => {
    // Create new session object instantly - no API calls, no waiting
    const newSession: ChatSession = {
      id: `local-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      user_id: 0,
      title: title,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      last_message_at: new Date().toISOString(),
      message_count: 0,
      model_used: modelUsed,
      is_active: true
    }

    // Instantly update state - this is what makes it feel like ChatGPT
    set(state => ({
      sessions: [newSession, ...state.sessions], // Add to top of list
      currentSession: newSession,                // Set as current
      messages: [],                              // Clear messages (empty chat)
      messageError: null,                        // Clear any errors
      sessionError: null,                        // Clear any errors
      isCreatingSession: false                   // Not loading
    }))

    // Sync with API in background (non-blocking)
    setTimeout(async () => {
      try {
        const response = await fetch('/api/chat-history/sessions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeaders(),
          },
          body: JSON.stringify({
            title,
            model_used: modelUsed,
          }),
          signal: AbortSignal.timeout(3000),
        })

        if (response.ok) {
          const serverSession = await response.json()
          
          // Replace local session with server session
          set(state => ({
            sessions: state.sessions.map(s => 
              s.id === newSession.id ? serverSession : s
            ),
            currentSession: state.currentSession?.id === newSession.id 
              ? serverSession 
              : state.currentSession
          }))
        }
        // If API fails, keep the local session - user doesn't notice
      } catch (error) {
        // Silent fail - user experience is not affected
        console.log('Background sync failed, keeping local session')
      }
    }, 0) // Run immediately but non-blocking
  },
  
  selectSession: async (sessionId: string) => {
    const currentState = get()
    const session = currentState.sessions.find(s => s.id === sessionId)
    const previousSessionId = currentState.currentSession?.id || null
    
    // Prevent reselecting the same session
    if (session && session.id !== previousSessionId) {
      // Clear any previous errors and set the new session
      set({ currentSession: session, messageError: null })
      
      // Only fetch messages if we're not already loading them
      if (!get().isLoadingMessages) {
        await get().fetchSessionMessages(sessionId)
        
        // Only validate in development mode to reduce production overhead
        if (process.env.NODE_ENV === 'development') {
          const updatedState = get()
          const validation = validateSessionSwitchIsolation(
            previousSessionId,
            sessionId,
            updatedState.messages,
            updatedState.sessions
          )
          logValidationResults('selectSession', validation)
          
          if (!validation.isValid) {
            console.error('Session switch isolation validation failed:', validation.errors)
            set({ messageError: 'Session isolation error - messages may be mixed' })
          }
        }
      }
    }
  },
  
  deleteSession: async (sessionId: string) => {
    try {
      const response = await fetch(`/api/chat-history/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
      })
      
      if (response.ok) {
        set(state => ({
          sessions: state.sessions.filter(s => s.id !== sessionId),
          currentSession: state.currentSession?.id === sessionId ? null : state.currentSession,
          messages: state.currentSession?.id === sessionId ? [] : state.messages,
        }))
      } else {
        console.error('Failed to delete session:', response.statusText)
      }
    } catch (error) {
      console.error('Error deleting session:', error)
    }
  },
  
  updateSessionTitle: async (sessionId: string, title: string) => {
    try {
      const response = await fetch(`/api/chat-history/sessions/${sessionId}/title`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ title }),
      })
      
      if (response.ok) {
        set(state => ({
          sessions: state.sessions.map(s => 
            s.id === sessionId ? { ...s, title } : s
          ),
          currentSession: state.currentSession?.id === sessionId 
            ? { ...state.currentSession, title } 
            : state.currentSession,
        }))
      } else {
        console.error('Failed to update session title:', response.statusText)
      }
    } catch (error) {
      console.error('Error updating session title:', error)
    }
  },
  
  // Message actions
  fetchSessionMessages: async (sessionId: string) => {
    const currentState = get()
    
    // Prevent fetching if already loading for the same session
    if (currentState.isLoadingMessages && currentState.currentSession?.id === sessionId) {
      return
    }
    
    set({ isLoadingMessages: true, messageError: null })
    try {
      const authHeaders = getAuthHeaders()
      const response = await fetch(`/api/chat-history/sessions/${sessionId}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(authHeaders.Authorization ? { 'Authorization': authHeaders.Authorization } : {}),
        },
      })
      
      if (response.ok) {
        const data: MessageHistoryResponse = await response.json()
        const messages = data.messages || []
        
        // Only validate in development mode to reduce production overhead
        if (process.env.NODE_ENV === 'development') {
          const validation = validateMessageSessionIsolation(messages, sessionId)
          logValidationResults('fetchSessionMessages', validation)
          
          if (!validation.isValid) {
            console.error('Message session isolation validation failed:', validation.errors)
            set({ 
              messageError: 'Could not load chat history - session isolation error',
              isLoadingMessages: false 
            })
            return
          }
        }
        
        set({ 
          messages,
          isLoadingMessages: false,
          messageError: null
        })
        
        // Log for debugging in development only
        if (process.env.NODE_ENV === 'development') {
          console.log(`📨 Fetched ${messages.length} messages for session ${sessionId}`)
        }
      } else {
        console.error('Failed to fetch messages:', response.statusText)
        set({ 
          messageError: 'Could not load chat history',
          isLoadingMessages: false 
        })
      }
    } catch (error) {
      console.error('Error fetching messages:', error)
      set({ 
        messageError: 'Could not load chat history',
        isLoadingMessages: false 
      })
    }
  },
  
  clearMessages: () => {
    set({ messages: [] })
  },
  
  clearCurrentMessages: () => {
    set({ messages: [], messageError: null })
  },
  
  // Error management
  setError: (error: string | null) => {
    set({ error })
  },
  
  setSessionError: (error: string | null) => {
    set({ sessionError: error })
  },
  
  setMessageError: (error: string | null) => {
    set({ messageError: error })
  },
  
  clearErrors: () => {
    set({ error: null, sessionError: null, messageError: null })
  },
  
  // UI actions
  toggleHistoryVisibility: () => {
    set(state => ({ isHistoryVisible: !state.isHistoryVisible }))
  },
  
  setCurrentSession: (session: ChatSession | null) => {
    set({ currentSession: session })
  },
  
  // Session isolation validation
  validateSessionIsolation: () => {
    const state = get()
    const isolationState: SessionIsolationState = {
      currentSessionId: state.currentSession?.id || null,
      messages: state.messages,
      sessions: state.sessions
    }
    
    const validation = validateCompleteSessionIsolation(isolationState)
    logValidationResults('validateSessionIsolation', validation)
    
    if (!validation.isValid) {
      console.error('Session isolation validation failed:', validation.errors)
      set({ 
        error: 'Session isolation integrity compromised - please refresh the page',
        messageError: 'Session data may be corrupted'
      })
    }
    
    return validation
  },
}))