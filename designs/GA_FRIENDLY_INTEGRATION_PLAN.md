# GA Friendliness Web UI Integration Plan

This document outlines the integration plan for adding GA friendliness data and persona-based scoring to the web UI. It builds on the designs in `GA_FRIENDLINESS_DESIGN.md` and follows the architecture principles in `UI_FILTER_STATE_DESIGN.md`.

---

## 1. Goals

1. **Display GA friendliness scores** for airports in the web UI
2. **Persona selection** - Allow users to choose their pilot persona (IFR touring, VFR budget, lunch stop, training)
3. **"Relevance" legend mode** - Color airports by relevance to selected persona
4. **Score breakdown** - Show feature score breakdown for transparency in a "Relevance" tab
5. **Integration with existing features** - Route search and locate should leverage GA scores

---

## 2. Architecture Principles (Inherited)

Following `UI_FILTER_STATE_DESIGN.md`:

1. **Single Source of Truth** - Zustand store holds all state including persona selection
2. **Separation of Concerns** - Backend handles GA data queries, frontend handles display
3. **Reactive Updates** - Persona changes trigger automatic UI/map updates via store subscriptions
4. **Type Safety** - Full TypeScript types for GA data structures

**New principles for GA integration:**

5. **Optional Enhancement** - GA data is additive; UI works without it
6. **Lazy Loading** - GA data loaded on-demand, not for every airport
7. **Score Transparency** - Every score is explainable from underlying features
8. **Graceful Degradation** - Missing GA data shown as "unknown" relevance, not hidden

---

## 3. Data Flow Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Backend (Python/FastAPI)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐  │
│  │  euro_aip.sqlite │    │  ga_meta.sqlite │    │  GAFriendlinessService  │  │
│  │  (airports,      │◄───│  (stats, scores,│◄───│  - load personas        │  │
│  │   procedures)    │    │   summaries)    │    │  - compute scores       │  │
│  └─────────────────┘    └─────────────────┘    │  - query by ICAO        │  │
│                                                 └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ REST API
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (TypeScript)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────┐    ┌───────────────┐    ┌────────────────────────────┐   │
│  │  Zustand Store │◄───│  API Adapter  │◄───│  GA Friendliness API       │   │
│  │  - persona     │    │  + GA methods │    │  - /api/ga/scores/{icaos}  │   │
│  │  - gaData      │    │               │    │  - /api/ga/personas        │   │
│  └───────────────┘    └───────────────┘    │  - /api/ga/summary/{icao}  │   │
│         │                                   └────────────────────────────┘   │
│         │ subscription                                                       │
│         ▼                                                                    │
│  ┌───────────────┐    ┌───────────────┐    ┌────────────────────────────┐   │
│  │  UI Manager   │    │  Visualization │    │  GA Score Panel            │   │
│  │  - persona    │    │  Engine        │    │  - score display           │   │
│  │    selector   │    │  - GA legend   │    │  - feature breakdown       │   │
│  └───────────────┘    │    mode        │    │  - persona comparison      │   │
│                       └───────────────┘    └────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Backend Changes

### 4.1 New API Endpoints

**Option A: Separate GA Router (Recommended)**

Create new `web/server/api/ga_friendliness.py`:

```python
# GET /api/ga/personas
# Returns available personas with labels and descriptions
{
  "personas": [
    {"id": "ifr_touring_sr22", "label": "IFR touring (SR22)", "description": "..."},
    {"id": "vfr_budget", "label": "VFR budget flyer", "description": "..."},
    ...
  ],
  "default_persona": "ifr_touring_sr22"
}

# GET /api/ga/scores?icaos=EGKB,LFPG,EHAM&persona=ifr_touring_sr22
# Bulk query GA scores for airports
{
  "persona": "ifr_touring_sr22",
  "scores": {
    "EGKB": {
      "score": 0.75,
      "features": {
        "ga_cost_score": 0.6,
        "ga_hassle_score": 0.8,
        "ga_ops_ifr_score": 0.9,
        ...
      },
      "has_data": true
    },
    "LFPG": {
      "score": 0.45,
      "features": {...},
      "has_data": true
    },
    "EHAM": {
      "score": null,
      "features": null,
      "has_data": false
    }
  }
}

# GET /api/ga/summary/{icao}
# Get full GA summary for airport detail view
{
  "icao": "EGKB",
  "summary_text": "Generally GA-friendly field...",
  "tags": ["GA friendly", "good restaurant", "reasonable fees"],
  "rating_avg": 4.2,
  "rating_count": 15,
  "features": {
    "ga_cost_score": 0.6,
    ...
  },
  "persona_scores": {
    "ifr_touring_sr22": 0.75,
    "vfr_budget": 0.82,
    ...
  },
  "fees": {
    "landing_fee_band": "€20-40",
    "parking_fee": "€10/night"
  }
}
```

**Option B: Extend Existing Airport Endpoints**

Add GA data to existing airport responses:

```python
# GET /api/airports/{icao}?include_ga=true&persona=ifr_touring_sr22
# Existing response + ga_friendliness object
```

**Recommendation:** Option A (Separate Router)
- Cleaner separation of concerns
- Optional GA feature doesn't bloat core API
- Easier to version/evolve independently
- Follows existing pattern (airports.py, rules.py, procedures.py)

### 4.2 GAFriendlinessService

Create `web/server/api/ga_friendliness.py`:

```python
class GAFriendlinessService:
    """Service for querying GA friendliness data."""
    
    def __init__(self, ga_meta_db_path: Path):
        self.db_path = ga_meta_db_path
        self.persona_manager = None  # Lazy load
        
    def get_personas(self) -> List[PersonaInfo]:
        """Get available personas."""
        
    def get_scores_for_airports(
        self,
        icaos: List[str],
        persona_id: str
    ) -> Dict[str, AirportGAScore]:
        """Bulk query scores for airports."""
        
    def get_summary(self, icao: str) -> Optional[AirportGASummary]:
        """Get full GA summary for airport."""
```

### 4.3 Database Configuration

**Environment Variable Pattern (mirroring `AIRPORTS_DB`):**

Add to `web/server/security_config.py`:

```python
def get_safe_ga_meta_db_path() -> str:
    """Get a safe GA meta database path with validation."""
    db_path = os.getenv("GA_META_DB", "ga_meta.db")
    
    # In production, ensure database is in a safe location
    if ENVIRONMENT == "production":
        # Ensure database is within allowed directory
        if not db_path.startswith(ALLOWED_DIR):
            db_path = f"{ALLOWED_DIR}/ga_meta.db"
    
    return db_path
```

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `GA_META_DB` | `ga_meta.db` | Path to GA meta database |
| `GA_FRIENDLINESS_ENABLED` | `true` | Enable/disable GA features |

**Sample `dev.env` additions:**

```bash
# GA Friendliness Configuration
GA_META_DB=../tmp/ga_meta.sqlite
GA_FRIENDLINESS_ENABLED=true
```

### 4.4 Database Attachment Strategy

**Decision: Always Attach at Startup (Option A)**

Rationale:
- Consistent with existing database access pattern
- GA features are expected to be commonly used
- Simpler implementation, no lazy-loading complexity
- If GA db doesn't exist, GA features gracefully degrade

```python
# In main.py lifespan handler
@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_storage, model, ga_service
    
    # ... existing startup ...
    
    # Initialize GA Friendliness service (optional)
    ga_meta_path = get_safe_ga_meta_db_path()
    ga_enabled = os.getenv("GA_FRIENDLINESS_ENABLED", "true").lower() == "true"
    
    if ga_enabled and Path(ga_meta_path).exists():
        logger.info(f"Loading GA friendliness data from '{ga_meta_path}'")
        ga_service = GAFriendlinessService(Path(ga_meta_path))
        ga_friendliness.set_service(ga_service)
        logger.info("GA friendliness service initialized")
    else:
        logger.info("GA friendliness disabled or database not found")
        ga_service = None
    
    yield
    
    # ... existing shutdown ...
```

**Graceful Degradation:**

When `ga_meta.db` is not available:
- `/api/ga/personas` returns empty list
- `/api/ga/scores` returns `has_data: false` for all airports
- `/api/ga/summary/{icao}` returns `null`
- Frontend shows "Unknown" relevance for all airports
- "Relevance" tab shows "No GA data available" message

