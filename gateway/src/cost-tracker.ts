/**
 * Cost Tracker — estimates per-turn cost for each live-voice provider.
 *
 * Pricing is based on published API rates as of mid-2026.
 * Estimates use audio duration + text character counts when available.
 *
 * OpenAI Realtime (gpt-4o-realtime-preview):
 *   Audio input:  $100/1M tokens (~$0.10/min at typical 1 token ≈ 32ms audio)
 *   Audio output: $200/1M tokens (~$0.20/min)
 *   Text input:   $5/1M tokens
 *   Text output:  $20/1M tokens
 *
 * Google Gemini Live (gemini-3.1-flash-live-preview):
 *   Currently FREE during preview period.
 *   Estimated GA pricing: ~$0.15/min audio input, ~$0.25/min audio output
 */

export interface CostEstimate {
  /** Provider name */
  provider: string;
  /** Estimated cost in USD for this turn */
  costUsd: number;
  /** Cumulative cost in USD for this session */
  cumulativeUsd: number;
  /** Estimated input audio duration in ms */
  audioInputMs: number;
  /** Estimated output audio duration in ms */
  audioOutputMs: number;
  /** Text input character count */
  textInputChars: number;
  /** Text output character count */
  textOutputChars: number;
  /** Pricing tier label (e.g. "Free", "$0.30/min", "$5.00/min") */
  pricingLabel: string;
}

interface PricingTier {
  /** Label shown in UI */
  label: string;
  /** Cost per ms for input audio */
  inputAudioPerMs: number;
  /** Cost per ms for output audio */
  outputAudioPerMs: number;
  /** Cost per character for input text */
  inputTextPerChar: number;
  /** Cost per character for output text */
  outputTextPerChar: number;
  /** Whether this provider is free (show "Free" instead of $0.0000) */
  isFree: boolean;
}

// ── Pricing tables ──

const PRICING: Record<string, PricingTier> = {
  "gemini-live": {
    label: "Free (preview)",
    inputAudioPerMs: 0,
    outputAudioPerMs: 0,
    inputTextPerChar: 0,
    outputTextPerChar: 0,
    isFree: true,
  },
  "openai-realtime": {
    label: "$0.30/min",
    // ~1 token per 32ms audio; $100/1M tokens = $0.0001 per 1K tokens ≈ $0.003125/sec
    inputAudioPerMs: 0.000003125,
    // $200/1M tokens ≈ $0.00625/sec
    outputAudioPerMs: 0.00000625,
    // $5/1M tokens; ~4 chars per token => $0.00000125/char
    inputTextPerChar: 0.00000125,
    // $20/1M tokens; ~4 chars per token => $0.000005/char
    outputTextPerChar: 0.000005,
    isFree: false,
  },
  "stub": {
    label: "Free (mock)",
    inputAudioPerMs: 0,
    outputAudioPerMs: 0,
    inputTextPerChar: 0,
    outputTextPerChar: 0,
    isFree: true,
  },
  "hermes": {
    label: "Free (local)",
    inputAudioPerMs: 0,
    outputAudioPerMs: 0,
    inputTextPerChar: 0,
    outputTextPerChar: 0,
    isFree: true,
  },
  "pi-agent": {
    label: "Free (local)",
    inputAudioPerMs: 0,
    outputAudioPerMs: 0,
    inputTextPerChar: 0,
    outputTextPerChar: 0,
    isFree: true,
  },
  "python-worker": {
    label: "Free (local)",
    inputAudioPerMs: 0,
    outputAudioPerMs: 0,
    inputTextPerChar: 0,
    outputTextPerChar: 0,
    isFree: true,
  },
};

// ── Default pricing for unknown providers ──

const DEFAULT_PRICING: PricingTier = {
  label: "Unknown",
  inputAudioPerMs: 0,
  outputAudioPerMs: 0,
  inputTextPerChar: 0,
  outputTextPerChar: 0,
  isFree: true,
};

/**
 * Cost Tracker — maintains session-level cumulative costs and
 * estimates per-turn cost for any provider.
 */
export class CostTracker {
  private cumulative: Map<string, number> = new Map();
  private totalCumulative: number = 0;

  /**
   * Estimate the cost of a single turn.
   *
   * @param provider Provider name
   * @param audioInputMs Estimated duration of input audio in ms
   * @param audioOutputMs Estimated duration of output audio in ms
   * @param textInputChars Number of characters in user's text input
   * @param textOutputChars Number of characters in assistant's text output
   * @returns Cost estimate for this turn + updated cumulative
   */
  estimateTurn(
    provider: string,
    audioInputMs: number = 0,
    audioOutputMs: number = 0,
    textInputChars: number = 0,
    textOutputChars: number = 0
  ): CostEstimate {
    const pricing = PRICING[provider] || DEFAULT_PRICING;

    const costFromAudioInput = audioInputMs * pricing.inputAudioPerMs;
    const costFromAudioOutput = audioOutputMs * pricing.outputAudioPerMs;
    const costFromTextInput = textInputChars * pricing.inputTextPerChar;
    const costFromTextOutput = textOutputChars * pricing.outputTextPerChar;

    const costUsd = costFromAudioInput + costFromAudioOutput + costFromTextInput + costFromTextOutput;

    // Update cumulative
    const prevCumulative = this.cumulative.get(provider) || 0;
    const newCumulative = prevCumulative + costUsd;
    this.cumulative.set(provider, newCumulative);
    this.totalCumulative += costUsd;

    return {
      provider,
      costUsd,
      cumulativeUsd: newCumulative,
      audioInputMs,
      audioOutputMs,
      textInputChars,
      textOutputChars,
      pricingLabel: pricing.isFree ? "Free" : pricing.label,
    };
  }

  /** Get cumulative cost for all providers */
  get totalCost(): number {
    return this.totalCumulative;
  }

  /** Get cumulative cost for a specific provider */
  getProviderCost(provider: string): number {
    return this.cumulative.get(provider) || 0;
  }

  /** Get all provider cumulative costs */
  getAllProviderCosts(): Map<string, number> {
    return new Map(this.cumulative);
  }

  /** Get the pricing label for a provider */
  getPricingLabel(provider: string): string {
    return (PRICING[provider] || DEFAULT_PRICING).label;
  }

  /** Reset all cumulative costs */
  reset(): void {
    this.cumulative.clear();
    this.totalCumulative = 0;
  }

  /** Get pricing info for display in provider selector */
  static getProviderPricingInfo(provider: string): { label: string; isFree: boolean } {
    const p = PRICING[provider] || DEFAULT_PRICING;
    return { label: p.label, isFree: p.isFree };
  }

  /** Return pricing info for all known providers (for UI) */
  static getAllPricingInfo(): Record<string, { label: string; isFree: boolean }> {
    const result: Record<string, { label: string; isFree: boolean }> = {};
    for (const [name, tier] of Object.entries(PRICING)) {
      result[name] = { label: tier.label, isFree: tier.isFree };
    }
    return result;
  }
}
