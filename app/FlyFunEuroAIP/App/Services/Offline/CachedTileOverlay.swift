import Foundation
import MapKit

/// Custom tile overlay that uses cached tiles for offline mode
class CachedTileOverlay: MKTileOverlay {
    
    /// Whether to use only cached tiles (offline mode)
    var offlineOnly: Bool = false
    
    /// Reference to tile manager
    private let tileManager = OfflineTileManager.shared
    
    override init(urlTemplate: String?) {
        super.init(urlTemplate: urlTemplate ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
        self.canReplaceMapContent = true
        self.minimumZ = 1
        self.maximumZ = 19
    }
    
    override func url(forTilePath path: MKTileOverlayPath) -> URL {
        let urlString = "https://tile.openstreetmap.org/\(path.z)/\(path.x)/\(path.y).png"
        return URL(string: urlString)!
    }
    
    override func loadTile(at path: MKTileOverlayPath, result: @escaping (Data?, Error?) -> Void) {
        // First check cache
        if let cachedData = tileManager.getTileData(z: path.z, x: path.x, y: path.y) {
            result(cachedData, nil)
            return
        }
        
        // If offline only, return error for missing tiles
        if offlineOnly {
            result(nil, NSError(domain: "OfflineMap", code: 404, userInfo: [NSLocalizedDescriptionKey: "Tile not cached"]))
            return
        }
        
        // Otherwise fetch from network and cache
        Task {
            do {
                let url = self.url(forTilePath: path)
                var request = URLRequest(url: url)
                request.setValue("FlyFun EuroAIP iOS App", forHTTPHeaderField: "User-Agent")
                
                let (data, response) = try await URLSession.shared.data(for: request)
                
                guard let httpResponse = response as? HTTPURLResponse,
                      httpResponse.statusCode == 200 else {
                    await MainActor.run {
                        result(nil, NSError(domain: "TileError", code: 500, userInfo: nil))
                    }
                    return
                }
                
                // Cache the tile for future offline use
                await MainActor.run {
                    self.saveTileToCache(data: data, path: path)
                    result(data, nil)
                }
            } catch {
                await MainActor.run {
                    result(nil, error)
                }
            }
        }
    }
    
    private func saveTileToCache(data: Data, path: MKTileOverlayPath) {
        let tilesDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
            .appendingPathComponent("tiles")
            .appendingPathComponent("\(path.z)")
            .appendingPathComponent("\(path.x)")
        
        try? FileManager.default.createDirectory(at: tilesDir, withIntermediateDirectories: true)
        
        let tilePath = tilesDir.appendingPathComponent("\(path.y).png")
        try? data.write(to: tilePath)
    }
}

/// Renderer for the cached tile overlay
class CachedTileOverlayRenderer: MKTileOverlayRenderer {
    // Uses default implementation
}