---

## 5. Frontend Changes

### 5.1 Type Definitions

Add to `ts/store/types.ts`:

```typescript
/**
 * Persona definition
 */
export interface Persona {
  id: string;
  label: string;
  description: string;
}

/**
 * GA feature scores (all 0-1 normalized)
 */
export interface GAFeatureScores {
  ga_cost_score: number | null;
  ga_review_score: number | null;
  ga_hassle_score: number | null;
  ga_ops_ifr_score: number | null;
  ga_ops_vfr_score: number | null;
  ga_access_score: number | null;
  ga_fun_score: number | null;
  ga_hospitality_score: number | null;
}

/**
 * GA score for an airport
 */
export interface AirportGAScore {
  score: number | null;
  features: GAFeatureScores | null;
  has_data: boolean;
}

/**
 * Full GA summary for airport detail
 */
export interface AirportGASummary {
  icao: string;
  summary_text: string | null;
  tags: string[];
  rating_avg: number | null;
  rating_count: number;
  features: GAFeatureScores | null;
  persona_scores: Record<string, number>;
  fees: {
    landing_fee_band: string | null;
    parking_fee: string | null;
  } | null;
}

/**
 * GA state in store
 */
export interface GAState {
  selectedPersona: string;           // Current persona ID
  personas: Persona[];               // Available personas
  scores: Map<string, AirportGAScore>; // Cached scores by ICAO
  summaries: Map<string, AirportGASummary>; // Cached summaries
  isLoading: boolean;
}
```

### 5.2 Store Changes

Add to `ts/store/store.ts`:

```typescript
interface AppState {
  // ... existing state ...
  
  // GA Friendliness state
  ga: GAState;
}

interface StoreActions {
  // ... existing actions ...
  
  // GA actions
  setSelectedPersona: (personaId: string) => void;
  setPersonas: (personas: Persona[]) => void;
  setGAScores: (scores: Record<string, AirportGAScore>) => void;
  setGASummary: (icao: string, summary: AirportGASummary) => void;
  setGALoading: (loading: boolean) => void;
  clearGACache: () => void;
}

const initialState: AppState = {
  // ... existing ...
  ga: {
    selectedPersona: 'ifr_touring_sr22', // Default
    personas: [],
    scores: new Map(),
    summaries: new Map(),
    isLoading: false
  }
};
```

### 5.3 API Adapter Extensions

Add to `ts/adapters/api-adapter.ts`:

```typescript
export class APIAdapter {
  // ... existing methods ...
  
  /**
   * Get available personas
   */
  async getPersonas(): Promise<{personas: Persona[], default_persona: string}> {
    const endpoint = '/api/ga/personas';
    return await this.request(endpoint);
  }
  
  /**
   * Get GA scores for airports
   */
  async getGAScores(
    icaos: string[],
    personaId: string
  ): Promise<{persona: string, scores: Record<string, AirportGAScore>}> {
    const params = new URLSearchParams();
    params.set('icaos', icaos.join(','));
    params.set('persona', personaId);
    const endpoint = `/api/ga/scores?${params.toString()}`;
    return await this.request(endpoint);
  }
  
  /**
   * Get GA summary for airport
   */
  async getGASummary(icao: string): Promise<AirportGASummary | null> {
    const endpoint = `/api/ga/summary/${icao}`;
    return await this.request(endpoint);
  }
}
```

### 5.4 UI Components

#### 5.4.1 Persona Selector

Add persona dropdown to filter panel with localStorage persistence:

```html
<!-- In index.html, filter panel - new section above filters -->
<div class="persona-section">
  <div class="persona-header">
    <label for="persona-select">Flying as:</label>
    <select id="persona-select" class="persona-dropdown">
      <!-- Populated dynamically -->
    </select>
  </div>
  <p class="persona-description" id="persona-description">
    <!-- Dynamic description -->
  </p>
</div>
```

**Persona Selector Manager:**

```typescript
// ts/managers/persona-manager.ts

const STORAGE_KEY = 'flyfun_selected_persona';
const DEFAULT_PERSONA = 'ifr_touring_sr22';

export class PersonaManager {
  private store: ReturnType<typeof useStore>;
  private apiAdapter: APIAdapter;
  
  constructor(store: ReturnType<typeof useStore>, apiAdapter: APIAdapter) {
    this.store = store;
    this.apiAdapter = apiAdapter;
  }
  
  /**
   * Initialize personas on app startup
   */
  async init(): Promise<void> {
    // Load personas from API
    const { personas, default_persona } = await this.apiAdapter.getPersonas();
    this.store.getState().setPersonas(personas);
    
    // Restore persisted persona or use default
    const savedPersona = localStorage.getItem(STORAGE_KEY);
    const initialPersona = savedPersona && personas.some(p => p.id === savedPersona)
      ? savedPersona
      : default_persona || DEFAULT_PERSONA;
    
    this.store.getState().setSelectedPersona(initialPersona);
    
    // Setup UI
    this.initSelector();
    this.subscribeToChanges();
  }
  
  /**
   * Initialize the dropdown UI
   */
  private initSelector(): void {
    const select = document.getElementById('persona-select') as HTMLSelectElement;
    const description = document.getElementById('persona-description');
    
    if (!select) return;
    
    // Populate options
    const personas = this.store.getState().ga.personas;
    select.innerHTML = personas.map(p => 
      `<option value="${p.id}">${p.label}</option>`
    ).join('');
    
    // Set initial value
    select.value = this.store.getState().ga.selectedPersona;
    this.updateDescription(description, select.value);
    
    // Handle changes
    select.addEventListener('change', (e) => {
      const personaId = (e.target as HTMLSelectElement).value;
      this.store.getState().setSelectedPersona(personaId);
      localStorage.setItem(STORAGE_KEY, personaId);
      this.updateDescription(description, personaId);
    });
  }
  
  /**
   * Update persona description text
   */
  private updateDescription(element: HTMLElement | null, personaId: string): void {
    if (!element) return;
    
    const persona = this.store.getState().ga.personas.find(p => p.id === personaId);
    element.textContent = persona?.description || '';
  }
  
  /**
   * Subscribe to persona changes for reactive updates
   */
  private subscribeToChanges(): void {
    this.store.subscribe((state, prevState) => {
      if (state.ga.selectedPersona !== prevState.ga.selectedPersona) {
        // Clear cached scores (they're persona-specific)
        this.store.getState().clearGAScoreCache();
        
        // Trigger refresh if in relevance legend mode
        if (state.visualization.legendMode === 'relevance') {
          this.refreshRelevanceScores();
        }
      }
    });
  }
  
  /**
   * Refresh relevance scores for visible airports
   */
  private async refreshRelevanceScores(): Promise<void> {
    const state = this.store.getState();
    const visibleIcaos = state.filteredAirports.map(a => a.ident);
    
    if (visibleIcaos.length === 0) return;
    
    this.store.getState().setGALoading(true);
    
    try {
      const response = await this.apiAdapter.getGAScores(
        visibleIcaos, 
        state.ga.selectedPersona
      );
      this.store.getState().setGAScores(response.scores);
    } finally {
      this.store.getState().setGALoading(false);
    }
  }
}
```

**CSS for Persona Selector:**

```css
.persona-section {
  background: var(--panel-bg-secondary);
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.persona-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.persona-header label {
  font-weight: 500;
  white-space: nowrap;
}

.persona-dropdown {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border-color);
  border-radius: 4px;
  font-size: 14px;
}

.persona-description {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.4;
}
```

#### 5.4.2 "Relevance" Tab in Airport Details

Add new "Relevance" tab to airport detail panel. **Position: Last tab** (after existing Details, AIP, Rules tabs):

**Tab Structure:**

