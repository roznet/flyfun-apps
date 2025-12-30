import Foundation
import MapKit
import Combine
import os
import RZUtilsSwift

/// Manages offline map tile downloading and caching
@MainActor
class OfflineTileManager: ObservableObject {
    static let shared = OfflineTileManager()
    
    /// Download progress (0.0 - 1.0)
    @Published var downloadProgress: Double = 0
    @Published var isDownloading = false
    @Published var downloadedRegions: Set<String> = []
    @Published var totalStorageBytes: Int64 = 0
    
    /// Tile server URL template (OpenStreetMap)
    private let tileServerTemplate = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    
    /// Zoom levels to download (5 = country level, 12 = city streets)
    private let minZoom = 5
    private let maxZoom = 10 // Reduced to 10 for faster downloads, still useful for navigation
    
    /// Predefined European regions
    static let europeanRegions: [MapRegion] = [
        MapRegion(id: "western_europe", name: "Western Europe", 
                  minLat: 42, maxLat: 56, minLon: -10, maxLon: 15),
        MapRegion(id: "central_europe", name: "Central Europe",
                  minLat: 45, maxLat: 55, minLon: 5, maxLon: 25),
        MapRegion(id: "northern_europe", name: "Northern Europe",
                  minLat: 54, maxLat: 72, minLon: 0, maxLon: 32),
        MapRegion(id: "southern_europe", name: "Southern Europe",
                  minLat: 34, maxLat: 46, minLon: -10, maxLon: 30),
        MapRegion(id: "uk_ireland", name: "UK & Ireland",
                  minLat: 49, maxLat: 61, minLon: -11, maxLon: 2),
        MapRegion(id: "germany", name: "Germany",
                  minLat: 47, maxLat: 55, minLon: 5.5, maxLon: 15.5),
        MapRegion(id: "france", name: "France",
                  minLat: 41, maxLat: 51.5, minLon: -5.5, maxLon: 10),
    ]
    
    private let fileManager = FileManager.default
    private var downloadTask: Task<Void, Never>?
    
    private init() {
        loadDownloadedRegions()
        calculateStorageUsed()
    }
    
    /// Base directory for tile cache
    var tilesDirectory: URL {
        let docs = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first!
        return docs.appendingPathComponent("tiles", isDirectory: true)
    }
    
    /// Check if a tile exists in cache
    func tileExists(z: Int, x: Int, y: Int) -> Bool {
        let tilePath = tilesDirectory
            .appendingPathComponent("\(z)")
            .appendingPathComponent("\(x)")
            .appendingPathComponent("\(y).png")
        return fileManager.fileExists(atPath: tilePath.path)
    }
    
    /// Get cached tile data
    func getTileData(z: Int, x: Int, y: Int) -> Data? {
        let tilePath = tilesDirectory
            .appendingPathComponent("\(z)")
            .appendingPathComponent("\(x)")
            .appendingPathComponent("\(y).png")
        return try? Data(contentsOf: tilePath)
    }
    
    /// Download tiles for a region
    func downloadRegion(_ region: MapRegion) async {
        guard !isDownloading else { return }
        
        isDownloading = true
        downloadProgress = 0
        
        Logger.app.info("Starting download for region: \(region.name)")
        
        // Calculate all tiles needed
        var tiles: [(z: Int, x: Int, y: Int)] = []
        for z in minZoom...maxZoom {
            let minX = lonToTileX(region.minLon, zoom: z)
            let maxX = lonToTileX(region.maxLon, zoom: z)
            let minY = latToTileY(region.maxLat, zoom: z) // Note: Y is inverted
            let maxY = latToTileY(region.minLat, zoom: z)
            
            for x in minX...maxX {
                for y in minY...maxY {
                    tiles.append((z, x, y))
                }
            }
        }
        
        Logger.app.info("Total tiles to download: \(tiles.count)")
        
        // Download tiles
        var downloaded = 0
        for (z, x, y) in tiles {
            if Task.isCancelled { break }
            
            // Skip if already cached
            if tileExists(z: z, x: x, y: y) {
                downloaded += 1
                downloadProgress = Double(downloaded) / Double(tiles.count)
                continue
            }
            
            // Download tile
            if let data = await downloadTile(z: z, x: x, y: y) {
                saveTile(data: data, z: z, x: x, y: y)
            }
            
            downloaded += 1
            downloadProgress = Double(downloaded) / Double(tiles.count)
            
            // Small delay to avoid overwhelming the server
            if downloaded % 10 == 0 {
                try? await Task.sleep(nanoseconds: 50_000_000) // 50ms
            }
        }
        
        // Mark region as downloaded
        downloadedRegions.insert(region.id)
        saveDownloadedRegions()
        calculateStorageUsed()
        
        isDownloading = false
        Logger.app.info("Download complete for region: \(region.name)")
    }
    
