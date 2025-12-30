import SwiftUI
import MapKit
import RZFlight

/// A map view that supports offline tiles via MKTileOverlay
/// Uses UIViewRepresentable since SwiftUI Map doesn't support overlays
struct OfflineMapView: UIViewRepresentable {
    @Binding var region: MKCoordinateRegion
    var airports: [RZFlight.Airport]
    var selectedAirport: RZFlight.Airport?
    var onAirportSelected: ((RZFlight.Airport) -> Void)?
    var onRegionChange: ((MKCoordinateRegion) -> Void)?  // Callback when map region changes
    var useOfflineTiles: Bool
    var legendMode: LegendMode = .airportType
    var borderCrossingAirports: Set<String> = []
    var activeRoute: RouteVisualization?
    var highlights: [String: MapHighlight] = [:]
    
    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        mapView.showsUserLocation = true
        mapView.showsCompass = true
        mapView.showsScale = true
        
        // Add offline tile overlay if enabled (use aboveRoads so route overlays show on top)
        if useOfflineTiles {
            let tileOverlay = CachedTileOverlay(urlTemplate: nil)
            tileOverlay.offlineOnly = !isNetworkAvailable()
            mapView.addOverlay(tileOverlay, level: .aboveRoads)
        }
        
        return mapView
    }
    
    func updateUIView(_ mapView: MKMapView, context: Context) {
        // Update region if changed significantly
        let currentCenter = mapView.region.center
        let newCenter = region.center
        let distance = CLLocation(latitude: currentCenter.latitude, longitude: currentCenter.longitude)
            .distance(from: CLLocation(latitude: newCenter.latitude, longitude: newCenter.longitude))
        
        if distance > 1000 { // More than 1km difference
            mapView.setRegion(region, animated: true)
        }
        
        // Update annotations
        updateAnnotations(mapView)
        
        // Update overlays (route + highlights)
        updateOverlays(mapView)
        print("[OfflineMapView] updateUIView - route: \(activeRoute != nil ? "YES (\(activeRoute!.coordinates.count) coords)" : "nil"), highlights: \(highlights.count)")
        
        // Update tile overlay offline status
        if let overlay = mapView.overlays.first(where: { $0 is CachedTileOverlay }) as? CachedTileOverlay {
            overlay.offlineOnly = useOfflineTiles && !isNetworkAvailable()
        }
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }
    
    private func updateAnnotations(_ mapView: MKMapView) {
        // Remove annotations not in current list
        let existingICaos = Set(mapView.annotations.compactMap { ($0 as? AirportAnnotation)?.icao })
        let newIcaos = Set(airports.map(\.icao))
        
        for annotation in mapView.annotations {
            if let airportAnnotation = annotation as? AirportAnnotation,
               !newIcaos.contains(airportAnnotation.icao) {
                mapView.removeAnnotation(annotation)
            }
        }
        
        // Add new annotations
        for airport in airports {
            if !existingICaos.contains(airport.icao) {
                let annotation = AirportAnnotation(airport: airport)
                mapView.addAnnotation(annotation)
            }
        }
    }
    
    /// Update route polyline and highlight circle overlays
    private func updateOverlays(_ mapView: MKMapView) {
        // Remove old route and highlight overlays (but keep tile overlay)
        let overlaysToRemove = mapView.overlays.filter { !($0 is CachedTileOverlay) }
        mapView.removeOverlays(overlaysToRemove)
        
        // Add route polyline if active - use level above roads so it's visible
        if let route = activeRoute, route.coordinates.count >= 2 {
            let polyline = MKPolyline(coordinates: route.coordinates, count: route.coordinates.count)
            mapView.addOverlay(polyline, level: .aboveRoads)
            print("[OfflineMapView] Added route polyline with \(route.coordinates.count) coords")
        }
        
        // Add highlight circles
        for highlight in highlights.values {
            let circle = MKCircle(center: highlight.coordinate, radius: highlight.radius)
            circle.title = highlight.id // Use title to identify the highlight for color
            mapView.addOverlay(circle, level: .aboveRoads)
        }
        
        if !highlights.isEmpty {
            print("[OfflineMapView] Added \(highlights.count) highlight circles")
        }
    }
    
    private func isNetworkAvailable() -> Bool {
        // For now, assume network is available unless explicitly offline
        return !useOfflineTiles
    }
    
    class Coordinator: NSObject, MKMapViewDelegate {
        var parent: OfflineMapView
        
        init(_ parent: OfflineMapView) {
            self.parent = parent
        }
        
        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let tileOverlay = overlay as? CachedTileOverlay {
                return MKTileOverlayRenderer(tileOverlay: tileOverlay)
            }
            
            // Route polyline
            if let polyline = overlay as? MKPolyline {
                let renderer = MKPolylineRenderer(polyline: polyline)
                renderer.strokeColor = UIColor.systemBlue.withAlphaComponent(0.8)
                renderer.lineWidth = 4
                return renderer
            }
            
            // Highlight circle
            if let circle = overlay as? MKCircle {
                let renderer = MKCircleRenderer(circle: circle)
                // Get color from highlight if we can identify it
                let color = colorForHighlight(circle.title)
                renderer.fillColor = color.withAlphaComponent(0.2)
                renderer.strokeColor = color
                renderer.lineWidth = 2
                return renderer
            }
            
            return MKOverlayRenderer(overlay: overlay)
        }
        
        private func colorForHighlight(_ id: String?) -> UIColor {
            guard let id = id,
                  let highlight = parent.highlights[id] else {
                return .blue
            }
            switch highlight.color {
            case .blue: return .systemBlue
            case .red: return .systemRed
            case .green: return .systemGreen
            case .orange: return .systemOrange
            case .purple: return .systemPurple
            }
        }
        
        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard let airportAnnotation = annotation as? AirportAnnotation else {
                return nil
            }
            
            // Use custom colored dot view (like online SwiftUI Map) instead of balloon markers
            let identifier = "airportDot"
            var annotationView = mapView.dequeueReusableAnnotationView(withIdentifier: identifier)
            
            if annotationView == nil {
                annotationView = MKAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                annotationView?.canShowCallout = true
            } else {
                annotationView?.annotation = annotation
            }
            
            // Create colored circle image
            let color = markerColor(for: airportAnnotation.airport)
            let size: CGFloat = 16  // Larger dot to match online version
            annotationView?.image = createCircleImage(size: size, color: color)
            annotationView?.centerOffset = CGPoint(x: 0, y: 0)
            annotationView?.displayPriority = .required
            
            return annotationView
        }
        
        /// Create a colored circle image for airport dot marker
        private func createCircleImage(size: CGFloat, color: UIColor) -> UIImage {
            let renderer = UIGraphicsImageRenderer(size: CGSize(width: size, height: size))
            return renderer.image { context in
                // Draw filled circle
                color.setFill()
                context.cgContext.fillEllipse(in: CGRect(x: 0, y: 0, width: size, height: size))
                
                // Draw border
                UIColor.white.setStroke()
                context.cgContext.setLineWidth(1.5)
                context.cgContext.strokeEllipse(in: CGRect(x: 0.75, y: 0.75, width: size - 1.5, height: size - 1.5))
            }
        }
        
        func mapView(_ mapView: MKMapView, didSelect annotation: MKAnnotation) {
            if let airportAnnotation = annotation as? AirportAnnotation {
                parent.onAirportSelected?(airportAnnotation.airport)
            }
        }
        
        func mapView(_ mapView: MKMapView, regionDidChangeAnimated animated: Bool) {
            parent.region = mapView.region
            // Notify parent to load airports for new region (like online map's onMapCameraChange)
            parent.onRegionChange?(mapView.region)
        }
        
        /// Match the online map legend colors
        private func markerColor(for airport: RZFlight.Airport) -> UIColor {
            let isBorderCrossing = parent.borderCrossingAirports.contains(airport.icao)
            
            switch parent.legendMode {
            case .airportType:
                if isBorderCrossing {
                    return UIColor(red: 0.157, green: 0.655, blue: 0.271, alpha: 1.0) // #28a745 Green
                }
                if airport.hasInstrumentProcedures {
                    return UIColor(red: 1.0, green: 0.757, blue: 0.027, alpha: 1.0) // #ffc107 Yellow
                }
                return UIColor(red: 0.863, green: 0.208, blue: 0.271, alpha: 1.0) // #dc3545 Red
                
            case .runwayLength:
                let maxLength = airport.runways.map(\.length_ft).max() ?? 0
                if maxLength > 8000 {
                    return UIColor(red: 0.157, green: 0.655, blue: 0.271, alpha: 1.0) // Green
                }
                if maxLength > 4000 {
                    return UIColor(red: 1.0, green: 0.757, blue: 0.027, alpha: 1.0) // Yellow
                }
                return UIColor(red: 0.863, green: 0.208, blue: 0.271, alpha: 1.0) // Red
                
            case .procedures:
                if airport.procedures.isEmpty {
                    return .gray
                }
                let hasPrecision = airport.procedures.contains { $0.precisionCategory == .precision }
                let hasRNAV = airport.procedures.contains { $0.precisionCategory == .rnav }
                if hasPrecision {
                    return UIColor(red: 1.0, green: 1.0, blue: 0.0, alpha: 1.0) // Yellow for ILS
                }
                if hasRNAV {
                    return UIColor(red: 0.0, green: 0.5, blue: 1.0, alpha: 1.0) // Blue for RNAV
                }
                return .orange // Non-precision
                
            case .country:
                let hash = abs(airport.country.hashValue)
                let colors: [UIColor] = [.blue, .systemGreen, .orange, .purple, .systemPink,
                                         .cyan, .systemMint, .systemIndigo, .systemTeal, .brown]
                return colors[hash % colors.count]
            }
        }
    }
}

/// Custom annotation for airports
class AirportAnnotation: NSObject, MKAnnotation {
    let airport: RZFlight.Airport
    
    var coordinate: CLLocationCoordinate2D {
        airport.coord
    }
    
    var title: String? {
        airport.icao
    }
    
    var subtitle: String? {
        airport.name
    }
    
    var icao: String {
        airport.icao
    }
    
    init(airport: RZFlight.Airport) {
        self.airport = airport
    }
}
