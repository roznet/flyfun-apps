/**
 * Theme Manager - Handles dark/light mode switching
 *
 * Features:
 * - System preference detection via prefers-color-scheme
 * - Manual override stored in localStorage
 * - Three-state toggle: system/light/dark
 */

export type ThemePreference = 'system' | 'light' | 'dark';

const STORAGE_KEY = 'theme-preference';

export class ThemeManager {
  private currentPreference: ThemePreference = 'system';
  private mediaQuery: MediaQueryList;
  private listeners: Set<(isDark: boolean) => void> = new Set();

  constructor() {
    // Set up media query listener for system preference
    this.mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  }

  /**
   * Initialize theme manager - should be called once on app startup
   */
  init(): void {
    // Load saved preference from localStorage
    const saved = localStorage.getItem(STORAGE_KEY) as ThemePreference | null;
    this.currentPreference = saved && ['system', 'light', 'dark'].includes(saved)
      ? saved
      : 'system';

    // Apply initial theme
    this.applyTheme();

    // Listen for system preference changes
    this.mediaQuery.addEventListener('change', () => {
      if (this.currentPreference === 'system') {
        this.applyTheme();
      }
    });

    console.log('[ThemeManager] Initialized with preference:', this.currentPreference);
  }

  /**
   * Get the current theme preference
   */
  getPreference(): ThemePreference {
    return this.currentPreference;
  }

  /**
   * Check if dark mode is currently active
   */
  isDarkMode(): boolean {
    if (this.currentPreference === 'system') {
      return this.mediaQuery.matches;
    }
    return this.currentPreference === 'dark';
  }

  /**
   * Set theme preference
   */
  setPreference(preference: ThemePreference): void {
    this.currentPreference = preference;
    localStorage.setItem(STORAGE_KEY, preference);
    this.applyTheme();
    console.log('[ThemeManager] Preference set to:', preference, '- isDark:', this.isDarkMode());
  }

  /**
   * Toggle through themes: system -> light -> dark -> system
   */
  cycleTheme(): ThemePreference {
    const order: ThemePreference[] = ['system', 'light', 'dark'];
    const currentIndex = order.indexOf(this.currentPreference);
    const nextIndex = (currentIndex + 1) % order.length;
    this.setPreference(order[nextIndex]);
    return this.currentPreference;
  }

  /**
   * Subscribe to theme changes
   */
  subscribe(callback: (isDark: boolean) => void): () => void {
    this.listeners.add(callback);
    return () => this.listeners.delete(callback);
  }

  /**
   * Apply the current theme to the document
   */
  private applyTheme(): void {
    const isDark = this.isDarkMode();

    if (isDark) {
      document.documentElement.setAttribute('data-theme', 'dark');
    } else {
      document.documentElement.removeAttribute('data-theme');
    }

    // Notify listeners
    this.listeners.forEach(callback => callback(isDark));
  }

  /**
   * Get icon class for current theme state (for UI toggle button)
   */
  getIconClass(): string {
    switch (this.currentPreference) {
      case 'light':
        return 'fa-sun';
      case 'dark':
        return 'fa-moon';
      case 'system':
      default:
        return 'fa-circle-half-stroke';
    }
  }

  /**
   * Get tooltip text for current theme state
   */
  getTooltip(): string {
    switch (this.currentPreference) {
      case 'light':
        return 'Light mode (click for dark)';
      case 'dark':
        return 'Dark mode (click for system)';
      case 'system':
      default:
        return 'System theme (click for light)';
    }
  }
}

// Singleton instance
let instance: ThemeManager | null = null;

export function getThemeManager(): ThemeManager {
  if (!instance) {
    instance = new ThemeManager();
  }
  return instance;
}
