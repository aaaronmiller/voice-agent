/**
 * MCP Bridge
 * 
 * Relays MCP (Model Context Protocol) tool invocations from the LLM
 * to actual MCP servers and returns results.
 */

import type { PipelineState } from '../utils/types';

export interface MCPConfig {
  enabled: boolean;
  servers: MCPServerConfig[];
}

export interface MCPServerConfig {
  name: string;
  url: string;
  transport: 'stdio' | 'http';
  command?: string;
  args?: string[];
  env?: Record<string, string>;
}

export interface MCPTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface MCPToolCall {
  tool_name: string;
  arguments: Record<string, unknown>;
}

export interface MCPToolResult {
  tool_call_id: string;
  result: unknown;
  error?: string;
}

type MCPToolCallback = (tools: MCPTool[]) => void;
type MCPToolResultCallback = (results: MCPToolResult[]) => void;

interface MCPConnection {
  ws: WebSocket | null;
  stdio: StdioProcess | null;
  tools: MCPTool[];
  initialized: boolean;
}

interface StdioProcess {
  stdin: { write: (data: string) => void };
  stdout: { on: (event: string, cb: (data: string) => void) => void };
  stderr: { on: (event: string, cb: (data: string) => void) => void };
  kill: () => void;
}

export class MCPBridge {
  private config: MCPConfig;
  private connections: Map<string, MCPConnection> = new Map();
  private toolCallback: MCPToolCallback | null = null;
  private resultCallback: MCPToolResultCallback | null = null;

  constructor(config: MCPConfig) {
    this.config = config;
  }

  /**
   * Check if MCP integration is enabled
   */
  isEnabled(): boolean {
    return this.config.enabled && this.config.servers.length > 0;
  }

  /**
   * Set tool discovery callback
   */
  onToolsDiscovered(callback: MCPToolCallback): void {
    this.toolCallback = callback;
  }

  /**
   * Set tool result callback
   */
  onToolResults(callback: MCPToolResultCallback): void {
    this.resultCallback = callback;
  }

  /**
   * Connect to all MCP servers
   */
  async connect(): Promise<void> {
    if (!this.config.enabled) {
      console.log('[MCP] Integration disabled');
      return;
    }

    for (const server of this.config.servers) {
      try {
        await this.connectToServer(server);
      } catch (error) {
        console.error(`[MCP] Failed to connect to ${server.name}:`, error);
      }
    }
  }

  /**
   * Connect to a specific MCP server
   */
  private async connectToServer(server: MCPServerConfig): Promise<void> {
    const connection: MCPConnection = {
      ws: null,
      stdio: null,
      tools: [],
      initialized: false,
    };

    if (server.transport === 'http') {
      await this.connectHTTP(server, connection);
    } else {
      await this.connectStdio(server, connection);
    }

    this.connections.set(server.name, connection);
  }

