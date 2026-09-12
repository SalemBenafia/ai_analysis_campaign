'use client'

import { useState, useCallback } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { copilotService } from '@/lib/api/services'
import type { CopilotMessage } from '@/types'

export function useCopilot(conversationId: string | null) {
  const [localMessages, setLocalMessages] = useState<CopilotMessage[]>([])

  const historyQuery = useQuery({
    queryKey: ['copilot-messages', conversationId],
    queryFn: async () => {
      if (!conversationId) return []
      const { messages } = await copilotService.messages(conversationId)
      setLocalMessages(messages)
      return messages
    },
    enabled: !!conversationId,
  })

  const sendMutation = useMutation({
    mutationFn: ({ convId, message }: { convId: string; message: string }) =>
      copilotService.send(convId, message),
    onMutate: ({ message }) => {
      const userMsg: CopilotMessage = {
        id: 'tmp-' + Date.now(),
        role: 'user',
        content: message,
        created_at: new Date().toISOString(),
      }
      setLocalMessages((prev) => [...prev, userMsg])
    },
    onSuccess: (data) => {
      const aiMsg: CopilotMessage = {
        id: data.message_id,
        role: 'assistant',
        content: data.text,
        echart_config: data.echart_config,
        semantic_query: data.semantic_query,
        tool_calls: data.tool_calls as CopilotMessage['tool_calls'],
        created_at: new Date().toISOString(),
      }
      setLocalMessages((prev) => [...prev, aiMsg])
    },
  })

  const send = useCallback((message: string) => {
    if (!conversationId) return
    sendMutation.mutate({ convId: conversationId, message })
  }, [conversationId, sendMutation])

  return {
    messages: localMessages,
    isLoading: historyQuery.isLoading,
    isSending: sendMutation.isPending,
    send,
  }
}
