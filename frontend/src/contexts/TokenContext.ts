import { createContext, useContext } from 'react'

type TokenContextValue = {
  getToken: () => Promise<string | null>
}

export const TokenContext = createContext<TokenContextValue>({
  getToken: async () => null,
})

export const useToken = () => useContext(TokenContext)
