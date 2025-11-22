# Development Setup

## Quick Start

### Option 1: Vite Dev Server (Recommended for Development)

1. **Start dev server**:
   ```bash
   cd web/client
   npm run dev
   ```

2. **Open browser**: `http://localhost:3000`

3. **Changes**: Vite will hot-reload automatically when you edit TypeScript files

### Option 2: Production Build

1. **Build**:
   ```bash
   cd web/client
   npm run build
   ```

2. **Preview**:
   ```bash
   npm run preview
   ```

3. **Or serve manually**: Serve `web/client/` directory with any static file server

## Important Notes

### Development Mode

- **HTML uses**: `<script type="module" src="/ts/main.ts"></script>`
- **Vite serves**: TypeScript files directly with hot-reload
- **No build needed**: Changes are reflected immediately

### Production Mode

- **HTML uses**: `<script src="dist/main.iife.js"></script>`
- **Requires build**: Must run `npm run build` first
- **No hot-reload**: Need to rebuild after changes

## Current HTML Configuration

The HTML file is currently set to use **Vite dev mode** (`<script type="module" src="/ts/main.ts"></script>`).

For production builds, change it back to:
```html
<script src="dist/main.iife.js?v=1.0"></script>
```

## Troubleshooting

### "Map container not found"
- Check that HTML has `<div id="map"></div>`

### "Leaflet library not loaded"
- Check that Leaflet CDN script is included before the app script
- Check browser Network tab for failed CDN requests

### Changes not reflecting
- **Dev mode**: Check Vite console for errors, refresh browser
- **Production mode**: Rebuild with `npm run build`