```html
<!-- Tab bar (Relevance tab added LAST) -->
<div class="detail-tabs">
  <button class="tab-btn active" data-tab="details">Details</button>
  <button class="tab-btn" data-tab="aip">AIP</button>
  <button class="tab-btn" data-tab="rules">Rules</button>
  <button class="tab-btn" data-tab="relevance">Relevance</button> <!-- NEW - last position -->
</div>

<!-- Relevance Tab Content -->
<div id="relevance-tab" class="tab-content" data-tab="relevance">
  <!-- Overall Score Section -->
  <div class="relevance-summary">
    <div class="relevance-badge" data-bucket="top-quartile">
      <span class="badge-label">Most Relevant</span>
      <span class="badge-score">0.82</span>
    </div>
    <div class="relevance-persona">
      for <strong id="relevance-persona-name">IFR touring (SR22)</strong>
    </div>
    <p class="relevance-explanation" id="relevance-explanation">
      <!-- Dynamic explanation of score -->
    </p>
  </div>

  <!-- Feature Breakdown Section -->
  <div class="feature-breakdown">
    <h4>Score Breakdown</h4>
    <div class="features-list">
      <!-- Each feature as a row -->
      <div class="feature-row" data-feature="ga_cost_score" data-weighted="true">
        <div class="feature-header">
          <span class="feature-name">Cost</span>
          <span class="feature-weight" title="Weight for selected persona">×0.20</span>
          <span class="feature-value">0.6</span>
        </div>
        <div class="feature-bar-container">
          <div class="feature-bar" style="width: 60%"></div>
        </div>
        <p class="feature-description">
          Lower cost = higher score. Based on landing fees, handling requirements.
        </p>
      </div>
      <!-- Repeat for all 8 features -->
    </div>
  </div>

  <!-- Source Data Section -->
  <div class="relevance-source">
    <h4>Data Sources</h4>
    <div class="source-info">
      <div class="source-row">
        <span class="source-label">Reviews</span>
        <span class="source-value">12 reviews (avg: 4.2/5)</span>
      </div>
      <div class="source-row">
        <span class="source-label">Last Updated</span>
        <span class="source-value">2025-11-15</span>
      </div>
      <div class="source-row">
        <span class="source-label">Data Source</span>
        <span class="source-value">airfield.directory</span>
      </div>
    </div>
  </div>

  <!-- Tags Section -->
  <div class="relevance-tags" id="relevance-tags">
    <h4>Tags</h4>
    <div class="tag-list">
      <span class="tag">GA friendly</span>
      <span class="tag">good restaurant</span>
      <span class="tag">reasonable fees</span>
    </div>
  </div>

  <!-- Summary Text Section -->
  <div class="relevance-summary-text" id="relevance-summary-text">
    <h4>Summary</h4>
    <p><!-- LLM-generated summary text --></p>
  </div>

  <!-- No Data State -->
  <div class="relevance-no-data" id="relevance-no-data" style="display: none;">
    <div class="no-data-icon">?</div>
    <p class="no-data-message">No GA friendliness data available for this airport.</p>
    <p class="no-data-hint">This airport hasn't been reviewed yet.</p>
  </div>
</div>
```

**Feature Descriptions (for tooltips/descriptions):**

| Feature | Display Name | Description |
|---------|--------------|-------------|
| `ga_cost_score` | Cost | Lower landing/handling fees = higher score |
| `ga_review_score` | Overall Reviews | Aggregate sentiment from pilot reviews |
| `ga_hassle_score` | Low Hassle | Simpler procedures, less bureaucracy = higher |
| `ga_ops_ifr_score` | IFR Operations | Quality of IFR procedures and capability |
| `ga_ops_vfr_score` | VFR Operations | VFR-friendliness, circuit patterns, traffic |
| `ga_access_score` | Ground Access | Transport, parking, accessibility |
| `ga_fun_score` | Fun/Atmosphere | Overall "vibe", enjoyment factor |
| `ga_hospitality_score` | Hospitality | Restaurant, accommodation availability |

**Score Explanation Generation:**

```typescript
function generateScoreExplanation(
  score: number,
  features: GAFeatureScores,
  persona: Persona
): string {
  // Example: "This airport scores well for IFR touring due to excellent IFR 
  // procedures (0.9) and low hassle (0.8), though cost is moderate (0.5)."
  
  const weights = getPersonaWeights(persona.id);
  const topContributors = Object.entries(features)
    .filter(([key, value]) => value !== null && weights[key] > 0)
    .sort((a, b) => (b[1] as number) * weights[b[0]] - (a[1] as number) * weights[a[0]])
    .slice(0, 3);
  
  // Generate natural language explanation
  return formatExplanation(score, topContributors, persona);
}
```

**Visual Design Notes:**

- Feature rows with non-zero weight for selected persona are visually highlighted (e.g., bold, accent color)
- Features with zero weight are shown dimmed with "(not used for this persona)" indicator
- Score bars use the same color scheme as the relevance legend
- Unknown/null feature values show "No data" instead of bar

#### 5.4.3 "Relevance" Legend Mode

Add new "Relevance" legend mode with **dynamic quartile-based buckets**:

```typescript
// In types.ts
export type LegendMode = 
  | 'airport-type' 
  | 'procedure-precision' 
  | 'runway-length' 
  | 'country'
  | 'relevance';  // NEW - GA-based relevance

/**
 * Relevance buckets for legend mode (quartile-based)
 */
export type RelevanceBucket = 
  | 'top-quartile'      // Top 25% of scores
  | 'second-quartile'   // 50-75% percentile
  | 'third-quartile'    // 25-50% percentile  
  | 'bottom-quartile'   // Bottom 25% of scores
  | 'unknown';          // No GA data

// Bucket configuration (colors only - thresholds computed dynamically)
export interface RelevanceBucketConfig {
  id: RelevanceBucket;
  label: string;
  color: string;
}

export const RELEVANCE_BUCKET_CONFIG: RelevanceBucketConfig[] = [
  { id: 'top-quartile', label: 'Most Relevant', color: '#27ae60' },      // Green
  { id: 'second-quartile', label: 'Relevant', color: '#3498db' },        // Blue
  { id: 'third-quartile', label: 'Less Relevant', color: '#e67e22' },    // Orange
  { id: 'bottom-quartile', label: 'Least Relevant', color: '#e74c3c' },  // Red
  { id: 'unknown', label: 'Unknown', color: '#95a5a6' },                 // Gray
];
```

**Dynamic Quartile Calculation:**

```typescript
// ts/utils/relevance.ts

/**
 * Compute quartile thresholds from actual score distribution.
 * 
 * Benefits:
 * - Always produces meaningful buckets regardless of scoring formula
 * - Works for any persona (different weight combinations)
 * - Adapts to score distribution changes
 */
export function computeQuartileThresholds(
  scores: Map<string, AirportGAScore>
): { q1: number; q2: number; q3: number } | null {
  // Extract valid scores
  const validScores = Array.from(scores.values())
    .filter(s => s.has_data && s.score !== null)
    .map(s => s.score as number)
    .sort((a, b) => a - b);
  
  if (validScores.length < 4) {
    return null; // Not enough data for quartiles
  }
  
  const n = validScores.length;
  return {
    q1: validScores[Math.floor(n * 0.25)],  // 25th percentile
    q2: validScores[Math.floor(n * 0.50)],  // 50th percentile (median)
    q3: validScores[Math.floor(n * 0.75)],  // 75th percentile
  };
}

/**
 * Get bucket for a score based on computed quartiles.
 */
export function getRelevanceBucket(
  score: number | null,
  quartiles: { q1: number; q2: number; q3: number } | null
): RelevanceBucket {
  if (score === null) {
    return 'unknown';
  }
  
  if (!quartiles) {
    // Fallback: no quartile data, treat all as unknown
    return 'unknown';
  }
  
  if (score >= quartiles.q3) return 'top-quartile';
  if (score >= quartiles.q2) return 'second-quartile';
  if (score >= quartiles.q1) return 'third-quartile';
  return 'bottom-quartile';
}
```

**Store: Computed Quartiles**

```typescript
// In GAState
export interface GAState {
  // ... existing ...
  
  // Computed from current scores (recalculated when scores change)
  computedQuartiles: { q1: number; q2: number; q3: number } | null;
}

// In store actions
setGAScores: (scores: Record<string, AirportGAScore>) => {
  const scoresMap = new Map(Object.entries(scores));
  const quartiles = computeQuartileThresholds(scoresMap);
  
  set(state => ({
    ga: {
      ...state.ga,
      scores: scoresMap,
      computedQuartiles: quartiles
    }
  }));
}
```

**Visualization Engine:**

