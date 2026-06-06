/**
 * Health Check Route for Echo-Node Gateway
 * 
 * GET /api/health - System health status
 */

import { Context } from 'hono';
import type { HealthResponse } from '../utils/types';

interface HealthDeps {
  workerConnected: boolean;
  pipelineState: string;
  uptimeSeconds: number;
}

/**
 * Create health check route handler
 */
export function createHealthRoute(deps: HealthDeps) {
  return async (c: Context) => {
    const response: HealthResponse = {
      status: deps.workerConnected ? 'ok' : 'error',
      worker_connected: deps.workerConnected,
      pipeline_state: deps.pipelineState as 'dormant' | 'triggered' | 'listening' | 'processing' | 'speaking',
      uptime_seconds: deps.uptimeSeconds,
    };

    // Return 503 if worker is disconnected
    if (!deps.workerConnected) {
      return c.json(response, 503);
    }

    return c.json(response);
  };
}
