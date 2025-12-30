import SwiftUI

/// View for managing offline map downloads
struct OfflineMapsView: View {
    @StateObject private var tileManager = OfflineTileManager.shared
    @State private var selectedRegion: MapRegion?
    @State private var showingDeleteConfirmation = false
    
    var body: some View {
        List {
            // Storage section
            Section {
                HStack {
                    Label("Storage Used", systemImage: "internaldrive")
                    Spacer()
                    Text(formatBytes(tileManager.totalStorageBytes))
                        .foregroundStyle(.secondary)
                }
                
                if tileManager.totalStorageBytes > 0 {
                    Button(role: .destructive) {
                        showingDeleteConfirmation = true
                    } label: {
                        Label("Clear All Maps", systemImage: "trash")
                    }
                }
            } header: {
                Text("Storage")
            }
            
            // Download progress
            if tileManager.isDownloading {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        HStack {
                            Text("Downloading...")
                            Spacer()
                            Text("\(Int(tileManager.downloadProgress * 100))%")
                        }
                        ProgressView(value: tileManager.downloadProgress)
                        
                        Button("Cancel") {
                            tileManager.cancelDownload()
                        }
                        .foregroundStyle(.red)
                    }
                } header: {
                    Text("Download Progress")
                }
            }
            
            // Regions section
            Section {
                ForEach(OfflineTileManager.europeanRegions) { region in
                    HStack {
                        VStack(alignment: .leading) {
                            Text(region.name)
                                .font(.headline)
                            Text("~\(region.estimatedStorageMB) MB")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        
                        Spacer()
                        
                        if tileManager.downloadedRegions.contains(region.id) {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(.green)
                        } else {
                            Button {
                                Task {
                                    await tileManager.downloadRegion(region)
                                }
                            } label: {
                                Image(systemName: "arrow.down.circle")
                                    .foregroundStyle(.blue)
                            }
                            .disabled(tileManager.isDownloading)
                        }
                    }
                    .padding(.vertical, 4)
                }
            } header: {
                Text("European Regions")
            } footer: {
                Text("Downloaded maps will be used when offline. Tiles are cached automatically as you browse.")
            }
        }
        .navigationTitle("Offline Maps")
        .confirmationDialog("Clear All Maps?", isPresented: $showingDeleteConfirmation) {
            Button("Clear All", role: .destructive) {
                tileManager.clearAllTiles()
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This will delete all downloaded map tiles. You can re-download them later.")
        }
    }
    
    private func formatBytes(_ bytes: Int64) -> String {
        if bytes < 1024 {
            return "\(bytes) B"
        } else if bytes < 1024 * 1024 {
            return String(format: "%.1f KB", Double(bytes) / 1024)
        } else if bytes < 1024 * 1024 * 1024 {
            return String(format: "%.1f MB", Double(bytes) / 1024 / 1024)
        } else {
            return String(format: "%.2f GB", Double(bytes) / 1024 / 1024 / 1024)
        }
    }
}

#Preview {
    NavigationStack {
        OfflineMapsView()
    }
}