```typescript
// In visualization-engine.ts
private getMarkerColorForRelevance(airport: Airport): string {
  const state = this.store.getState();
  const gaScore = state.ga.scores.get(airport.ident);
  const quartiles = state.ga.computedQuartiles;
  
  const bucket = getRelevanceBucket(gaScore?.score ?? null, quartiles);
  const config = RELEVANCE_BUCKET_CONFIG.find(c => c.id === bucket);
  return config?.color ?? '#95a5a6';
}
```

**Legend Panel for Relevance Mode:**

```html
<div class="legend-panel" data-mode="relevance">
  <h4>Relevance to <span id="legend-persona-name">IFR touring</span></h4>
  <div class="legend-items">
    <div class="legend-item">
      <span class="legend-dot" style="background: #27ae60"></span>
      <span>Most Relevant (top 25%)</span>
    </div>
    <div class="legend-item">
      <span class="legend-dot" style="background: #3498db"></span>
      <span>Relevant</span>
    </div>
    <div class="legend-item">
      <span class="legend-dot" style="background: #e67e22"></span>
      <span>Less Relevant</span>
    </div>
    <div class="legend-item">
      <span class="legend-dot" style="background: #e74c3c"></span>
      <span>Least Relevant (bottom 25%)</span>
    </div>
    <div class="legend-item">
      <span class="legend-dot" style="background: #95a5a6"></span>
      <span>Unknown</span>
    </div>
  </div>
</div>
```

**✅ Decision: Dynamic Quartile-Based Bucketing**

Rationale:
- Hardcoded thresholds (0.7, 0.4) don't adapt to different scoring distributions
- Different personas produce different score ranges
- Quartiles ensure ~25% of airports in each bucket (balanced visualization)
- Works regardless of how scoring formula evolves

---

## 6. Integration Points

### 6.1 Route Search Integration

When displaying route search results, fetch and display GA scores:

```typescript
// After route search completes
async function onRouteSearchComplete(airports: Airport[]): void {
  const store = useStore.getState();
  const icaos = airports.map(a => a.ident);
  const persona = store.ga.selectedPersona;
  
  // Fetch GA scores for route airports
  const response = await apiAdapter.getGAScores(icaos, persona);
  store.setGAScores(response.scores);
  
  // Optionally sort by GA score
  // airports.sort((a, b) => (response.scores[b.ident]?.score ?? 0) - (response.scores[a.ident]?.score ?? 0));
}
```

### 6.2 Airport Detail View Integration

When showing airport details, load GA summary:

```typescript
// In UIManager or detail component
async function loadAirportGAData(icao: string): void {
  const store = useStore.getState();
  
  // Check cache first
  if (store.ga.summaries.has(icao)) {
    this.displayGASummary(store.ga.summaries.get(icao)!);
    return;
  }
  
  // Fetch from API
  const summary = await this.apiAdapter.getGASummary(icao);
  if (summary) {
    store.setGASummary(icao, summary);
    this.displayGASummary(summary);
  }
}
```

### 6.3 Chatbot Integration

The aviation agent can reference GA scores in responses:

```typescript
// In LLMIntegration
handleVisualization(viz: Visualization): void {
  // Existing handling...
  
  // If visualization includes GA context
  if (viz.ga_context) {
    // Apply persona if specified
    if (viz.ga_context.persona) {
      this.store.getState().setSelectedPersona(viz.ga_context.persona);
    }
    
    // If sorting by GA score requested
    if (viz.ga_context.sort_by_ga_score) {
      // Trigger GA score fetch and re-sort
    }
  }
}
```

### 6.4 Filter Integration

Consider adding GA-based filters:

```typescript
// New filter options
interface FilterConfig {
  // ... existing ...
  
  // GA filters (applied server-side)
  min_ga_score: number | null;        // Minimum GA score (0-1)
  has_ga_data: boolean | null;         // Filter to airports with GA data
  ga_persona: string | null;           // Persona for scoring
}
```

---

## 7. Caching Strategy

### 7.1 Frontend Caching

```typescript
interface GACacheConfig {
  maxScoreEntries: number;    // Max ICAO scores to cache (e.g., 500)
  maxSummaryEntries: number;  // Max full summaries to cache (e.g., 50)
  scoreTTL: number;           // Score cache TTL in ms (e.g., 5 minutes)
  summaryTTL: number;         // Summary cache TTL in ms (e.g., 10 minutes)
}

// Clear cache when persona changes (scores are persona-specific)
setSelectedPersona: (personaId: string) => {
  set(state => ({
    ga: {
      ...state.ga,
      selectedPersona: personaId,
      scores: new Map() // Clear score cache on persona change
    }
  }));
}
```

### 7.2 Backend Caching

- Persona configs: Load once at startup
- GA scores: Consider in-memory LRU cache for hot airports
- Summaries: Cache in Redis/memory for repeated queries

---

## 8. Performance Considerations

### 8.1 Bulk Loading

For map views with many airports:
- Don't load GA data for every visible airport
- Load GA data only for:
  - Selected airport (detail view)
  - Route search results
  - Explicit request (legend mode = ga-score)

### 8.2 Progressive Loading

```typescript
// For ga-score legend mode with many airports
async function loadGAScoresProgressively(icaos: string[]): void {
  const BATCH_SIZE = 50;
  
  for (let i = 0; i < icaos.length; i += BATCH_SIZE) {
    const batch = icaos.slice(i, i + BATCH_SIZE);
    const scores = await apiAdapter.getGAScores(batch, store.ga.selectedPersona);
    store.setGAScores(scores.scores);
    // Map updates reactively
  }
}
```

### 8.3 Debouncing Persona Changes

```typescript
// Debounce persona changes to avoid rapid API calls
const debouncedPersonaChange = debounce((personaId: string) => {
  this.loadGAScoresForVisibleAirports(personaId);
}, 300);
```

---

## 9. Design Decisions (Resolved)

### 9.1 Data Availability

**Decision:** Show "Unknown" relevance indicator for airports without GA data.
- Transparent about data availability
- "Unknown" bucket in legend mode
- Gray marker color for unknown

### 9.2 Persona Persistence

**Decision:** Use localStorage for persona persistence across sessions.
- User preference persists across browser refreshes
- Default to `ifr_touring_sr22` if no stored preference
- Store key: `flyfun_selected_persona`

### 9.3 Score Visibility

**Decision:** "Relevance" legend mode + always in detail view's "Relevance" tab.
- Map markers colored by relevance bucket when legend mode = "relevance"
- Detailed breakdown always available in airport detail "Relevance" tab
- Both views show same underlying data, different granularity

### 9.4 Backend Database Path

**Decision:** Use `GA_META_DB` environment variable mirroring `AIRPORTS_DB` pattern.
- Follows existing pattern in `security_config.py`
- Defaults to `ga_meta.db` (same directory pattern)
- Production validation same as `get_safe_db_path()`

### 9.5 Feature Visibility in Detail View

**Decision:** Show all features with explanation, highlight weighted features.
- "Relevance" tab shows all 8 features as horizontal bars
- Features with non-zero weight for selected persona are highlighted
- Each feature has an explanatory tooltip/label
- Summary text explains overall score calculation

---

## 10. Consistency Strategy: Library ↔ API ↔ UI

This section addresses how to maintain consistency of feature names, persona definitions, weights, and bucket thresholds across all three layers.

### 10.1 Sources of Truth

| Data | Source of Truth | Location |
|------|-----------------|----------|
| Feature names | Python library | `shared/ga_friendliness/personas.py::FEATURE_NAMES` |
| Persona definitions | Python library | `shared/ga_friendliness/config.py::DEFAULT_PERSONAS` |
| Persona weights | Python library | `PersonaConfig.weights` in personas.json |
| Relevance thresholds | Shared config | New: `shared/ga_friendliness/ui_config.py` |
| Feature display names | Shared config | New: `shared/ga_friendliness/ui_config.py` |

### 10.2 Python API: Direct Reuse (Easy)

The backend API directly imports and uses the library:

