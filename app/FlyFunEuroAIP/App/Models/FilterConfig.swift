//
//  FilterConfig.swift
//  FlyFunEuroAIP
//
//  Created by Brice Rosenzweig on 28/11/2025.
//

import Foundation

/// Pure filter configuration for airports
/// NOTE: This is a pure data struct. Filtering logic is in the Repository.
struct FilterConfig: Codable, Equatable, Sendable {
    // MARK: - Geographic Filters
    var country: String?
    
    // MARK: - Feature Filters
    var hasProcedures: Bool?
    var hasHardRunway: Bool?
    var hasLightedRunway: Bool?
    var pointOfEntry: Bool?
    
    // MARK: - Runway Filters
    var minRunwayLengthFt: Int?
    var maxRunwayLengthFt: Int?
    
    // MARK: - Approach Filters
    var hasILS: Bool?
    var hasRNAV: Bool?
    var hasPrecisionApproach: Bool?
    
    // MARK: - AIP Filters
    var aipField: String?
    
    // MARK: - Default
    static let `default` = FilterConfig()
    
    // MARK: - Computed Properties
    
    /// Returns true if any filter is active
    var hasActiveFilters: Bool {
        country != nil ||
        hasProcedures == true ||
        hasHardRunway == true ||
        hasLightedRunway == true ||
        pointOfEntry == true ||
        minRunwayLengthFt != nil ||
        maxRunwayLengthFt != nil ||
        hasILS == true ||
        hasRNAV == true ||
        hasPrecisionApproach == true ||
        aipField != nil
    }
    
    /// Count of active filters
    var activeFilterCount: Int {
        var count = 0
        if country != nil { count += 1 }
        if hasProcedures == true { count += 1 }
        if hasHardRunway == true { count += 1 }
        if hasLightedRunway == true { count += 1 }
        if pointOfEntry == true { count += 1 }
        if minRunwayLengthFt != nil { count += 1 }
        if maxRunwayLengthFt != nil { count += 1 }
        if hasILS == true { count += 1 }
        if hasRNAV == true { count += 1 }
        if hasPrecisionApproach == true { count += 1 }
        if aipField != nil { count += 1 }
        return count
    }
    
    /// Human-readable description of active filters
    var description: String {
        var parts: [String] = []
        if let country = country { parts.append("Country: \(country)") }
        if hasProcedures == true { parts.append("Has procedures") }
        if hasHardRunway == true { parts.append("Hard runway") }
        if hasLightedRunway == true { parts.append("Lighted runway") }
        if pointOfEntry == true { parts.append("Border crossing") }
        if let min = minRunwayLengthFt { parts.append("Runway ≥ \(min)ft") }
        if let max = maxRunwayLengthFt { parts.append("Runway ≤ \(max)ft") }
        if hasILS == true { parts.append("Has ILS") }
        if hasRNAV == true { parts.append("Has RNAV") }
        if hasPrecisionApproach == true { parts.append("Precision approach") }
        if let field = aipField { parts.append("AIP field: \(field)") }
        return parts.isEmpty ? "No filters" : parts.joined(separator: ", ")
    }
    
    // MARK: - Mutating Helpers
    
    /// Reset all filters to defaults
    mutating func reset() {
        self = .default
    }
}

