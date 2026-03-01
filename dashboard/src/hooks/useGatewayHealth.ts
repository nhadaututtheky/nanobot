import { useQuery } from '@tanstack/react-query'
import { gatewayApi } from '@/api/gateway'

export function useGatewayHealth(enabled = true) {
  return useQuery({
    queryKey: ['gateway', 'health'],
    queryFn: () => gatewayApi.health(),
    refetchInterval: 30_000,
    retry: 1,
    enabled,
  })
}