```python
# web/server/api/ga_friendliness.py

from shared.ga_friendliness import (
    PersonaManager,
    get_default_personas,
    FEATURE_NAMES,
)
from shared.ga_friendliness.ui_config import (
    FEATURE_DISPLAY_NAMES,
    RELEVANCE_BUCKETS,  # Colors only - quartiles computed client-side
)

class GAFriendlinessService:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.personas_config = get_default_personas()
        self.persona_manager = PersonaManager(self.personas_config)
    
    def get_personas(self) -> dict:
        """Return personas with full metadata for UI."""
        return {
            "personas": [
                {
                    "id": p.id,
                    "label": p.label,
                    "description": p.description,
                    "weights": p.weights.model_dump(),  # Full weights for UI
                }
                for p in self.persona_manager.list_personas()
            ],
            "default_persona": "ifr_touring_sr22",
            "feature_names": FEATURE_NAMES,
            "feature_display_names": FEATURE_DISPLAY_NAMES,
            "relevance_buckets": RELEVANCE_BUCKETS,  # Colors only - thresholds computed client-side
        }
```

**Key principle:** API never duplicates definitions - always imports from library.

### 10.3 New: UI Config Module

Create `shared/ga_friendliness/ui_config.py` as centralized UI-related config:

```python
"""
UI configuration for GA friendliness display.

This module is the source of truth for:
- Feature display names and descriptions
- Relevance bucket thresholds
- Color schemes (for reference, actual colors in CSS)

These values are served via API to ensure frontend consistency.
"""

from typing import Dict, List
from dataclasses import dataclass

# Feature display configuration
FEATURE_DISPLAY_NAMES: Dict[str, str] = {
    "ga_cost_score": "Cost",
    "ga_review_score": "Overall Reviews", 
    "ga_hassle_score": "Low Hassle",
    "ga_ops_ifr_score": "IFR Operations",
    "ga_ops_vfr_score": "VFR Operations",
    "ga_access_score": "Ground Access",
    "ga_fun_score": "Fun/Atmosphere",
    "ga_hospitality_score": "Hospitality",
}

FEATURE_DESCRIPTIONS: Dict[str, str] = {
    "ga_cost_score": "Lower landing/handling fees = higher score",
    "ga_review_score": "Aggregate sentiment from pilot reviews",
    "ga_hassle_score": "Simpler procedures, less bureaucracy = higher",
    "ga_ops_ifr_score": "Quality of IFR procedures and capability",
    "ga_ops_vfr_score": "VFR-friendliness, circuit patterns, traffic",
    "ga_access_score": "Transport, parking, accessibility",
    "ga_fun_score": "Overall vibe, enjoyment factor",
    "ga_hospitality_score": "Restaurant, accommodation availability",
}

# Relevance bucket configuration (colors only - thresholds computed dynamically from quartiles)
RELEVANCE_BUCKETS: List[Dict] = [
    {"id": "top-quartile", "label": "Most Relevant", "color": "#27ae60"},      # Green - top 25%
    {"id": "second-quartile", "label": "Relevant", "color": "#3498db"},        # Blue - 50-75%
    {"id": "third-quartile", "label": "Less Relevant", "color": "#e67e22"},    # Orange - 25-50%
    {"id": "bottom-quartile", "label": "Least Relevant", "color": "#e74c3c"},  # Red - bottom 25%
    {"id": "unknown", "label": "Unknown", "color": "#95a5a6"},                 # Gray - no data
]

# Note: Bucket thresholds are computed dynamically from actual score distribution
# using quartiles. This ensures meaningful buckets regardless of scoring formula
# or persona. See frontend: ts/utils/relevance.ts::computeQuartileThresholds()
```

### 10.4 TypeScript: API-Driven Configuration

**Strategy:** Frontend fetches all configuration from API on startup - no hardcoded definitions.

#### 10.4.1 Enhanced API Response

```python
# GET /api/ga/config
# Returns all UI configuration from library
{
    "feature_names": ["ga_cost_score", "ga_review_score", ...],
    "feature_display_names": {
        "ga_cost_score": "Cost",
        ...
    },
    "feature_descriptions": {
        "ga_cost_score": "Lower landing/handling fees = higher score",
        ...
    },
    "relevance_buckets": [
        # Bucket colors only - thresholds computed dynamically from quartiles
        {"id": "top-quartile", "label": "Most Relevant", "color": "#27ae60"},
        {"id": "second-quartile", "label": "Relevant", "color": "#3498db"},
        {"id": "third-quartile", "label": "Less Relevant", "color": "#e67e22"},
        {"id": "bottom-quartile", "label": "Least Relevant", "color": "#e74c3c"},
        {"id": "unknown", "label": "Unknown", "color": "#95a5a6"},
    ],
    "personas": [
        {
            "id": "ifr_touring_sr22",
            "label": "IFR touring (SR22)",
            "description": "...",
            "weights": {"ga_cost_score": 0.20, "ga_hassle_score": 0.20, ...}
        },
        ...
    ],
    "default_persona": "ifr_touring_sr22",
    "version": "1.0"
}
```

#### 10.4.2 TypeScript Store for Config

```typescript
// ts/store/types.ts

/**
 * Relevance bucket configuration (colors only - thresholds computed from quartiles)
 */
export interface RelevanceBucketConfig {
    id: RelevanceBucket;
    label: string;
    color: string;
}

/**
 * GA configuration from API (source of truth)
 */
export interface GAConfig {
    feature_names: string[];
    feature_display_names: Record<string, string>;
    feature_descriptions: Record<string, string>;
    relevance_buckets: RelevanceBucketConfig[];  // Colors only - no thresholds
    personas: PersonaWithWeights[];
    default_persona: string;
    version: string;
}

// Note: RelevanceThreshold interface removed - thresholds computed from quartiles
// See RelevanceBucketConfig (colors only) earlier in this file

export interface PersonaWithWeights extends Persona {
    weights: Record<string, number>;
}
```

```typescript
// ts/store/store.ts - GAState extended

export interface GAState {
    // Configuration from API
    config: GAConfig | null;
    configLoaded: boolean;
    
    // Runtime state
    selectedPersona: string;
    scores: Map<string, AirportGAScore>;
    summaries: Map<string, AirportGASummary>;
    isLoading: boolean;
    
    // Computed from current scores (recalculated when scores change)
    computedQuartiles: { q1: number; q2: number; q3: number } | null;
}
```

#### 10.4.3 Config Loading on Startup

```typescript
// ts/managers/persona-manager.ts

export class PersonaManager {
    async init(): Promise<void> {
        // 1. Load config from API (source of truth)
        const config = await this.apiAdapter.getGAConfig();
        this.store.getState().setGAConfig(config);
        
        // 2. Restore persona from localStorage (validated against config)
        const savedPersona = localStorage.getItem(STORAGE_KEY);
        const validPersona = config.personas.find(p => p.id === savedPersona);
        const initialPersona = validPersona ? savedPersona : config.default_persona;
        
        this.store.getState().setSelectedPersona(initialPersona);
        
        // 3. Initialize UI with config-driven values
        this.initSelector();
    }
}
```

#### 10.4.4 Config-Driven Bucket Calculation

```typescript
// ts/utils/relevance.ts

/**
 * Get relevance bucket for a score - uses config from store
 */
export // Note: getRelevanceBucket() using dynamic quartiles is defined in section 5.4.3
// See ts/utils/relevance.ts::getRelevanceBucket() and computeQuartileThresholds()

// Usage in VisualizationEngine - uses dynamic quartiles computed from score distribution
private getMarkerColorForRelevance(airport: Airport): string {
    const state = this.store.getState();
    const gaScore = state.ga.scores.get(airport.ident);
    const quartiles = state.ga.computedQuartiles;  // Computed from current scores
    const buckets = state.ga.config?.relevance_buckets ?? [];
    
    const bucketId = getRelevanceBucket(gaScore?.score ?? null, quartiles);
    const bucket = buckets.find(b => b.id === bucketId) ?? buckets.find(b => b.id === 'unknown');
    return bucket?.color ?? '#95a5a6';
}
```

### 10.5 Validation Strategy

#### 10.5.1 Runtime Validation (TypeScript)

