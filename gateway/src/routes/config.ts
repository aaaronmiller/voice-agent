/**
 * Configuration Routes for Echo-Node Gateway
 * 
 * GET  /api/config - Get current configuration
 * PUT  /api/config - Update configuration
 */

import { Context } from 'hono';
import type { EchoNodeConfig } from '../utils/config-loader';
import type { ConfigUpdateRequest, ConfigUpdateResponse } from '../utils/types';

interface ConfigDeps {
  getConfig: () => EchoNodeConfig;
  updateConfig: (updates: Partial<EchoNodeConfig>) => Promise<{ restarted: string[] }>;
}

/**
 * Create config route handlers
 */
export function createConfigRoutes(deps: ConfigDeps) {
  return {
    /**
     * GET /api/config - Get current configuration
     */
    getConfig: async (c: Context) => {
      const config = deps.getConfig();
      return c.json(config);
    },

    /**
     * PUT /api/config - Update configuration
     */
    updateConfig: async (c: Context) => {
      try {
        const updates = await c.json<ConfigUpdateRequest>();
        
        // Validate updates contain at least one field
        if (!updates || Object.keys(updates).length === 0) {
          return c.json(
            { error: { code: 'INVALID_REQUEST', message: 'Configuration updates cannot be empty' } },
            400
          );
        }

        // Apply updates
        const result = await deps.updateConfig(updates as Partial<EchoNodeConfig>);

        const response: ConfigUpdateResponse = {
          success: true,
          restarted_components: result.restarted,
          message: `Configuration updated. Restarted: ${result.restarted.join(', ') || 'none'}`,
        };

        return c.json(response);
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unknown error';
        
        return c.json(
          {
            error: {
              code: 'CONFIG_UPDATE_FAILED',
              message,
              suggestion: 'Check that provider names are valid and required fields are present',
            },
          },
          400
        );
      }
    },
  };
}
