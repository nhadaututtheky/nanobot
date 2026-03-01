import { useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { rpc } from '@/ws/rpc'
import { useEvent } from '@/ws/provider'
import type { TaskGraph, GraphSummary, ModelInfo } from '@/types/orchestrator'

// ---------------------------------------------------------------------------
// Query keys
// ---------------------------------------------------------------------------

const keys = {
  list: ['orchestrator-graphs'] as const,
  detail: (id: string) => ['orchestrator-graph', id] as const,
  models: ['orchestrator-models'] as const,
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

export function useGraphList() {
  return useQuery({
    queryKey: keys.list,
    queryFn: () => rpc.orchestrator.graphList({ limit: 50 }),
    select: (d) => (d as { graphs: GraphSummary[] }).graphs,
    refetchInterval: 10_000,
  })
}

export function useGraph(graphId: string | null) {
  return useQuery({
    queryKey: keys.detail(graphId ?? ''),
    queryFn: () => rpc.orchestrator.graphGet({ graphId: graphId ?? '' }),
    select: (d) => d as TaskGraph,
    enabled: !!graphId,
    refetchInterval: 3_000,
  })
}

export function useModels() {
  return useQuery({
    queryKey: keys.models,
    queryFn: () => rpc.orchestrator.models(),
    select: (d) => (d as { models: ModelInfo[] }).models,
    staleTime: 60_000,
  })
}

export function useRunGoal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params: { goal: string; context?: string }) =>
      rpc.orchestrator.run(params),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.list })
    },
  })
}

export function useDecomposeGoal() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (params: { goal: string; context?: string }) =>
      rpc.orchestrator.decompose(params),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.list })
    },
  })
}

export function useExecuteGraph() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (graphId: string) => rpc.orchestrator.execute({ graphId }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.list })
    },
  })
}

export function useCancelGraph() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (graphId: string) => rpc.orchestrator.graphCancel({ graphId }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.list })
    },
  })
}

export function useRetryGraph() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (graphId: string) => rpc.orchestrator.graphRetry({ graphId }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.list })
    },
  })
}

export function useDeleteGraph() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (graphId: string) => rpc.orchestrator.graphDelete({ graphId }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.list })
    },
  })
}

/** Subscribe to orchestrator broadcast events and invalidate queries. */
export function useOrchestratorEvents() {
  const qc = useQueryClient()

  useEvent(
    'orchestrator',
    useCallback(
      (payload: unknown) => {
        const data = payload as { graphId?: string } | undefined
        void qc.invalidateQueries({ queryKey: keys.list })
        if (data?.graphId) {
          void qc.invalidateQueries({ queryKey: keys.detail(data.graphId) })
        }
      },
      [qc],
    ),
  )
}
