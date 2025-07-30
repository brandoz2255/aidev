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
  createNewChat: () => Promise<ChatSession | null>
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

  clearCurrentChat: () => void
  refreshSessionMessages: (sessionId?: string) => Promise<void>
  
  toggleHistoryVisibility: () => void
  setCurrentSession: (session: ChatSession | null) => void
  setError: (error: string | null) => void
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
  error: null,
  
  // Error state
  error: null,
  sessionError: null,
  messageError: null,
  
  // Session actions
  fetchSessions: async () => {
    const state = get()
    
    // Prevent concurrent fetches
    if (state.isLoadingSessions) {
      return
    }

    // Check if user is logged in
    const token = localStorage.getItem('token')
    if (!token) {
      console.log('❌ No auth token found, user needs to login')
      set({ 
        isLoadingSessions: false,
        error: 'Please login to view chat history'
      })
      return
    }
    
    set({ isLoadingSessions: true, error: null })
    try {
      const response = await fetch('/api/chat-history/sessions', {
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        signal: AbortSignal.timeout(10000), // 10 second timeout
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
        set({ 
          sessions: Array.isArray(sessions) ? sessions : [],
          isLoadingSessions: false,
          error: null 
        })
      } else {
        const errorText = await response.text()
        console.error('Failed to fetch sessions:', response.statusText, errorText)
        
        // Handle auth errors specifically
        if (response.status === 401) {
          localStorage.removeItem('token') // Clear invalid token
          set({ 
            isLoadingSessions: false,
            error: 'Session expired. Please login again.'
          })
        } else {
          set({ 
            isLoadingSessions: false,
            error: 'Could not load chat history'
          })
        }
      }
    } catch (error) {
      console.error('Error fetching sessions:', error)
      set({ 
        sessionError: 'Could not load chat sessions',
        isLoadingSessions: false 
        isLoadingSessions: false,
        error: error instanceof Error && error.name === 'AbortError' 
          ? 'Request timed out' 
          : 'Could not load chat history'
      })
    }
  },
  
  createNewChat: async () => {
    const state = get()
    
    // Prevent concurrent new chat creation
    if (state.isLoadingSessions) {
      return null
    }
    
    try {
      set({ error: null, isLoadingSessions: true })
      
      // Generate unique title with timestamp
      const now = new Date()
      const title = `New Chat ${now.toLocaleString('en-US', { 
        month: 'short', 
        day: 'numeric', 
        hour: '2-digit', 
        minute: '2-digit' 
      })}`
      
      const response = await fetch('/api/chat-history/sessions', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          title,
        }),
        signal: AbortSignal.timeout(10000), // 10 second timeout
      })
      
      if (response.ok) {
        const newSession = await response.json()
        set(state => ({
          sessions: [newSession, ...state.sessions],
          currentSession: newSession,
          messages: [], // Completely clear messages for new chat
          isLoadingSessions: false,
          isLoadingMessages: false, // Reset message loading state
          error: null,
        }))
        
        console.log(`🆕 Created new chat session: ${newSession.id} with title: "${title}"`)
        return newSession
      } else {
        const errorText = await response.text()
        set({ 
          error: 'Could not start new chat', 
          isLoadingSessions: false 
        })
        console.error('Failed to create new chat:', errorText)
        return null
      }
    } catch (error) {
      const isTimeout = error instanceof Error && error.name === 'AbortError'
      set({ 
        error: isTimeout ? 'New chat creation timed out' : 'Could not start new chat', 
        isLoadingSessions: false 
      })
      console.error('Error creating new chat:', error)
      return null
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
    const state = get()
    const session = state.sessions.find(s => s.id === sessionId)
    
    console.log(`🔄 Switching to session ${sessionId}`)
    console.log(`📋 Session found:`, session ? 'Yes' : 'No')
    console.log(`🔄 Current session:`, state.currentSession?.id)
    console.log(`⏳ Already loading:`, state.isLoadingMessages)
    
    // Prevent reselecting the same session or selecting invalid sessions
    if (!session) {
      console.warn(`❌ Session ${sessionId} not found in sessions list`)
      return
    }
    
    if (session.id === state.currentSession?.id && state.messages.length > 0 && !state.isLoadingMessages) {
      console.log(`⏭️ Already on session ${sessionId} with messages loaded, skipping`)
      return
    }
    
    // Don't prevent concurrent switches, but ensure proper cleanup
    try {
      console.log(`✅ Setting current session to: ${session.title} (${sessionId})`)
      
      // Set session first, then load messages
      set({ 
        currentSession: session, 
        error: null,
        messages: [], // Clear messages immediately when switching
        isLoadingMessages: true
      })
      
      // Fetch messages for this session
      console.log(`📞 Calling fetchSessionMessages for: ${sessionId}`)
      
      // Set a timeout to reset loading state if fetch gets stuck
      const loadingTimeout = setTimeout(() => {
        const currentState = get()
        if (currentState.isLoadingMessages && currentState.currentSession?.id === sessionId) {
          console.log(`⏰ Loading timeout for session ${sessionId}, resetting state`)
          set({ 
            isLoadingMessages: false,
            error: 'Loading timed out, please try again'
          })
        }
      }, 20000) // 20 second timeout
      
      try {
        await get().fetchSessionMessages(sessionId)
        clearTimeout(loadingTimeout)
      } catch (error) {
        clearTimeout(loadingTimeout)
        throw error
      }
      
    } catch (error) {
      console.error(`❌ Error selecting session ${sessionId}:`, error)
      set({ 
        error: 'Could not load chat history',
        messages: [],
        isLoadingMessages: false
      })
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
    
    console.log(`🔄 Starting to fetch messages for session: ${sessionId}`)
    console.log(`🔄 Current loading state:`, currentState.isLoadingMessages)
    console.log(`🔄 Current session:`, currentState.currentSession?.id)

    // Check authentication first
    const token = localStorage.getItem('token')
    if (!token) {
      console.log('❌ No auth token found, cannot fetch messages')
      set({ 
        error: 'Please login to view chat messages',
        messages: [],
        isLoadingMessages: false 
      })
      return
    }
    
    // Only skip if we're loading AND already have messages for this session
    if (currentState.isLoadingMessages && currentState.currentSession?.id === sessionId && currentState.messages.length > 0) {
      console.log(`⏳ Already loading messages for session ${sessionId} and have messages, skipping duplicate request`)
      return
    }
    
    set({ isLoadingMessages: true, messageError: null })
    // Always set loading state to ensure UI updates
    set({ isLoadingMessages: true, error: null })
    
    try {
      const authHeaders = getAuthHeaders()
      console.log(`🔐 Auth headers for session fetch:`, authHeaders.Authorization ? 'Present' : 'Missing')
      
      const response = await fetch(`/api/chat-history/sessions/${sessionId}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(authHeaders.Authorization ? { 'Authorization': authHeaders.Authorization } : {}),
        },
        signal: AbortSignal.timeout(15000), // Increased timeout to 15 seconds
      })
      
      console.log(`🌐 API response status: ${response.status} ${response.statusText}`)
      
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

        console.log(`📊 Raw API response:`, { 
          messagesCount: data.messages?.length, 
          sessionTitle: data.session?.title,
          totalCount: data.total_count 
        })
        
        // Always update if we got a successful response
        const state = get()
        const messages = Array.isArray(data.messages) ? data.messages : []
        
        // Update session info if provided and matches current session
        const sessionUpdate = data.session && state.currentSession?.id === data.session.id 
          ? { currentSession: data.session } 
          : {}
        
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

          error: null,
          ...sessionUpdate
        })
        
        console.log(`📨 Successfully loaded ${messages.length} messages for session ${sessionId}`)
        
        // If we loaded messages but they're not showing, force a state update
        if (messages.length > 0) {
          // Small delay to ensure state propagation
          setTimeout(() => {
            const currentState = get()
            if (currentState.currentSession?.id === sessionId && currentState.messages.length !== messages.length) {
              console.log(`🔄 Force updating messages state for session ${sessionId}`)
              set({ messages })
            }
          }, 100)
        }
      } else {
        const errorText = await response.text()
        console.error(`❌ API Error ${response.status}:`, errorText)
        
        // Handle auth errors specifically
        if (response.status === 401) {
          localStorage.removeItem('token') // Clear invalid token
          set({ 
            error: 'Session expired. Please login again.',
            messages: [],
            isLoadingMessages: false 
          })
        } else {
          set({ 
            error: response.status === 404 ? 'Chat session not found' : 'Could not load chat history',
            messages: [],
            isLoadingMessages: false 
          })
        }
      }
    } catch (error) {
      const isTimeout = error instanceof Error && error.name === 'AbortError'
      console.error(`❌ Fetch error for session ${sessionId}:`, error)
      set({ 
        error: isTimeout ? 'Request timed out' : 'Could not load chat history',
        messages: [],
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
  clearCurrentChat: () => {
    set({ 
      messages: [],
      currentSession: null,
      error: null,
      isLoadingMessages: false, // Reset loading state
      isLoadingSessions: false, // Reset session loading state
    })
    console.log('🧹 Cleared current chat - complete context reset')
  },
  
  // Add a method to force refresh session messages
  refreshSessionMessages: async (sessionId?: string) => {
    const state = get()
    const targetSessionId = sessionId || state.currentSession?.id
    
    if (!targetSessionId) {
      console.log('🔄 No session to refresh')
      return
    }
    
    console.log(`🔄 Force refreshing messages for session: ${targetSessionId}`)
    
    // Force clear messages first
    set({ 
      messages: [],
      isLoadingMessages: true,
      error: null
    })
    
    // Small delay to ensure UI updates
    await new Promise(resolve => setTimeout(resolve, 50))
    
    // Fetch messages
    await get().fetchSessionMessages(targetSessionId)
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

  setError: (error: string | null) => {
    set({ error })
  },
}))