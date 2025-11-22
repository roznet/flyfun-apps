# TypeScript Architecture Implementation

## Setup Instructions

### 1. Install Dependencies

```bash
cd web/client
npm install
```

This will install:
- TypeScript
- Zustand (state management)
- Vite (build tool)
- Leaflet types
- ESLint

### 2. Type Checking

```bash
npm run type-check
```

### 3. Development

```bash
npm run dev
```

This starts Vite dev server with hot reload.

### 4. Build

```bash
npm run build
```

## Project Structure

```
ts/
├── store/
│   ├── types.ts              # TypeScript interfaces
│   └── store.ts              # Zustand store
├── engines/
│   ├── filter-engine.ts      # Filter logic (TODO)
│   └── visualization-engine.ts # Map rendering
├── adapters/
│   ├── api-adapter.ts        # API client (Fetch)
│   └── llm-integration.ts    # Chatbot integration (TODO)
├── managers/
│   └── ui-manager.ts         # DOM updates (TODO)
├── utils/
│   ├── legend-modes.ts       # Legend mode logic (TODO)
│   └── url-sync.ts           # URL persistence (TODO)
└── main.ts                   # Application entry point (TODO)
```

## Current Status

✅ **Completed**:
- TypeScript configuration
- Zustand store with types
- API adapter (Fetch-based)
- Visualization engine skeleton
- Package.json with dependencies
- Vite configuration

🚧 **In Progress**:
- Visualization engine implementation

⏳ **TODO**:
- Filter engine wrapper (integrate Python FilterEngine)
- UI manager (reactive DOM updates)
- LLM integration (chatbot interface)
- Main application entry point
- URL sync utility
- Legend mode utilities

## Integration Points

### Python FilterEngine Integration

The existing `shared/filtering/FilterEngine` is in Python. We need to:

1. **Option A**: Call Python FilterEngine via API endpoint
   - Create `/api/filter` endpoint in Python
   - Send airports + filters, get filtered airports back
   - Simple but requires API call

2. **Option B**: Port FilterEngine to TypeScript
   - Rewrite filter logic in TypeScript
   - More work but no API dependency
   - Better performance

**Recommendation**: Start with Option A (API endpoint), port to TypeScript later if needed.

## Next Steps

1. Complete visualization engine
2. Create UI manager
3. Create main.ts entry point
4. Integrate with existing HTML
5. Test end-to-end
6. Remove old JavaScript files

## Notes

- **No backward compatibility needed** - Big bang migration
- **Python API unchanged** - Only frontend changes
- **LangChain agent unchanged** - Only frontend changes

