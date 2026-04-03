/**
 * Personalities Route for Echo-Node Gateway
 * 
 * GET /api/personalities - List available personality presets
 */

import { Context } from 'hono';
import type { PersonalitiesResponse, PersonalityInfo } from '../utils/types';
import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';
import { parse } from 'yaml';

interface PersonalitiesDeps {
  personalitiesDir: string;
  getActivePersonality: () => string;
}

/**
 * Create personalities route handler
 */
export function createPersonalitiesRoute(deps: PersonalitiesDeps) {
  return async (c: Context) => {
    try {
      const builtIn: PersonalityInfo[] = [];
      const custom: PersonalityInfo[] = [];

      // Read personality files from worker/personalities/
      const personalitiesDir = deps.personalitiesDir;
      
      try {
        const files = readdirSync(personalitiesDir)
          .filter(f => f.endsWith('.yaml') || f.endsWith('.yml'));

        for (const file of files) {
          const filePath = join(personalitiesDir, file);
          const content = readFileSync(filePath, 'utf-8');
          const personality = parse(content) as { name: string; description: string };

          const info: PersonalityInfo = {
            name: personality.name || file.replace(/\.(yaml|yml)$/, ''),
            description: personality.description || 'No description',
          };

          // Custom personalities could be in a separate directory
          // For now, all are considered built-in
          builtIn.push(info);
        }
      } catch (error) {
        console.error('[Personalities] Error reading personalities:', error);
      }

      const response: PersonalitiesResponse = {
        built_in: builtIn,
        custom: custom,
      };

      return c.json(response);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown error';
      return c.json(
        { error: { code: 'PERSONALITIES_ERROR', message } },
        500
      );
    }
  };
}
