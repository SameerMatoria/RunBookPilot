import { createContext, useContext } from 'react'
import { hasRole } from './api.js'

export const SessionContext = createContext({ user: null, signOut: () => {} })

export function useSession() {
  const session = useContext(SessionContext)
  return { ...session, can: (role) => hasRole(session.user, role) }
}
