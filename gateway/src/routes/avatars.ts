/**
 * Avatars Route for Echo-Node Gateway
 * 
 * GET /api/avatars - List available VRM avatar models
 */

import { Context } from 'hono';
import type { AvatarsResponse, AvatarInfo } from '../utils/types';
import { readdirSync } from 'fs';
import { join } from 'path';

interface AvatarsDeps {
  avatarsDir: string;
}

/**
 * Create avatars route handler
 */
export function createAvatarsRoute(deps: AvatarsDeps) {
  return async (c: Context) => {
    try {
      const bundled: AvatarInfo[] = [];
      const custom: AvatarInfo[] = [];

      // Read VRM files from avatars directory
      const avatarsDir = deps.avatarsDir;
      
      try {
        const files = readdirSync(avatarsDir)
          .filter(f => f.endsWith('.vrm'));

        for (const file of files) {
          const displayName = file
            .replace(/\.vrm$/i, '')
            .replace(/-/g, ' ')
            .replace(/(\d+)/, '')
            .split(' ')
            .map(w => w.charAt(0).toUpperCase() + w.slice(1))
            .join(' ');

          const info: AvatarInfo = {
            model: file,
            display_name: displayName,
          };

          // Custom avatars could be in a subdirectory
          // For now, all are considered bundled
          bundled.push(info);
        }
      } catch (error) {
        console.error('[Avatars] Error reading avatars:', error);
      }

      const response: AvatarsResponse = {
        bundled,
        custom,
      };

      return c.json(response);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      return c.json(
        { error: { code: 'AVATARS_ERROR', message } },
        500
      );
    }
  };
}

// GET /api/avatars endpoint added
