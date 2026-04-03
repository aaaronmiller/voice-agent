/**
 * Status Route for Echo-Node Gateway
 * 
 * GET /api/status - Current pipeline status
 */

import { Context } from 'hono';
import type { StatusResponse } from '../utils/types';

interface StatusDeps {
  getState: () => string;
  getSessionActive: () => boolean;
  getPersonality: () => string;
  getConversationTurns: () => number;
  getVRAM?: () => { total_mb: number; used_mb: number; available_mb: number } | null;
}

/**
 * Create status route handler
 */
export function createStatusRoute(deps: StatusDeps) {
  return async (c: Context) => {
    const vram = deps.getVRAM?.();
    
    const response: StatusResponse = {
      state: deps.getState() as 'dormant' | 'triggered' | 'listening' | 'processing' | 'speaking',
      session_active: deps.getSessionActive(),
      current_personality: deps.getPersonality(),
      conversation_turns: deps.getConversationTurns(),
      ...(vram && { vram }),
    };

    return c.json(response);
  };
}