```typescript
// ts/utils/ga-validation.ts

/**
 * Validate API config response matches expected structure
 */
export function validateGAConfig(config: unknown): config is GAConfig {
    if (!config || typeof config !== 'object') return false;
    
    const c = config as Record<string, unknown>;
    
    // Required fields
    if (!Array.isArray(c.feature_names)) return false;
    if (typeof c.feature_display_names !== 'object') return false;
    if (!Array.isArray(c.relevance_buckets)) return false;  // Colors only - no thresholds
    if (!Array.isArray(c.personas)) return false;
    
    // Validate feature consistency
    const featureCount = c.feature_names.length;
    if (Object.keys(c.feature_display_names).length !== featureCount) {
        console.warn('GA Config: feature_display_names count mismatch');
    }
    
    // Validate personas have weights for known features
    for (const persona of c.personas as PersonaWithWeights[]) {
        const weightKeys = Object.keys(persona.weights);
        const unknownWeights = weightKeys.filter(k => !c.feature_names.includes(k));
        if (unknownWeights.length > 0) {
            console.warn(`GA Config: Persona ${persona.id} has unknown weight keys:`, unknownWeights);
        }
    }
    
    return true;
}
```

#### 10.5.2 Python Unit Tests

```python
# tests/ga_friendliness/test_ui_config_consistency.py

import pytest
from shared.ga_friendliness.ui_config import (
    FEATURE_DISPLAY_NAMES,
    FEATURE_DESCRIPTIONS,
    RELEVANCE_BUCKETS,  # Colors only - quartiles computed client-side
)
from shared.ga_friendliness.personas import FEATURE_NAMES
from shared.ga_friendliness.config import get_default_personas

def test_all_features_have_display_names():
    """Every feature in FEATURE_NAMES must have a display name."""
    for feature in FEATURE_NAMES:
        assert feature in FEATURE_DISPLAY_NAMES, f"Missing display name for {feature}"

def test_all_features_have_descriptions():
    """Every feature in FEATURE_NAMES must have a description."""
    for feature in FEATURE_NAMES:
        assert feature in FEATURE_DESCRIPTIONS, f"Missing description for {feature}"

def test_persona_weights_use_valid_features():
    """Persona weights must only reference known features."""
    personas = get_default_personas()
    for persona_id, persona in personas.personas.items():
        for weight_key in persona.weights.model_dump().keys():
            if getattr(persona.weights, weight_key, 0) > 0:
                assert weight_key in FEATURE_NAMES, \
                    f"Persona {persona_id} references unknown feature: {weight_key}"

def test_relevance_buckets_have_required_fields():
    """Relevance buckets should have id, label, and color."""
    for bucket in RELEVANCE_BUCKETS:
        assert "id" in bucket, f"Bucket missing 'id': {bucket}"
        assert "label" in bucket, f"Bucket missing 'label': {bucket}"
        assert "color" in bucket, f"Bucket missing 'color': {bucket}"
        assert bucket["color"].startswith("#"), f"Bucket color should be hex: {bucket}"

def test_relevance_buckets_have_unknown():
    """Relevance buckets should include 'unknown' for missing data."""
    bucket_ids = [b["id"] for b in RELEVANCE_BUCKETS]
    assert "unknown" in bucket_ids, "Must have 'unknown' bucket for missing data"

# Note: Threshold coverage tests not needed - thresholds computed dynamically 
# from quartiles at runtime (frontend computes from actual score distribution)
```

### 10.6 Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                    SOURCE OF TRUTH                               │
│  shared/ga_friendliness/                                        │
│  ├── personas.py      → FEATURE_NAMES                           │
│  ├── config.py        → DEFAULT_PERSONAS (weights)              │
│  └── ui_config.py     → Display names, descriptions, bucket colors │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ import
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND API                                   │
│  web/server/api/ga_friendliness.py                              │
│  └── GET /api/ga/config → Returns all config as JSON            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ fetch on startup
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND (TypeScript)                         │
│  ts/store/store.ts                                              │
│  └── ga.config: GAConfig   → Cached config from API             │
│                                                                  │
│  No hardcoded values! All UI logic reads from ga.config         │
└─────────────────────────────────────────────────────────────────┘
```

### 10.7 Design Rules

1. **Never hardcode in TypeScript** - All feature names, weights, bucket colors come from API
2. **API imports, never duplicates** - Backend always imports from `shared/ga_friendliness`
3. **Single config endpoint** - `/api/ga/config` returns everything UI needs
4. **Fail gracefully** - If config load fails, disable GA features entirely
5. **Version tracking** - Config includes version string for cache busting
6. **Test consistency** - Unit tests verify all definitions are complete and consistent
7. **Dynamic quartiles** - Bucket thresholds computed client-side from actual score distribution

---

## 11. Scoring Architecture Analysis & Flexibility

This section analyzes the current scoring mechanism and proposes enhancements for experimentation.

### 11.1 Current Architecture

**Two-Stage Scoring Pipeline:**

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Stage 1: Feature Score Computation (features.py::FeatureMapper)         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Review Labels     ───► Label-to-Score     ───► Feature Combination     │
│  (distributions)        Mapping                  Formulas                │
│                                                                          │
│  {"cost": {"cheap": 3,  {"cheap": 1.0,     ga_hospitality_score =       │
│            "expensive": 1}}  "expensive": 0.2}   0.6 * restaurant +      │
│                                                   0.4 * accommodation    │
│                                                                          │
│  Output: 8 normalized feature scores [0, 1]                              │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Stage 2: Persona Scoring (personas.py::PersonaManager)                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Feature Scores    ───► Weighted Average   ───► Final Score             │
│  + Persona Weights      (with missing                                    │
│                          handling)                                       │
│                                                                          │
│  score = Σ(weight_i × feature_i) / Σ(active_weights)                    │
│                                                                          │
│  Output: Single persona score [0, 1]                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

### 11.2 Current Flexibility Points

| Component | Flexibility | How |
|-----------|-------------|-----|
| Label → Score mapping | ✅ Configurable | `FeatureMappingsConfig` in JSON |
| Persona weights | ✅ Configurable | `personas.json` |
| Missing value behavior | ✅ Per-feature per-persona | `MissingBehavior` enum |
| Score explanation | ✅ Built-in | `PersonaManager.explain_score()` |

### 11.3 Current Limitations (Hardcoded)

| Component | Limitation | Location |
|-----------|------------|----------|
| Feature combination formulas | Hardcoded ratios | `FeatureMapper.map_hospitality_score()` uses 0.6/0.4 |
| Hassle score combination | Hardcoded 70/30 review/AIP split | `map_hassle_score()` |
| IFR score base values | Hardcoded 0.1/0.8 | `map_ops_ifr_score()` |
| Scoring formula | Only weighted average | `PersonaManager.compute_score()` |
| No non-linear transforms | Can't do thresholds, curves | Entire pipeline is linear |
| No feature interactions | Can't bonus IFR + Night | No interaction terms |
| No penalty factors | Can't penalize mandatory handling | Not implemented |

### 11.4 Experimentation Needs

For effective experimentation, we need:

1. **Configurable Feature Combination Weights** - Don't hardcode 0.6/0.4
2. **Non-linear Scoring Functions** - Thresholds, sigmoids, step functions
3. **Bonus/Penalty Rules** - Conditional modifiers
4. **Multi-source Integration** - AIP data, fees, runway length
5. **A/B Testing** - Multiple scoring versions simultaneously
6. **Score Versioning** - Track which formula produced which score

### 11.5 Proposed: Enhanced Scoring Configuration

**New: `scoring_config.json`**

```json
{
  "version": "2.0",
  "feature_computation": {
    "ga_hospitality_score": {
      "type": "weighted_combination",
      "sources": {
        "restaurant": {"aspect": "restaurant", "weight": 0.6},
        "accommodation": {"aspect": "accommodation", "weight": 0.4}
      }
    },
    "ga_hassle_score": {
      "type": "weighted_combination",
      "sources": {
        "bureaucracy": {"aspect": "bureaucracy", "weight": 0.7},
        "notification": {"source": "aip_notification_score", "weight": 0.3}
      }
    },
    "ga_ops_ifr_score": {
      "type": "conditional",
      "base": {
        "condition": "ifr_procedure_available == false",
        "value": 0.1
      },
      "else": {
        "type": "weighted_combination",
        "sources": {
          "base": {"value": 0.8, "weight": 0.7},
          "runway": {"aspect": "runway", "weight": 0.3}
        }
      }
    }
  },
  "persona_scoring": {
    "type": "weighted_average",
    "normalization": "active_weights"
  },
  "modifiers": {
    "mandatory_handling_penalty": {
      "condition": "mandatory_handling == true",
      "effect": {"multiply": 0.8}
    },
    "night_ifr_bonus": {
      "condition": "night_available == true AND ifr_procedure_available == true",
      "effect": {"add_to": "ga_ops_ifr_score", "value": 0.1}
    }
  }
}
```

### 11.6 Proposed: Pluggable Scoring Functions

```python
# shared/ga_friendliness/scoring.py