  /**
   * Connect via HTTP transport
   */
  private async connectHTTP(server: MCPServerConfig, connection: MCPConnection): Promise<void> {
    return new Promise((resolve, reject) => {
      try {
        connection.ws = new WebSocket(server.url);

        connection.ws.onopen = async () => {
          console.log(`[MCP] Connected to ${server.name}`);
          await this.initializeMCP(connection.ws!, server.name);
          resolve();
        };

        connection.ws.onmessage = (event) => {
          this.handleMessage(server.name, event.data, connection);
        };

        connection.ws.onerror = (error) => {
          console.error(`[MCP] Error from ${server.name}:`, error);
          reject(error);
        };

        connection.ws.onclose = () => {
          console.log(`[MCP] Disconnected from ${server.name}`);
          connection.initialized = false;
        };
      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Connect via stdio transport
   */
  private async connectStdio(server: MCPServerConfig, connection: MCPConnection): Promise<void> {
    console.log(`[MCP] Stdio transport not yet implemented for ${server.name}`);
    throw new Error('Stdio transport not implemented');
  }

  /**
   * Initialize MCP connection
   */
  private async initializeMCP(ws: WebSocket, serverName: string): Promise<void> {
    const initializeMessage = {
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {
          tools: {},
        },
        clientInfo: {
          name: 'echo-node',
          version: '1.0.0',
        },
      },
    };

    ws.send(JSON.stringify(initializeMessage));
  }

  /**
   * Handle incoming MCP message
   */
  private handleMessage(serverName: string, data: string | ArrayBuffer, connection: MCPConnection): void {
    if (typeof data !== 'string') {
      return;
    }

    try {
      const message = JSON.parse(data);

      if (message.id === 1 && message.result) {
        connection.initialized = true;
        console.log(`[MCP] ${serverName} initialized`);
        this.discoverTools(connection.ws!, serverName);
      } else if (message.method === 'tools/list') {
        const tools = message.result?.tools || [];
        connection.tools = [...connection.tools, ...tools];
        this.toolCallback?.(this.getAllTools());
      } else if (message.method === 'tools/call') {
        const result = message.result;
        this.resultCallback?.([result]);
      }
    } catch {
      console.warn(`[MCP] Failed to parse message from ${serverName}`);
    }
  }

  /**
   * Discover tools from server
   */
  private async discoverTools(ws: WebSocket, serverName: string): Promise<void> {
    const listMessage = {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/list',
      params: {},
    };

    ws.send(JSON.stringify(listMessage));
  }

  /**
   * Get all tools from all servers
   */
  getAllTools(): MCPTool[] {
    const allTools: MCPTool[] = [];
    for (const connection of this.connections.values()) {
      allTools.push(...connection.tools);
    }
    return allTools;
  }

  /**
   * Call an MCP tool
   */
  async callTool(name: string, arguments_: Record<string, unknown>): Promise<MCPToolResult> {
    for (const [serverName, connection] of this.connections.entries()) {
      const tool = connection.tools.find(t => t.name === name);
      if (!tool || !connection.ws || connection.ws.readyState !== WebSocket.OPEN) {
        continue;
      }

      const callMessage = {
        jsonrpc: '2.0',
        id: Date.now(),
        method: 'tools/call',
        params: {
          name,
          arguments: arguments_,
        },
      };

      return new Promise((resolve) => {
        const handler = (event: MessageEvent) => {
          if (typeof event.data !== 'string') {
            return;
          }

          try {
            const message = JSON.parse(event.data);
            if (message.id === callMessage.id) {
              connection.ws!.removeEventListener('message', handler);
              resolve({
                tool_call_id: message.id.toString(),
                result: message.result?.content?.[0]?.text || message.result,
                error: message.error?.message,
              });
            }
          } catch {
            // Ignore parse errors
          }
        };

        connection.ws.addEventListener('message', handler);
        connection.ws.send(JSON.stringify(callMessage));
      });
    }

    return {
      tool_call_id: '',
      result: null,
      error: `Tool ${name} not found`,
    };
  }

  /**
   * Call multiple tools at once
   */
  async callTools(calls: MCPToolCall[]): Promise<MCPToolResult[]> {
    const results: MCPToolResult[] = [];
    for (const call of calls) {
      const result = await this.callTool(call.tool_name, call.arguments);
      results.push(result);
    }
    return results;
  }

  /**
   * Disconnect from all servers
   */
  disconnect(): void {
    for (const [serverName, connection] of this.connections.entries()) {
      if (connection.ws) {
        connection.ws.close();
      }
      if (connection.stdio) {
        connection.stdio.kill();
      }
      console.log(`[MCP] Disconnected from ${serverName}`);
    }
    this.connections.clear();
  }

  /**
   * Get connection status
   */
  getStatus(): { server: string; connected: boolean; tools: number }[] {
    const status: { server: string; connected: boolean; tools: number }[] = [];
    for (const [serverName, connection] of this.connections.entries()) {
      status.push({
        server: serverName,
        connected: connection.initialized,
        tools: connection.tools.length,
      });
    }
    return status;
  }
}

/**
 * Create MCP bridge instance
 */
export function createMCPBridge(config: MCPConfig): MCPBridge {
  return new MCPBridge(config);
}

/**
 * Get default MCP configuration
 */
export function getDefaultMCPConfig(): MCPConfig {
  return {
    enabled: false,
    servers: [],
  };
}