    /// Cancel ongoing download
    func cancelDownload() {
        downloadTask?.cancel()
        isDownloading = false
    }
    
    /// Delete cached tiles for a region
    func deleteRegion(_ region: MapRegion) {
        // For simplicity, we just remove from the tracked regions
        // Actual tile deletion would require tracking which tiles belong to which region
        downloadedRegions.remove(region.id)
        saveDownloadedRegions()
    }
    
    /// Clear all cached tiles
    func clearAllTiles() {
        try? fileManager.removeItem(at: tilesDirectory)
        downloadedRegions.removeAll()
        saveDownloadedRegions()
        calculateStorageUsed()
    }
    
    // MARK: - Private Methods
    
    private func downloadTile(z: Int, x: Int, y: Int) async -> Data? {
        let urlString = tileServerTemplate
            .replacingOccurrences(of: "{z}", with: "\(z)")
            .replacingOccurrences(of: "{x}", with: "\(x)")
            .replacingOccurrences(of: "{y}", with: "\(y)")
        
        guard let url = URL(string: urlString) else { return nil }
        
        var request = URLRequest(url: url)
        request.setValue("FlyFun EuroAIP iOS App", forHTTPHeaderField: "User-Agent")
        
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                return nil
            }
            return data
        } catch {
            return nil
        }
    }
    
    private func saveTile(data: Data, z: Int, x: Int, y: Int) {
        let tileDir = tilesDirectory
            .appendingPathComponent("\(z)")
            .appendingPathComponent("\(x)")
        
        try? fileManager.createDirectory(at: tileDir, withIntermediateDirectories: true)
        
        let tilePath = tileDir.appendingPathComponent("\(y).png")
        try? data.write(to: tilePath)
    }
    
    private func lonToTileX(_ lon: Double, zoom: Int) -> Int {
        return Int(floor((lon + 180.0) / 360.0 * pow(2.0, Double(zoom))))
    }
    
    private func latToTileY(_ lat: Double, zoom: Int) -> Int {
        let latRad = lat * .pi / 180.0
        return Int(floor((1.0 - log(tan(latRad) + 1.0 / cos(latRad)) / .pi) / 2.0 * pow(2.0, Double(zoom))))
    }
    
    private func loadDownloadedRegions() {
        let path = tilesDirectory.appendingPathComponent("regions.json")
        if let data = try? Data(contentsOf: path),
           let regions = try? JSONDecoder().decode(Set<String>.self, from: data) {
            downloadedRegions = regions
        }
    }
    
    private func saveDownloadedRegions() {
        try? fileManager.createDirectory(at: tilesDirectory, withIntermediateDirectories: true)
        let path = tilesDirectory.appendingPathComponent("regions.json")
        if let data = try? JSONEncoder().encode(downloadedRegions) {
            try? data.write(to: path)
        }
    }
    
    private func calculateStorageUsed() {
        Task {
            var size: Int64 = 0
            if let enumerator = fileManager.enumerator(at: tilesDirectory, includingPropertiesForKeys: [.fileSizeKey]) {
                for case let fileURL as URL in enumerator {
                    if let attrs = try? fileURL.resourceValues(forKeys: [.fileSizeKey]),
                       let fileSize = attrs.fileSize {
                        size += Int64(fileSize)
                    }
                }
            }
            await MainActor.run {
                totalStorageBytes = size
            }
        }
    }
}

/// Represents a downloadable map region
struct MapRegion: Identifiable, Hashable {
    let id: String
    let name: String
    let minLat: Double
    let maxLat: Double
    let minLon: Double
    let maxLon: Double
    
    /// Estimate tile count for this region (for UI display)
    var estimatedTileCount: Int {
        var count = 0
        for z in 5...10 {
            let minX = Int(floor((minLon + 180.0) / 360.0 * pow(2.0, Double(z))))
            let maxX = Int(floor((maxLon + 180.0) / 360.0 * pow(2.0, Double(z))))
            let minY = Int(floor((1.0 - log(tan(maxLat * .pi / 180) + 1.0 / cos(maxLat * .pi / 180)) / .pi) / 2.0 * pow(2.0, Double(z))))
            let maxY = Int(floor((1.0 - log(tan(minLat * .pi / 180) + 1.0 / cos(minLat * .pi / 180)) / .pi) / 2.0 * pow(2.0, Double(z))))
            count += (maxX - minX + 1) * (maxY - minY + 1)
        }
        return count
    }
    
    /// Estimated storage in MB
    var estimatedStorageMB: Int {
        // Average tile size is ~15KB
        return estimatedTileCount * 15 / 1024
    }
}