from abc import ABC, abstractmethod
from typing import Dict, Optional
from .models import AirportFeatureScores, PersonaConfig

class ScoringFunction(ABC):
    """Base class for persona scoring functions."""
    
    @abstractmethod
    def compute(
        self,
        features: AirportFeatureScores,
        persona: PersonaConfig,
    ) -> float:
        """Compute persona score from features."""
        pass

class WeightedAverageScoring(ScoringFunction):
    """Current default: simple weighted average."""
    
    def compute(self, features, persona):
        # Current implementation
        ...

class ThresholdBoostScoring(ScoringFunction):
    """Weighted average with threshold boosts."""
    
    def __init__(self, thresholds: Dict[str, float], boost: float = 0.1):
        self.thresholds = thresholds  # {"ga_ops_ifr_score": 0.8}
        self.boost = boost
    
    def compute(self, features, persona):
        base_score = weighted_average(features, persona)
        
        # Add boost for features exceeding thresholds
        for feature, threshold in self.thresholds.items():
            value = getattr(features, feature, None)
            if value and value >= threshold:
                base_score += self.boost
        
        return min(1.0, base_score)

class GeometricMeanScoring(ScoringFunction):
    """Geometric mean - penalizes low scores more heavily."""
    
    def compute(self, features, persona):
        # Product of features^weight, then nth root
        ...

# Registry for A/B testing
SCORING_FUNCTIONS = {
    "weighted_average_v1": WeightedAverageScoring(),
    "threshold_boost_v1": ThresholdBoostScoring({"ga_ops_ifr_score": 0.8}),
    "geometric_v1": GeometricMeanScoring(),
}
```

### 11.7 Proposed: Scoring Context for External Data

```python
# shared/ga_friendliness/models.py

class ScoringContext(BaseModel):
    """
    Additional context for scoring beyond review-derived features.
    
    Allows incorporating AIP data, fees, runway info, etc.
    """
    icao: str
    
    # AIP-derived data
    ifr_procedure_available: bool = False
    ifr_score: int = 0  # 0-4 scale
    night_available: bool = False
    mandatory_handling: bool = False
    
    # Fee data
    landing_fee_eur: Optional[float] = None  # Normalized to EUR
    handling_fee_eur: Optional[float] = None
    
    # Runway data
    longest_runway_ft: Optional[int] = None
    has_hard_runway: bool = False
    
    # Review metadata
    review_count: int = 0
    last_review_date: Optional[str] = None
    
    # External ratings
    airfield_directory_rating: Optional[float] = None

# Updated PersonaManager
class PersonaManager:
    def compute_score(
        self,
        persona_id: str,
        features: AirportFeatureScores,
        context: Optional[ScoringContext] = None,  # NEW
        scoring_function: Optional[str] = None,    # NEW
    ) -> Optional[float]:
        """
        Compute score with optional context and custom scoring function.
        """
        func = SCORING_FUNCTIONS.get(scoring_function, self.default_scoring)
        return func.compute(features, persona, context)
```

### 11.8 API Support for Scoring Experiments

```python
# GET /api/ga/scores?icaos=EGKB&persona=ifr_touring&scoring=threshold_boost_v1
# Allows frontend to test different scoring functions

# GET /api/ga/scores?icaos=EGKB&persona=ifr_touring&explain=true
# Returns full explanation with context
{
  "EGKB": {
    "score": 0.75,
    "scoring_function": "weighted_average_v1",
    "explanation": {
      "features": {
        "ga_cost_score": {"value": 0.6, "weight": 0.2, "contribution": 0.12},
        ...
      },
      "context_applied": {
        "mandatory_handling_penalty": false,
        "night_ifr_bonus": true
      },
      "final_calculation": "0.72 + 0.03 (night_ifr_bonus) = 0.75"
    }
  }
}
```

### 11.9 Migration Path

**✅ Phase 1 (DECIDED - Ship Now):** Use existing hardcoded formulas
- Ship with current implementation
- Gather real usage data
- Track `scoring_version: "v1"` in all responses

**Phase 2 (Future):** Extract hardcoded values to config
- Create `scoring_config.json`
- Make feature combination weights configurable
- No code changes needed to experiment
- Backward compatible: same scores if same config

**Phase 3 (Future):** Add pluggable scoring functions
- Implement `ScoringFunction` interface
- Add A/B testing support via `?scoring=` parameter
- Track which function produced each score

**Phase 4 (Future):** Support learned weights
- Store user feedback (helpful/not helpful)
- Train weights from feedback
- A/B test learned vs. manual weights

### 11.10 What Can Be Changed Without Code (Today)

Even with current hardcoded formulas, these are already configurable:

| Change | How | Rebuild Required? |
|--------|-----|-------------------|
| Persona weights | Edit `personas.json` or `DEFAULT_PERSONAS` | Yes (rebuild ga_meta.db) |
| Add new persona | Add to `personas.json` | Yes |
| Label scores (e.g., "cheap" → 0.9 instead of 1.0) | Edit `DEFAULT_LABEL_SCORES` in features.py | Yes |
| Missing value behavior | Edit persona's `missing_behaviors` | Yes |
| Relevance bucket thresholds | Edit `ui_config.py` | No (API config only) |
| Display names/descriptions | Edit `ui_config.py` | No |

### 11.11 What Requires Code Changes (Future)

| Change | Code Location | Complexity |
|--------|---------------|------------|
| Feature combination ratios (0.6/0.4) | `features.py` map_* methods | Low |
| Add new input to scoring (e.g., runway length) | `FeatureMapper` + `ScoringContext` | Medium |
| Non-linear transforms | New scoring function | Medium |
| Conditional bonuses/penalties | New modifier system | Medium |

### 11.12 Extension Example: Adding Runway Length to Scoring

When we want to incorporate runway length into VFR ops score:

```python
# Current (hardcoded)
def map_ops_vfr_score(self, runway_dist, traffic_dist):
    return 0.6 * runway_score + 0.4 * traffic_score

# Future (with ScoringContext)
def map_ops_vfr_score(self, runway_dist, traffic_dist, context: ScoringContext):
    base = 0.6 * runway_score + 0.4 * traffic_score
    
    # Bonus for long runways
    if context and context.longest_runway_ft:
        if context.longest_runway_ft >= 2000:
            base += 0.1
        elif context.longest_runway_ft >= 1500:
            base += 0.05
    
    return min(1.0, base)
