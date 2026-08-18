const SESSION_KEY = 'greenfab-loop-api-key'

let inMemoryApiKey: string | null = null

const sessionStore = () => {
  if (typeof window === 'undefined') return null
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

export const getSessionApiKey = () => {
  if (inMemoryApiKey) return inMemoryApiKey

  let stored = ''
  try {
    stored = sessionStore()?.getItem(SESSION_KEY)?.trim() ?? ''
  } catch {
    stored = ''
  }
  inMemoryApiKey = stored || null
  return inMemoryApiKey
}

export const setSessionApiKey = (apiKey: string) => {
  const normalized = apiKey.trim()
  if (normalized.length < 16 || normalized.length > 512) {
    throw new Error('API Access Key는 16자 이상 512자 이하여야 합니다.')
  }

  inMemoryApiKey = normalized
  try {
    sessionStore()?.setItem(SESSION_KEY, normalized)
  } catch {
    // The in-memory credential still supports privacy-restricted browsers.
  }
}

export const clearSessionApiKey = () => {
  inMemoryApiKey = null
  try {
    sessionStore()?.removeItem(SESSION_KEY)
  } catch {
    // Nothing else to clear when session storage is unavailable.
  }
}
