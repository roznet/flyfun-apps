/**
 * UI Manager - Reactive DOM updates based on Zustand store
 * Handles all user interactions and updates UI based on state changes
 */

import { useStore } from '../store/store';
import type { AppState, FilterConfig, LegendMode, Airport } from '../store/types';
import { APIAdapter } from '../adapters/api-adapter';

/**
 * UI Manager class
 */
export class UIManager {
  private store: typeof useStore;
  private apiAdapter: APIAdapter;
  private unsubscribe: (() => void) | null = null;
  private debounceTimeouts: Map<string, number> = new Map();

  constructor(store: typeof useStore, apiAdapter: APIAdapter) {
    this.store = store;
    this.apiAdapter = apiAdapter;
  }

  /**
   * Initialize UI Manager
   */
  init(): void {
    // Initialize event listeners first
    this.initEventListeners();
    this.initTabs();
    this.initDrawer();

    // Subscribe to store changes - Zustand's subscribe works outside React
    // Use a debounce and state comparison to prevent infinite loops
    let lastStateHash: string = '';
    let updateTimeout: number | null = null;
    this.unsubscribe = this.store.subscribe((state) => {
      // Create a hash of state to detect actual changes
      const stateHash = JSON.stringify({
        filters: state.filters,
        searchQuery: state.ui.searchQuery,
        legendMode: state.visualization.legendMode,
        selectedAirport: state.selectedAirport?.ident,
        loading: state.ui.loading,
        error: state.ui.error,
        filteredCount: state.filteredAirports.length
      });

      // Only update if state actually changed
      if (stateHash === lastStateHash) {
        return; // No change, skip update
      }
      lastStateHash = stateHash;

      // Debounce UI updates to prevent too many DOM updates
      if (updateTimeout) {
        clearTimeout(updateTimeout);
      }
      updateTimeout = window.setTimeout(() => {
        this.updateUI(state);
      }, 10); // Small delay to batch updates
    });

    // Initial UI update
    const initialState = this.store.getState();
    this.updateUI(initialState);

    // Load filter metadata (countries, AIP fields, presets)
    this.loadFilterMetadata();
  }

  /**
   * Load filter metadata (countries, AIP fields, presets)
   */
  private async loadFilterMetadata(): Promise<void> {
    try {
      // Load countries for dropdown
      await this.loadCountries();

      // Load AIP fields and presets
      await this.loadAIPFilters();
    } catch (error: any) {
      console.error('Error loading filter metadata:', error);
    }
  }

  /**
   * Load countries for dropdown
   */
  private async loadCountries(): Promise<void> {
    try {
      const filtersData = await this.apiAdapter.getAllFilters();
      const countries = filtersData?.countries || [];

      const countrySelect = document.getElementById('country-filter') as HTMLSelectElement;
      if (countrySelect) {
        // Clear existing options except "All Countries"
        countrySelect.innerHTML = '<option value="">All Countries</option>';

        // Add countries - API returns objects with {code, name, count}
        countries.forEach((country: any) => {
          const option = document.createElement('option');
          // Use country code for the value and name for display
          option.value = country.code || country;
          option.textContent = country.name || country.code || country;
          countrySelect.appendChild(option);
        });

        // Update selected value if set in store
        const currentCountry = this.store.getState().filters.country;
        if (currentCountry) {
          countrySelect.value = currentCountry;
        }
      }
    } catch (error: any) {
      console.error('Error loading countries:', error);
    }
  }

  /**
   * Update persona selector visibility based on legend mode.
   * Note: Persona selector is now in the global header and always visible.
   */
  private updatePersonaSelectorVisibility(_legendMode: LegendMode): void {
    // Persona selector is now in global header - always visible
    // No visibility toggle needed
  }

  /**
   * Populate persona selector with personas from GA config.
   */
  populatePersonaSelector(): void {
    const selector = document.getElementById('persona-selector') as HTMLSelectElement;
    if (!selector) return;

    const state = this.store.getState();
    const config = state.ga?.config;

    if (!config || !config.personas) {
      selector.innerHTML = '<option value="ifr_touring_sr22">IFR Touring (SR22)</option>';
      return;
    }

    selector.innerHTML = '';
    config.personas.forEach(persona => {
      const option = document.createElement('option');
      option.value = persona.id;
      option.textContent = persona.label;
      selector.appendChild(option);
    });

    // Select the current persona
    const currentPersona = state.ga?.selectedPersona || config.default_persona;
    if (currentPersona) {
      selector.value = currentPersona;
    }
  }

  /**
   * Trigger loading of GA scores for visible airports.
   */
  private triggerGAScoresLoad(): void {
    const state = this.store.getState();
    const icaos = state.filteredAirports.map(a => a.ident);

    if (icaos.length > 0 && (window as any).personaManager) {
      (window as any).personaManager.loadScores(icaos);
    }
  }

