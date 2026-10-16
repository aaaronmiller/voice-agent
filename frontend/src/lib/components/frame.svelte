<script lang="ts">
  import { mount } from 'svelte';

  export type ThemeName = 'minimal' | 'cyberpunk' | 'retro-terminal' | 'glassmorphism' | 'none';

  interface Props {
    theme?: ThemeName;
    children?: import('svelte').Snippet;
  }

  let { theme = 'minimal', children }: Props = $props();

  // Theme CSS custom properties
  const themes: Record<ThemeName, Record<string, string>> = {
    minimal: {
      '--frame-bg': 'rgba(255, 255, 255, 0.05)',
      '--frame-border': 'rgba(255, 255, 255, 0.1)',
      '--frame-accent': '#3b82f6',
      '--frame-glow': 'none',
      '--frame-radius': '16px',
      '--frame-shadow': '0 4px 24px rgba(0, 0, 0, 0.2)',
    },
    cyberpunk: {
      '--frame-bg': 'rgba(15, 23, 42, 0.9)',
      '--frame-border': '#06b6d4',
      '--frame-accent': '#f472b6',
      '--frame-glow': '0 0 20px rgba(6, 182, 212, 0.5)',
      '--frame-radius': '4px',
      '--frame-shadow': '0 0 40px rgba(6, 182, 212, 0.3)',
    },
    'retro-terminal': {
      '--frame-bg': 'rgba(16, 185, 129, 0.1)',
      '--frame-border': '#22c55e',
      '--frame-accent': '#4ade80',
      '--frame-glow': '0 0 10px rgba(34, 197, 94, 0.3)',
      '--frame-radius': '2px',
      '--frame-shadow': '0 0 20px rgba(34, 197, 94, 0.2)',
    },
    glassmorphism: {
      '--frame-bg': 'rgba(255, 255, 255, 0.1)',
      '--frame-border': 'rgba(255, 255, 255, 0.2)',
      '--frame-accent': '#a78bfa',
      '--frame-glow': 'none',
      '--frame-radius': '24px',
      '--frame-shadow': '0 8px 32px rgba(0, 0, 0, 0.3)',
    },
    none: {
      '--frame-bg': 'transparent',
      '--frame-border': 'transparent',
      '--frame-accent': 'transparent',
      '--frame-glow': 'none',
      '--frame-radius': '0',
      '--frame-shadow': 'none',
    },
  };

  const currentTheme = $derived(themes[theme] ?? themes.minimal);

  $effect(() => {
    // Apply theme CSS variables to document
    const root = document.documentElement;
    Object.entries(currentTheme).forEach(([prop, value]) => {
      root.style.setProperty(prop, value);
    });

    return () => {
      // Cleanup on unmount
      Object.keys(currentTheme).forEach((prop) => {
        root.style.removeProperty(prop);
      });
    };
  });
</script>

<div class="frame" style={currentTheme}>
  {#if children}
    {@render children()}
  {/if}
</div>

<style>
  .frame {
    position: relative;
    background: var(--frame-bg);
    border: 1px solid var(--frame-border);
    border-radius: var(--frame-radius);
    box-shadow: var(--frame-shadow);
    overflow: hidden;
    transition: all 0.3s ease;
  }

  .frame::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(
      90deg,
      transparent,
      var(--frame-accent),
      transparent
    );
    opacity: 0.5;
  }

  :global(body) {
    --frame-bg: rgba(255, 255, 255, 0.05);
    --frame-border: rgba(255, 255, 255, 0.1);
    --frame-accent: #3b82f6;
    --frame-glow: none;
    --frame-radius: 16px;
    --frame-shadow: 0 4px 24px rgba(0, 0, 0, 0.2);
  }
</style>

<!-- theme switching added -->
