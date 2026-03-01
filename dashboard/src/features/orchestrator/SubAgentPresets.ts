export interface PresetOption {
  value: string
  label: string
  description: string
  raw: number
}

export const THINKING_STYLE_OPTIONS: PresetOption[] = [
  { value: 'creative', label: 'Creative', description: 'Exploratory, varied responses', raw: 1.0 },
  { value: 'balanced', label: 'Balanced', description: 'Good mix of variety and focus', raw: 0.7 },
  { value: 'precise', label: 'Precise', description: 'Focused, deterministic responses', raw: 0.3 },
]

export const PERSISTENCE_OPTIONS: PresetOption[] = [
  { value: 'quick', label: 'Quick', description: 'Fast results, up to 5 iterations', raw: 5 },
  { value: 'normal', label: 'Normal', description: 'Balanced, up to 15 iterations', raw: 15 },
  { value: 'thorough', label: 'Thorough', description: 'Deep work, up to 30 iterations', raw: 30 },
]

export const RESPONSE_LENGTH_OPTIONS: PresetOption[] = [
  { value: 'brief', label: 'Brief', description: 'Short and concise (~2K tokens)', raw: 2048 },
  { value: 'normal', label: 'Normal', description: 'Standard length (~4K tokens)', raw: 4096 },
  { value: 'detailed', label: 'Detailed', description: 'Comprehensive (~8K tokens)', raw: 8192 },
]
