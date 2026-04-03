# Gateway Integrations

This directory contains integration modules for external services.

## Available Integrations

### Home Assistant (`home-assistant.ts`)
Integration with Home Assistant smart home platform for:
- Device state queries
- Automation triggers
- Entity control

### Open Home Panel (`open-home-panel.ts`)
Integration with Open Home Panel for:
- Device management
- Group controls
- Scene activation

## Usage

```typescript
import { HomeAssistantIntegration } from './integrations/home-assistant';

const ha = new HomeAssistantIntegration({
  url: 'http://homeassistant.local:8123',
  token: 'your-long-lived-access-token',
});

// Query device state
const state = await ha.getEntityState('light.living_room');
```

## Creating New Integrations

Create a new file in this directory following the `BaseIntegration` interface:

```typescript
import type { BaseIntegration, IntegrationConfig, IntegrationResult } from './base';

export interface MyIntegrationConfig extends IntegrationConfig {
  // Your config fields
}

export class MyIntegration implements BaseIntegration {
  constructor(private config: MyIntegrationConfig) {}
  
  async initialize(): Promise<void> {
    // Setup connection
  }
  
  async query(query: string): Promise<IntegrationResult> {
    // Process query
  }
  
  async dispose(): Promise<void> {
    // Cleanup
  }
}
```