  /**
   * Load AIP filters (fields and presets)
   */
  private async loadAIPFilters(): Promise<void> {
    try {
      const [fields, presets] = await Promise.all([
        this.apiAdapter.getAvailableAIPFields(),
        this.apiAdapter.getAIPFilterPresets()
      ]);

      // Populate AIP field select
      const aipFieldSelect = document.getElementById('aip-field-select') as HTMLSelectElement;
      if (aipFieldSelect) {
        aipFieldSelect.innerHTML = '<option value="">Select AIP Field...</option>';

        fields.forEach((field: any) => {
          const option = document.createElement('option');
          option.value = field.field || field.std_field || field.name || '';
          option.textContent = field.name || field.field || field.std_field || '';
          option.dataset.fieldId = field.std_field_id || '';
          aipFieldSelect.appendChild(option);
        });
      }

      // Populate AIP preset buttons
      const presetContainer = document.getElementById('aip-preset-buttons');
      if (presetContainer && Array.isArray(presets)) {
        presetContainer.innerHTML = '';

        presets.forEach((preset: any) => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'aip-preset-btn';
          button.dataset.field = preset.field || preset.std_field || '';
          button.dataset.operator = preset.operator || 'contains';
          button.dataset.value = preset.value || '';
          button.textContent = preset.name || `${preset.field}: ${preset.value}`;
          button.addEventListener('click', () => {
            this.applyAIPPreset(preset);
          });
          presetContainer.appendChild(button);
        });
      }

      // Wire up AIP filter controls
      this.wireUpAIPFilters();
    } catch (error: any) {
      console.error('Error loading AIP filters:', error);
    }
  }

  /**
   * Wire up AIP filter controls
   */
  private wireUpAIPFilters(): void {
    // AIP field select
    const aipFieldSelect = document.getElementById('aip-field-select');
    if (aipFieldSelect) {
      aipFieldSelect.addEventListener('change', () => {
        this.handleAIPFieldChange();
      });
    }

    // AIP operator select
    const aipOperatorSelect = document.getElementById('aip-operator-select');
    if (aipOperatorSelect) {
      aipOperatorSelect.addEventListener('change', () => {
        this.handleAIPFieldChange();
      });
    }

    // AIP value input
    const aipValueInput = document.getElementById('aip-value-input');
    if (aipValueInput) {
      aipValueInput.addEventListener('input', () => {
        this.handleAIPFieldChange();
      });
    }

    // Persona selector listener - reload GA relevance data when persona changes
    const personaSelector = document.getElementById('persona-selector');
    if (personaSelector) {
      personaSelector.addEventListener('change', () => {
        // Check if relevance tab is currently active and an airport is selected
        const relevancePanel = document.getElementById('relevance-panel');
        // Check for 'active' class instead of 'show' (Bootstrap)
        if (relevancePanel && !relevancePanel.classList.contains('hidden') && this.store.getState().selectedAirport) {
          this.triggerGAScoresLoad();
        }
      });
    }
    // Clear AIP filter button
    const clearAIPFilterBtn = document.getElementById('clear-aip-filter');
    if (clearAIPFilterBtn) {
      clearAIPFilterBtn.addEventListener('click', () => {
        this.clearAIPFilter();
      });
    }

    // Remove AIP filter button
    const removeAIPFilterBtn = document.getElementById('remove-aip-filter');
    if (removeAIPFilterBtn) {
      removeAIPFilterBtn.addEventListener('click', () => {
        this.clearAIPFilter();
      });
    }
  }

  /**
   * Handle AIP field change
   */
  private handleAIPFieldChange(): void {
    const aipFieldSelect = document.getElementById('aip-field-select') as HTMLSelectElement;
    const aipOperatorSelect = document.getElementById('aip-operator-select') as HTMLSelectElement;
    const aipValueInput = document.getElementById('aip-value-input') as HTMLInputElement;

    if (!aipFieldSelect || !aipOperatorSelect || !aipValueInput) return;

    const field = aipFieldSelect.value;
    const operator = aipOperatorSelect.value;
    const value = aipValueInput.value.trim();

    if (!field) {
      this.clearAIPFilter();
      return;
    }

    // Update store
    const updates: Partial<FilterConfig> = {
      aip_field: field,
      aip_operator: operator as any
    };

    // Handle "not_empty" operator (no value needed)
    if (operator === 'not_empty') {
      updates.aip_value = null;
    } else {
      updates.aip_value = value || null;
    }

    this.store.getState().setFilters(updates);

    // Update active filter display
    this.updateActiveAIPFilter(field, operator, value);
  }

  /**
   * Apply AIP preset
   */
  private applyAIPPreset(preset: any): void {
    const aipFieldSelect = document.getElementById('aip-field-select') as HTMLSelectElement;
    const aipOperatorSelect = document.getElementById('aip-operator-select') as HTMLSelectElement;
    const aipValueInput = document.getElementById('aip-value-input') as HTMLInputElement;

    if (aipFieldSelect) aipFieldSelect.value = preset.field || preset.std_field || '';
    if (aipOperatorSelect) aipOperatorSelect.value = preset.operator || 'contains';
    if (aipValueInput) aipValueInput.value = preset.value || '';

    this.handleAIPFieldChange();

    // Highlight active preset button
    const presetButtons = document.querySelectorAll('.aip-preset-btn');
    presetButtons.forEach(btn => {
      if ((btn as HTMLElement).dataset.field === preset.field) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }

  /**
   * Clear AIP filter
   */
  private clearAIPFilter(): void {
    const aipFieldSelect = document.getElementById('aip-field-select') as HTMLSelectElement;
    const aipOperatorSelect = document.getElementById('aip-operator-select') as HTMLSelectElement;
    const aipValueInput = document.getElementById('aip-value-input') as HTMLInputElement;

    if (aipFieldSelect) aipFieldSelect.value = '';
    if (aipOperatorSelect) aipOperatorSelect.value = 'contains';
    if (aipValueInput) aipValueInput.value = '';

    // Clear from store
    this.store.getState().setFilters({
      aip_field: null,
      aip_value: null,
      aip_operator: 'contains'
    });

    // Hide active filter display
    const activeFilterDiv = document.getElementById('active-aip-filter');
    if (activeFilterDiv) {
      activeFilterDiv.style.display = 'none';
    }

    // Remove active state from preset buttons
    const presetButtons = document.querySelectorAll('.aip-preset-btn');
    presetButtons.forEach(btn => btn.classList.remove('active'));
  }

  /**
   * Update active AIP filter display
   */
  private updateActiveAIPFilter(field: string, operator: string, value: string): void {
    const activeFilterDiv = document.getElementById('active-aip-filter');
    const activeFilterText = document.getElementById('active-aip-filter-text');

    if (!activeFilterDiv || !activeFilterText) return;

    if (operator === 'not_empty') {
      activeFilterText.textContent = `${field} is not empty`;
    } else if (value) {
      activeFilterText.textContent = `${field} ${operator} "${value}"`;
    } else {
      activeFilterDiv.style.display = 'none';
      return;
    }

    activeFilterDiv.style.display = 'block';
  }

  /**
   * Cleanup
   */
  destroy(): void {
    if (this.unsubscribe) {
      this.unsubscribe();
    }
    // Clear debounce timeouts
    this.debounceTimeouts.forEach(timeout => clearTimeout(timeout));
    this.debounceTimeouts.clear();
  }

  /**
   * Update UI based on state
   */
  private updateUI(state: AppState): void {
    // Update filter controls
    this.updateFilterControls(state.filters);

    // Update search input
    this.updateSearchInput(state.ui.searchQuery);

    // Update legend mode
    this.updateLegendMode(state.visualization.legendMode);

    // Update loading state
    this.updateLoadingState(state.ui.loading);

    // Update error state
    this.updateErrorState(state.ui.error);

    // Update airport count
    this.updateAirportCount(state.filteredAirports.length);

    // Update airport details panel
    if (state.selectedAirport) {
      // We don't call updateAirportDetails here because it's handled by the 'airport-click' event
      // or 'display-airport-details' event which calls displayAirportDetails in main.ts
      // But we might want to ensure the panel is visible if it was hidden
      const rightPanel = document.getElementById('right-panel');
      if (rightPanel) rightPanel.classList.remove('hidden');
    } else {
      const rightPanel = document.getElementById('right-panel');
      if (rightPanel) rightPanel.classList.add('hidden');
    }

    // Update reset zoom button
    this.updateResetZoomButton(state.filteredAirports.length > 0);
  }

  /**
   * Initialize custom tabs (Segmented Control)
   */
  private initTabs(): void {
    const tabButtons = document.querySelectorAll('.segment-btn');

    tabButtons.forEach(btn => {
      btn.addEventListener('click', (e) => {
        const targetBtn = e.currentTarget as HTMLElement;
        const targetSelector = targetBtn.dataset.target;

        if (!targetSelector) return;

        // Update buttons state
        tabButtons.forEach(b => b.classList.remove('active'));
        targetBtn.classList.add('active');

        // Update panels state
        const allPanels = document.querySelectorAll('.tab-pane');
        allPanels.forEach(p => p.classList.add('hidden'));

        const targetPanel = document.querySelector(targetSelector);
        if (targetPanel) {
          targetPanel.classList.remove('hidden');
          targetPanel.classList.add('active');
        }

        // Trigger specific logic based on tab
        if (targetSelector === '#relevance-panel' && this.store.getState().selectedAirport) {
          this.triggerGAScoresLoad();
        }
      });
    });
  }

  /**
   * Initialize Filter Drawer
   */
  private initDrawer(): void {
    const drawer = document.getElementById('filter-drawer');
    const toggleBtn = document.getElementById('filter-toggle-btn');
    const closeBtn = document.getElementById('filter-close-btn');
    const applyBtn = document.getElementById('apply-filters');

    if (!drawer) return;

    const toggleDrawer = () => {
      drawer.classList.toggle('open');
    };

    if (toggleBtn) toggleBtn.addEventListener('click', toggleDrawer);
    if (closeBtn) closeBtn.addEventListener('click', toggleDrawer);

    // Close drawer when applying filters on mobile/drawer view
    if (applyBtn) {
      applyBtn.addEventListener('click', () => {
        drawer.classList.remove('open');
        this.applyFilters();
      });
    }
  }

  /**
   * Initialize event listeners
   */
  private initEventListeners(): void {
    // Filter controls
    // Helper to handle filter changes - if route/locate active, re-run search
    const handleFilterChange = (filterUpdate: Partial<FilterConfig>) => {
      // Update filters first
      this.store.getState().setFilters(filterUpdate);

      // Check current state after filter update
      const state = this.store.getState();

      // If we have an active route or locate, re-run the search with new filters
      if (state.route && state.route.airports && !state.route.isChatbotSelection) {
        // Active route search - re-run with new filters
        this.applyFilters();
      } else if (state.locate && state.locate.center) {
        // Active locate search - re-run with new filters
        this.applyFilters();
      }
      // Otherwise, just client-side filtering is fine (normal mode)
    };

    const countrySelect = document.getElementById('country-filter');
    if (countrySelect) {
      countrySelect.addEventListener('change', (e) => {
        const target = e.target as HTMLSelectElement;
        handleFilterChange({ country: target.value || null });
      });
    }

    const hasProcedures = document.getElementById('has-procedures');
    if (hasProcedures) {
      hasProcedures.addEventListener('change', (e) => {
        const target = e.target as HTMLInputElement;
        handleFilterChange({ has_procedures: target.checked || null });
      });
    }

    const hasAipData = document.getElementById('has-aip-data');
    if (hasAipData) {
      hasAipData.addEventListener('change', (e) => {
        const target = e.target as HTMLInputElement;
        handleFilterChange({ has_aip_data: target.checked || null });
      });
    }

    const hasHardRunway = document.getElementById('has-hard-runway');
    if (hasHardRunway) {
      hasHardRunway.addEventListener('change', (e) => {
        const target = e.target as HTMLInputElement;
        handleFilterChange({ has_hard_runway: target.checked || null });
      });
    }

    const borderCrossing = document.getElementById('border-crossing-only');
    if (borderCrossing) {
      borderCrossing.addEventListener('change', (e) => {
        const target = e.target as HTMLInputElement;
        handleFilterChange({ point_of_entry: target.checked || null });
      });
    }

    const maxAirports = document.getElementById('max-airports-filter');
    if (maxAirports) {
      maxAirports.addEventListener('change', (e) => {
        const target = e.target as HTMLSelectElement;
        const limit = target.value ? parseInt(target.value, 10) : null;
        handleFilterChange({ limit: limit || 1000 });
      });
    }

    // Search input
    const searchInput = document.getElementById('search-input');
    if (searchInput) {
      // Debounce search input
      searchInput.addEventListener('input', (e) => {
        const target = e.target as HTMLInputElement;
        this.store.getState().setSearchQuery(target.value);

        // Clear existing timeout
        const existingTimeout = this.debounceTimeouts.get('search');
        if (existingTimeout) {
          clearTimeout(existingTimeout);
        }

        // Debounce search execution
        const timeout = setTimeout(() => {
          this.handleSearch(target.value.trim());
        }, 500);

        this.debounceTimeouts.set('search', timeout);
      });
    }

    // Legend mode
    const legendModeSelect = document.getElementById('legend-mode-filter');
    if (legendModeSelect) {
      legendModeSelect.addEventListener('change', (e) => {
        const target = e.target as HTMLSelectElement;
        this.store.getState().setLegendMode(target.value as LegendMode);

        // Show/hide persona selector based on legend mode
        this.updatePersonaSelectorVisibility(target.value as LegendMode);

        // If switching to relevance mode, load GA scores for visible airports
        if (target.value === 'relevance') {
          this.triggerGAScoresLoad();
        }
      });
    }

    // Persona selector
    const personaSelector = document.getElementById('persona-selector');
    if (personaSelector) {
      personaSelector.addEventListener('change', (e) => {
        const target = e.target as HTMLSelectElement;
        // Use window.personaManager directly since it's exposed globally
        if ((window as any).personaManager) {
          (window as any).personaManager.selectPersona(target.value);
          // Reload GA scores for visible airports
          this.triggerGAScoresLoad();
        }
      });
    }

    // Apply filters button
    const applyFiltersBtn = document.getElementById('apply-filters');
    if (applyFiltersBtn) {
      applyFiltersBtn.addEventListener('click', () => {
        this.applyFilters();
      });
    }

    // Clear filters button
    const clearFiltersBtn = document.getElementById('clear-filters');
    if (clearFiltersBtn) {
      clearFiltersBtn.addEventListener('click', () => {
        this.clearFilters();
      });
    }

    // Locate button
    const locateBtn = document.getElementById('locate-button');
    if (locateBtn) {
      locateBtn.addEventListener('click', () => {
        this.handleLocate();
      });
    }

    // Reset zoom button
    const resetZoomBtn = document.getElementById('reset-zoom');
    if (resetZoomBtn) {
      resetZoomBtn.addEventListener('click', () => {
        this.handleResetZoom();
      });
    }

    // Airport click event (from map)
    window.addEventListener('airport-click', ((e: Event) => {
      const customEvent = e as CustomEvent<Airport>;
      this.store.getState().selectAirport(customEvent.detail);
      this.loadAirportDetails(customEvent.detail);
    }) as EventListener);
  }

  /**
   * Update filter controls to match state
   */
  private updateFilterControls(filters: FilterConfig): void {
    const countrySelect = document.getElementById('country-filter') as HTMLSelectElement;
    if (countrySelect) {
      countrySelect.value = filters.country || '';
    }

    const hasProcedures = document.getElementById('has-procedures') as HTMLInputElement;
    if (hasProcedures) {
      hasProcedures.checked = filters.has_procedures === true;
    }

    const hasAipData = document.getElementById('has-aip-data') as HTMLInputElement;
    if (hasAipData) {
      hasAipData.checked = filters.has_aip_data === true;
    }

    const hasHardRunway = document.getElementById('has-hard-runway') as HTMLInputElement;
    if (hasHardRunway) {
      hasHardRunway.checked = filters.has_hard_runway === true;
    }

    const borderCrossing = document.getElementById('border-crossing-only') as HTMLInputElement;
    if (borderCrossing) {
      borderCrossing.checked = filters.point_of_entry === true;
    }

    const maxAirports = document.getElementById('max-airports-filter') as HTMLSelectElement;
    if (maxAirports) {
      maxAirports.value = filters.limit ? String(filters.limit) : '';
    }

    // Update AIP filters
    if (filters.aip_field) {
      const aipFieldSelect = document.getElementById('aip-field-select') as HTMLSelectElement;
      const aipOperatorSelect = document.getElementById('aip-operator-select') as HTMLSelectElement;
      const aipValueInput = document.getElementById('aip-value-input') as HTMLInputElement;

      if (aipFieldSelect) aipFieldSelect.value = filters.aip_field;
      if (aipOperatorSelect && filters.aip_operator) {
        aipOperatorSelect.value = filters.aip_operator;
      }
      if (aipValueInput && filters.aip_value) {
        aipValueInput.value = filters.aip_value;
      }

      this.updateActiveAIPFilter(
        filters.aip_field,
        filters.aip_operator || 'contains',
        filters.aip_value || ''
      );
    } else {
      // Clear AIP filter display if no filter
      const activeFilterDiv = document.getElementById('active-aip-filter');
      if (activeFilterDiv) {
        activeFilterDiv.style.display = 'none';
      }
    }
  }

  /**
   * Update search input
   */
  private updateSearchInput(query: string): void {
    const searchInput = document.getElementById('search-input') as HTMLInputElement;
    if (searchInput && searchInput.value !== query) {
      searchInput.value = query;
    }
  }

  /**
   * Update legend mode
   */
  private updateLegendMode(legendMode: LegendMode): void {
    const legendModeSelect = document.getElementById('legend-mode-filter') as HTMLSelectElement;
    if (legendModeSelect && legendModeSelect.value !== legendMode) {
      legendModeSelect.value = legendMode;
    }

    // Update legend display
    this.updateLegendDisplay(legendMode);
  }

  /**
   * Update legend display
   */
  private updateLegendDisplay(legendMode: LegendMode): void {
    const legendContent = document.getElementById('legend-content');
    if (!legendContent) return;

    let html = '';

    switch (legendMode) {
      case 'airport-type':
        html = `
          <div class="legend-item">
            <div class="legend-color" style="background-color: #28a745;"></div>
            <span>Border Crossing</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #ffc107;"></div>
            <span>Airport with Procedures</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #dc3545;"></div>
            <span>Airport without Procedures</span>
          </div>
        `;
        break;

      case 'procedure-precision':
        html = `
          <div class="legend-item">
            <div class="legend-line" style="background-color: #ffff00;"></div>
            <span>ILS (Precision)</span>
          </div>
          <div class="legend-item">
            <div class="legend-line" style="background-color: #0000ff;"></div>
            <span>RNP/RNAV (RNP)</span>
          </div>
          <div class="legend-item">
            <div class="legend-line" style="background-color: #ffffff;"></div>
            <span>VOR/NDB (Non-Precision)</span>
          </div>
        `;
        break;

      case 'runway-length':
        html = `
          <div class="legend-item">
            <div class="legend-color" style="background-color: #28a745;"></div>
            <span>Long Runway (>8000ft)</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #ffc107;"></div>
            <span>Medium Runway (4000-8000ft)</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #dc3545;"></div>
            <span>Short Runway (<4000ft)</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #6c757d;"></div>
            <span>Unknown Length</span>
          </div>
        `;
        break;

      case 'country':
        html = `
          <div class="legend-item">
            <div class="legend-color" style="background-color: #007bff;"></div>
            <span>France (LF)</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #dc3545;"></div>
            <span>United Kingdom (EG)</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #28a745;"></div>
            <span>Germany (ED)</span>
          </div>
          <div class="legend-item">
            <div class="legend-color" style="background-color: #ffc107;"></div>
            <span>Other Countries</span>
          </div>
        `;
        break;

      case 'relevance': {
        // Get bucket colors from GA config or use defaults
        const state = this.store.getState();
        const buckets = state.ga?.config?.relevance_buckets || [
          { id: 'top-quartile', label: 'Most Relevant', color: '#27ae60' },
          { id: 'second-quartile', label: 'Relevant', color: '#3498db' },
          { id: 'third-quartile', label: 'Less Relevant', color: '#f39c12' },
          { id: 'bottom-quartile', label: 'Least Relevant', color: '#e74c3c' },
          { id: 'unknown', label: 'No Data', color: '#95a5a6' }
        ];

        html = buckets.map(bucket => `
          <div class="legend-item">
            <div class="legend-color" style="background-color: ${bucket.color};"></div>
            <span>${bucket.label}</span>
          </div>
        `).join('');
        break;
      }
    }

    legendContent.innerHTML = html;
  }

  /**
   * Update loading state
   */
  private updateLoadingState(loading: boolean): void {
    const loadingEl = document.getElementById('loading');
    if (loadingEl) {
      if (loading) {
        loadingEl.classList.remove('hidden');
      } else {
        loadingEl.classList.add('hidden');
      }
    }

    const applyBtn = document.getElementById('apply-filters');
    if (applyBtn) {
      (applyBtn as HTMLButtonElement).disabled = loading;
      applyBtn.innerHTML = loading
        ? '<i class="fas fa-spinner fa-spin"></i> Loading...'
        : 'Apply Filters';
    }
  }

  /**
   * Update error state
   */
  private updateErrorState(error: string | null): void {
    // Remove existing error alerts
    const existingAlerts = document.querySelectorAll('.alert-danger.position-fixed');
    existingAlerts.forEach(alert => alert.remove());

    if (error) {
      const alertDiv = document.createElement('div');
      alertDiv.className = 'alert alert-danger alert-dismissible fade show position-fixed';
      alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
      alertDiv.innerHTML = `
        <i class="fas fa-exclamation-triangle"></i> ${error}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      `;

      document.body.appendChild(alertDiv);

      // Auto-remove after 5 seconds
      setTimeout(() => {
        if (alertDiv.parentNode) {
          alertDiv.remove();
        }
      }, 5000);
    }
  }

  /**
   * Update airport count
   */
  private updateAirportCount(count: number): void {
    // Update any elements that display airport count
    const countElements = document.querySelectorAll('[data-airport-count]');
    countElements.forEach(el => {
      el.textContent = String(count);
    });
  }

  /**
   * Update airport details panel
   */
  private updateAirportDetails(airport: Airport): void {
    // This will be implemented to show airport details in right panel
    // For now, just ensure panel is visible
    const airportContent = document.getElementById('airport-content');
    if (airportContent) {
      airportContent.style.display = 'flex';
    }

    const noSelection = document.getElementById('no-selection');
    if (noSelection) {
      noSelection.style.display = 'none';
    }
  }

  /**
   * Hide airport details panel
   */
  private hideAirportDetails(): void {
    const airportContent = document.getElementById('airport-content');
    if (airportContent) {
      airportContent.style.display = 'none';
    }

    const noSelection = document.getElementById('no-selection');
    if (noSelection) {
      noSelection.style.display = 'block';
    }
  }

  /**
   * Update reset zoom button state
   */
  private updateResetZoomButton(enabled: boolean): void {
    const resetBtn = document.getElementById('reset-zoom');
    if (resetBtn) {
      (resetBtn as HTMLButtonElement).disabled = !enabled;
    }
  }

  /**
   * Apply filters (trigger API call)
   */
  async applyFilters(): Promise<void> {
    const state = this.store.getState();

    this.store.getState().setLoading(true);
    this.store.getState().setError(null);

    try {
      // Check if we have route state
      if (state.route && state.route.isChatbotSelection && state.route.chatbotAirports) {
        // Client-side filtering for chatbot airports
        // Filters are already applied via store.setFilters()
        this.store.getState().setLoading(false);
        return;
      }

      if (state.route && state.route.airports) {
        // Route search mode
        await this.applyRouteSearch(state.route);
        return;
      }

      if (state.locate && state.locate.center) {
        // Locate mode with cached center
        await this.applyLocateWithCenter(state.locate);
        return;
      }

      // Normal filter mode
      const response = await this.apiAdapter.getAirports(state.filters);
      this.store.getState().setAirports(response.data);

      this.showSuccess(`Applied filters: ${response.data.length} airports found`);
      this.store.getState().setLoading(false);
    } catch (error: any) {
      console.error('Error applying filters:', error);
      this.store.getState().setError('Error applying filters: ' + (error.message || 'Unknown error'));
      this.store.getState().setLoading(false);
    }
  }

  /**
   * Apply route search
   */
  private async applyRouteSearch(route: NonNullable<ReturnType<typeof useStore.getState>['route']>): Promise<void> {
    if (!route.airports || route.airports.length < 1) return;

    const state = this.store.getState();
    const distanceInput = document.getElementById('route-distance') as HTMLInputElement;
    const distanceNm = distanceInput ? parseFloat(distanceInput.value) || 50.0 : 50.0;

    const enrouteInput = document.getElementById('enroute-distance') as HTMLInputElement;
    const enrouteMaxNm = enrouteInput ? parseFloat(enrouteInput.value) || undefined : undefined;

    try {
      const filters: Partial<FilterConfig> = { ...state.filters };
      if (enrouteMaxNm) {
        filters.enroute_distance_max_nm = enrouteMaxNm;
      }

      const response = await this.apiAdapter.searchAirportsNearRoute(
        route.airports,
        distanceNm,
        filters
      );

      // Extract airports from response
      const airports = response.airports.map(item => ({
        ...item.airport,
        _routeSegmentDistance: item.segment_distance_nm,
        _routeEnrouteDistance: item.enroute_distance_nm,
        _closestSegment: item.closest_segment
      }));

      this.store.getState().setAirports(airports);

      // Update route state
      this.store.getState().setRoute({
        ...route,
        distance_nm: distanceNm
      });

      this.showSuccess(`Route search: ${response.airports_found} airports within ${distanceNm}nm`);
      this.store.getState().setLoading(false);
    } catch (error: any) {
      console.error('Error in route search:', error);
      this.store.getState().setError('Error searching route: ' + (error.message || 'Unknown error'));
      this.store.getState().setLoading(false);
    }
  }

  /**
   * Apply locate with cached center
   */
  private async applyLocateWithCenter(locate: NonNullable<ReturnType<typeof useStore.getState>['locate']>): Promise<void> {
    if (!locate.center) return;

    const state = this.store.getState();
    const radiusInput = document.getElementById('route-distance') as HTMLInputElement;
    const radiusNm = radiusInput ? parseFloat(radiusInput.value) || locate.radiusNm : locate.radiusNm;

    try {
      const response = await this.apiAdapter.locateAirportsByCenter(
        { lat: locate.center.lat, lon: locate.center.lng, label: locate.center.label } as { lat: number; lon: number; label?: string },
        radiusNm,
        state.filters
      );

      if (response.airports) {
        this.store.getState().setAirports(response.airports);

        // Update locate state
        this.store.getState().setLocate({
          ...locate,
          radiusNm
        });

        this.showSuccess(response.pretty || `Found ${response.count} airports within ${radiusNm}nm`);
        this.store.getState().setLoading(false);
      }
    } catch (error: any) {
      console.error('Error in locate:', error);
      this.store.getState().setError('Error locating airports: ' + (error.message || 'Unknown error'));
      this.store.getState().setLoading(false);
    }
  }

  /**
   * Handle search input
   */
  private async handleSearch(query: string): Promise<void> {
    if (!query.trim()) {
      // Clear search
      this.store.getState().setAirports([]);
      return;
    }

    // Check if this is a route search (4-letter ICAO codes)
    const routeAirports = this.parseRouteFromQuery(query);

    if (routeAirports && routeAirports.length > 0) {
      // Route search
      await this.handleRouteSearch(routeAirports);
    } else {
      // Text search
      this.store.getState().setLoading(true);
      this.store.getState().setError(null);

      try {
        const response = await this.apiAdapter.searchAirports(query, 50);
        this.store.getState().setAirports(response.data);
        this.showSuccess(`Search results: ${response.data.length} airports found for "${query}"`);
        this.store.getState().setLoading(false);
      } catch (error: any) {
        console.error('Error in search:', error);
        this.store.getState().setError('Error searching airports: ' + (error.message || 'Unknown error'));
        this.store.getState().setLoading(false);
      }
    }
  }

  /**
   * Parse route from query string
   */
  private parseRouteFromQuery(query: string): string[] | null {
    const parts = query.trim().split(/\s+/).filter(part => part.length > 0);
    const icaoPattern = /^[A-Za-z]{4}$/;

    const allIcaoCodes = parts.every(part => icaoPattern.test(part));

    if (allIcaoCodes && parts.length >= 1) {
      return parts.map(part => part.toUpperCase());
    }

    return null;
  }

  /**
   * Handle route search
   */
  private async handleRouteSearch(routeAirports: string[]): Promise<void> {
    const distanceInput = document.getElementById('route-distance') as HTMLInputElement;
    const distanceNm = distanceInput ? parseFloat(distanceInput.value) || 50.0 : 50.0;

    this.store.getState().setLoading(true);
    this.store.getState().setError(null);

    try {
      const state = this.store.getState();

      // Get original route airport coordinates for route line
      const originalRouteAirports = await this.getRouteAirportCoordinates(routeAirports);

      const response = await this.apiAdapter.searchAirportsNearRoute(
        routeAirports,
        distanceNm,
        state.filters
      );

      // Extract airports
      const airports = response.airports.map(item => ({
        ...item.airport,
        _routeSegmentDistance: item.segment_distance_nm,
        _routeEnrouteDistance: item.enroute_distance_nm,
        _closestSegment: item.closest_segment
      }));

      this.store.getState().setAirports(airports);

      // Set route state
      this.store.getState().setRoute({
        airports: routeAirports,
        distance_nm: distanceNm,
        originalRouteAirports,
        isChatbotSelection: false,
        chatbotAirports: null
      });

      this.showSuccess(`Route search: ${response.airports_found} airports within ${distanceNm}nm of route ${routeAirports.join(' → ')}`);
      this.store.getState().setLoading(false);
    } catch (error: any) {
      console.error('Error in route search:', error);
      this.store.getState().setError('Error searching route: ' + (error.message || 'Unknown error'));
      this.store.getState().setLoading(false);
    }
  }

  /**
   * Get route airport coordinates
   */
  private async getRouteAirportCoordinates(routeAirports: string[]): Promise<Array<{ icao: string; lat: number; lng: number }>> {
    const coordinates: Array<{ icao: string; lat: number; lng: number }> = [];

    for (const icao of routeAirports) {
      try {
        const airport = await this.apiAdapter.getAirportDetail(icao);
        if (airport.latitude_deg && airport.longitude_deg) {
          coordinates.push({
            icao,
            lat: airport.latitude_deg,
            lng: airport.longitude_deg
          });
        }
      } catch (error) {
        console.error(`Error getting coordinates for ${icao}:`, error);
      }
    }

    return coordinates;
  }

  /**
   * Handle locate
   */
  private async handleLocate(): Promise<void> {
    const searchInput = document.getElementById('search-input') as HTMLInputElement;
    const radiusInput = document.getElementById('route-distance') as HTMLInputElement;

    const query = searchInput ? searchInput.value.trim() : '';
    const radiusNm = radiusInput ? parseFloat(radiusInput.value) || 50.0 : 50.0;

    if (!query) {
      this.store.getState().setError('Enter a place in the search box to locate near.');
      return;
    }

    this.store.getState().setLoading(true);
    this.store.getState().setError(null);

    try {
      const state = this.store.getState();
      const response = await this.apiAdapter.locateAirports(query, radiusNm, state.filters);

      if (response.airports) {
        this.store.getState().setAirports(response.airports);

        if (response.center) {
          this.store.getState().setLocate({
            query,
            center: { lat: response.center.lat, lng: (response.center as any).lon || (response.center as any).lng || response.center.lat, label: response.center.label || '' },
            radiusNm
          });
        }

        this.showSuccess(response.pretty || `Located ${response.count} airports within ${radiusNm}nm of "${query}"`);
        this.store.getState().setLoading(false);
      }
    } catch (error: any) {
      console.error('Error in locate:', error);
      this.store.getState().setError('Error locating airports: ' + (error.message || 'Unknown error'));
      this.store.getState().setLoading(false);
    }
  }

  /**
   * Clear filters
   */
  private clearFilters(): void {
    this.store.getState().clearFilters();
    this.store.getState().setRoute(null);
    this.store.getState().setLocate(null);
    this.store.getState().setSearchQuery('');
    this.applyFilters();
  }

  /**
   * Handle reset zoom
   */
  private handleResetZoom(): void {
    const event = new CustomEvent('reset-zoom');
    window.dispatchEvent(event);
  }

  /**
   * Load airport details
   */
  private async loadAirportDetails(airport: Airport): Promise<void> {
    this.store.getState().setLoading(true);

    try {
      const persona = useStore.getState().ga.selectedPersona;
      const [detail, procedures, runways, aipEntries, rules, gaSummary] = await Promise.all([
        this.apiAdapter.getAirportDetail(airport.ident),
        this.apiAdapter.getAirportProcedures(airport.ident),
        this.apiAdapter.getAirportRunways(airport.ident),
        this.apiAdapter.getAirportAIPEntries(airport.ident),
        airport.iso_country ? this.apiAdapter.getCountryRules(airport.iso_country) : Promise.resolve(null),
        this.apiAdapter.getGASummary(airport.ident, persona).catch(() => null)
      ]);

      // Dispatch event to display airport details
      const event = new CustomEvent('display-airport-details', {
        detail: { detail, procedures, runways, aipEntries, rules, gaSummary }
      });
      window.dispatchEvent(event);

      this.store.getState().setLoading(false);
    } catch (error: any) {
      console.error('Error loading airport details:', error);
      this.store.getState().setError('Error loading airport details: ' + (error.message || 'Unknown error'));
      this.store.getState().setLoading(false);
    }
  }

  /**
   * Show success message
   */
  private showSuccess(message: string): void {
    // Remove existing success alerts
    const existingAlerts = document.querySelectorAll('.alert-success.position-fixed');
    existingAlerts.forEach(alert => alert.remove());

    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert alert-success alert-dismissible fade show position-fixed';
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alertDiv.innerHTML = `
      <i class="fas fa-check-circle"></i> ${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;

    document.body.appendChild(alertDiv);

    // Auto-remove after 3 seconds
    setTimeout(() => {
      if (alertDiv.parentNode) {
        alertDiv.remove();
      }
    }, 3000);
  }

  /**
   * Sync filters to UI controls (for chatbot filter profiles)
   */
  syncFiltersToUI(filters: Partial<FilterConfig>): void {
    // Update DOM controls to match filter state
    if (filters.country) {
      const select = document.getElementById('country-filter') as HTMLSelectElement;
      if (select) select.value = filters.country;
    }

    if (filters.has_procedures) {
      const checkbox = document.getElementById('has-procedures') as HTMLInputElement;
      if (checkbox) checkbox.checked = true;
    }

    if (filters.has_aip_data) {
      const checkbox = document.getElementById('has-aip-data') as HTMLInputElement;
      if (checkbox) checkbox.checked = true;
    }

    if (filters.has_hard_runway) {
      const checkbox = document.getElementById('has-hard-runway') as HTMLInputElement;
      if (checkbox) checkbox.checked = true;
    }

    if (filters.point_of_entry) {
      const checkbox = document.getElementById('border-crossing-only') as HTMLInputElement;
      if (checkbox) checkbox.checked = true;
    }

    // Update store filters
    this.store.getState().setFilters(filters);
  }
}