```

The key insight: **current architecture accepts this extension cleanly** because:
1. `AirportFeatureScores` is a Pydantic model - easy to add fields
2. `PersonaManager.compute_score()` iterates over `FEATURE_NAMES` - add to list
3. Feature combination happens in isolated methods - change one method
4. API returns whatever `ga_meta.db` contains - no frontend changes needed

### 11.13 Future Enhancement Priorities

| Priority | Change | Effort | Impact |
|----------|--------|--------|--------|
| **Deferred** | Extract feature combination weights to config | Low | Easy experimentation |
| **Deferred** | Add `ScoringContext` for external data | Medium | Richer scoring inputs |
| **Deferred** | Pluggable scoring functions | Medium | A/B testing |
| **Deferred** | Bonus/penalty rules in config | Medium | Conditional modifiers |
| **Low** | Non-linear transforms | High | Diminishing returns |
| **Low** | ML-based weights | High | Requires feedback data |

### 11.14 Immediate Actions (for V1 Ship)

✅ **Decision: Ship with current hardcoded formulas**

For the UI integration, we will:

1. **Use current implementation** - It works, ship it
2. **Include `scoring_version: "v1"` in API responses** - Track for future comparison
3. **Add `explain=true` option to API** - Transparency aids debugging
4. **Document current formulas** - So we know what V1 produces

The architecture is **designed for extension** - we can:
- Change persona weights anytime (rebuild DB)
- Extract hardcoded ratios to config later
- Add new inputs (runway length, fees) without breaking existing scores
- A/B test new scoring functions alongside V1

---

## 12. Additional Design Considerations

### 12.1 Relevance Score vs. Bucket Granularity

**Decision:** Show both - buckets on map (quartile colors), raw score in detail view.

| Approach | Pros | Cons |
|----------|------|------|
| Raw scores | Precise comparison, familiar (like ratings) | Over-precision may be misleading given data quality |
| Buckets only | Simple, appropriate uncertainty | Less differentiation between airports |
| **Both** ✅ | Best of both worlds | Minor UI complexity |

### 12.2 Score Composition Transparency

**Decision:** Full breakdown in "Relevance" tab - show feature scores + weights + data sources.

Transparency builds trust. Users can see exactly why an airport scored high/low.

### 12.3 Handling Sparse Data

**Decision:** Always show review count - "Based on 12 reviews".

Simple transparency without blocking score display. Bayesian smoothing (already in library) handles statistical reliability.

### 12.4 Persona Weight Visibility

**Decision:** Show relative importance through visual emphasis (bold/accent for weighted features), not numeric weights.

Users don't need to see "Cost: 20%" - they can see which features matter by visual emphasis.

### 12.5 Cross-Persona Comparison

**Decision:** Show only selected persona for V1.

Future enhancement: Add "Best for: Lunch stop" indicator.

### 12.6 Score Update Frequency

**Decision:** Precomputed scores at build time, stored in `ga_meta.db`.

Runtime computation deferred to future if custom personas are needed.

---

## 13. Implementation Phases

### Phase 1: Backend Foundation
- [ ] Create `shared/ga_friendliness/ui_config.py` (display names, descriptions, bucket colors)
- [ ] Add unit tests for config consistency (`test_ui_config_consistency.py`)
- [ ] Add `GA_META_DB` to `security_config.py`
- [ ] Create `GAFriendlinessService` class (imports from library)
- [ ] Add `/api/ga/config` endpoint (returns all UI config)
- [ ] Add `/api/ga/personas` endpoint
- [ ] Add `/api/ga/scores` endpoint  
- [ ] Add `/api/ga/summary/{icao}` endpoint
- [ ] Graceful degradation when DB missing

### Phase 2: Store & Types
- [ ] Add TypeScript types (`GAConfig`, `Persona`, `GAFeatureScores`, `AirportGAScore`, `AirportGASummary`, `GAState`)
- [ ] Add GA state to Zustand store (including `config`, `computedQuartiles`)
- [ ] Add GA actions (`setGAConfig`, `setSelectedPersona`, `setGAScores`, `setGASummary`, `clearGAScoreCache`)
- [ ] Add `computeQuartileThresholds()` utility function
- [ ] Add API adapter methods (`getGAConfig`, `getGAScores`, `getGASummary`)
- [ ] Add `validateGAConfig()` runtime validation utility
- [ ] Load config on app startup (before persona selector init)

### Phase 3: Persona Selector
- [ ] Create `PersonaManager` class
- [ ] Add persona dropdown UI
- [ ] Implement localStorage persistence
- [ ] Load personas on app init
- [ ] Subscribe to persona changes

### Phase 4: "Relevance" Legend Mode
- [ ] Add `relevance` to `LegendMode` type
- [ ] Implement dynamic quartile bucket calculation
- [ ] Add relevance color mapping (from config)
- [ ] Create legend panel for relevance mode
- [ ] Trigger GA score loading when mode selected
- [ ] Show all markers gray until scores loaded

### Phase 5: "Relevance" Tab
- [ ] Add tab to detail panel (last position)
- [ ] Implement feature breakdown UI with review count
- [ ] Score explanation generation
- [ ] Tags and summary display
- [ ] No-data state handling

### Phase 6: Integration & Polish
- [ ] Route search GA scores integration
- [ ] Performance optimization (batching, caching)
- [ ] Loading states and error handling
- [ ] E2E testing

---

## 14. Data Loading Strategy

### 14.1 When to Load GA Scores

| Trigger | Action | Airports |
|---------|--------|----------|
| App init | Load personas | N/A |
| Select "Relevance" legend mode | Batch load scores | Visible/filtered airports |
| Open airport detail (any mode) | Load full summary | Single airport |
| Persona change (in relevance mode) | Clear cache + reload | Visible airports |
| Route search complete | Batch load scores | Route result airports |
| Locate search complete | Batch load scores | Located airports |

### 14.2 Loading State Flow

```
User selects "Relevance" legend mode
  │
  ├─► Check: Any airports in view?
  │     ├─► No: Show empty state
  │     └─► Yes: Continue
  │
  ├─► Check: Scores cached for visible airports?
  │     ├─► Yes: Use cached, render immediately
  │     └─► No: Continue
  │
  ├─► Set loading state
  │
  ├─► Batch fetch scores (max 200 ICAOs per request)
  │     └─► For large sets, show progress indicator
  │
  ├─► Store in cache
  │
  ├─► Clear loading state
  │
  └─► Markers update reactively via store subscription
```

### 14.3 Cache Invalidation

```typescript
// Cache is invalidated when:
// 1. Persona changes (scores are persona-specific)
// 2. Manual refresh requested
// 3. TTL expires (optional, default: session-only)

const GA_CACHE_CONFIG = {
  maxScoreEntries: 500,      // LRU eviction above this
  maxSummaryEntries: 50,     // Full summaries are larger
  invalidateOnPersonaChange: true,
  ttl: null                  // null = session-only
};
```

---

## 15. Testing Strategy

### 15.1 Backend Tests
- Unit tests for `GAFriendlinessService`
- API endpoint tests with mock data
- Integration tests with test database
- Graceful degradation when DB missing

### 15.2 Frontend Tests
- Store action tests
- PersonaManager unit tests
- Relevance bucket calculation tests
- Component render tests (Relevance tab)
- E2E tests for persona selection flow

### 15.3 Test Data
- Create test `ga_meta_test.sqlite` with sample data
- Include edge cases:
  - Airports with full data
  - Airports with partial data (some features null)
  - Airports with no GA data
  - Airports with low review count

---

## 16. Migration & Rollout

### 16.1 Feature Flag

Backend (Python):
```python
GA_FRIENDLINESS_ENABLED = os.getenv("GA_FRIENDLINESS_ENABLED", "true").lower() == "true"
```

Frontend (TypeScript):
```typescript
const GA_FRIENDLINESS_ENABLED = import.meta.env.VITE_GA_FRIENDLINESS_ENABLED !== 'false';
```

### 16.2 Backward Compatibility

- All GA features are additive
- Existing functionality works without GA data
- API endpoints return empty/null gracefully
- "Relevance" legend mode shows all airports as "Unknown" if no data
- "Relevance" tab shows "No data" message gracefully

### 16.3 Rollout Steps

1. Deploy backend with GA endpoints (behind feature flag)
2. Deploy frontend with GA UI (behind feature flag)
3. Enable feature flag in dev/staging
4. Test with real ga_meta.db
5. Enable in production

---

## 17. Future Considerations (Out of Scope)

### 17.1 Chatbot Integration
- Allow LLM to reference GA scores in responses
- Support persona specification in chat queries
- Include GA context in visualizations
- **Status:** Deferred to later phase

### 17.2 Custom Personas
- Allow users to define custom weight profiles
- Store in localStorage or user account
- **Status:** Future enhancement

### 17.3 Score Filtering
- Filter airports by minimum relevance score
- "Show only Most Relevant" toggle
- **Status:** Future enhancement

### 17.4 Comparison View
- Compare GA scores across multiple airports
- Side-by-side feature breakdown
- **Status:** Future enhancement

---

## 18. Resolved Design Decisions Summary

| Item | Decision | Rationale |
|------|----------|-----------|
| **Bucket thresholds** | ✅ Dynamic quartiles | Adapts to any scoring formula/persona; always produces balanced buckets |
| **Feature display names** | ✅ Keep current (higher = better) | Consistent direction for all features |
| **Tab ordering** | ✅ "Relevance" tab last | Less disruptive; can reorder later based on usage |
| **Empty state (relevance mode)** | ✅ Show all markers gray ("Unknown") | Consistent with unknown bucket; clear feedback |
| **Score confidence** | ✅ Always show review count | Simple transparency: "Based on 12 reviews" |

---

*Document created: 2025-11-27*
*Last updated: 2025-11-27*
*Status: Design Complete*
*Related: GA_FRIENDLINESS_DESIGN.md, UI_FILTER_STATE_DESIGN.md*

