//
//  APIAirportModels.swift
//  FlyFunEuroAIP
//
//  Internal models matching API JSON responses.
//  These are converted to RZFlight models by adapters - never exposed to the rest of the app.
//

import Foundation

// MARK: - Airport Summary (List Response)

/// Matches Python `AirportSummary` model
struct APIAirportSummary: Codable, Sendable {
    let ident: String
    let name: String?
    let latitudeDeg: Double?
    let longitudeDeg: Double?
    let isoCountry: String?
    let municipality: String?
    let pointOfEntry: Bool?
    let hasProcedures: Bool
    let hasRunways: Bool
    let hasAipData: Bool
    let hasHardRunway: Bool?
    let hasLightedRunway: Bool?
    let hasSoftRunway: Bool?
    let hasWaterRunway: Bool?
    let hasSnowRunway: Bool?
    let longestRunwayLengthFt: Int?
    let procedureCount: Int
    let runwayCount: Int
    let aipEntryCount: Int
    let ga: APIGAFriendlySummary?
}

// MARK: - Airport Detail

/// Matches Python `AirportDetail` model
struct APIAirportDetail: Codable, Sendable {
    let ident: String
    let name: String?
    let type: String?
    let latitudeDeg: Double?
    let longitudeDeg: Double?
    let elevationFt: Double?
    let continent: String?
    let isoCountry: String?
    let isoRegion: String?
    let municipality: String?
    let scheduledService: String?
    let gpsCode: String?
    let iataCode: String?
    let localCode: String?
    let homeLink: String?
    let wikipediaLink: String?
    let keywords: String?
    let pointOfEntry: Bool?
    let avgas: Bool?
    let jetA: Bool?
    let hasHardRunway: Bool?
    let hasLightedRunway: Bool?
    let hasSoftRunway: Bool?
    let hasWaterRunway: Bool?
    let hasSnowRunway: Bool?
    let longestRunwayLengthFt: Int?
    let sources: [String]
    let runways: [APIRunway]
    let procedures: [APIProcedure]
    let aipEntries: [APIAIPEntry]
    let createdAt: String
    let updatedAt: String
}

// MARK: - Runway

/// Matches Python `RunwayResponse` model
struct APIRunway: Codable, Sendable {
    let leIdent: String
    let heIdent: String
    let lengthFt: Int?
    let widthFt: Int?
    let surface: String?
    let lighted: Bool?
    let closed: Bool?
    let leLatitudeDeg: Double?
    let leLongitudeDeg: Double?
    let leElevationFt: Int?
    let leHeadingDegT: Double?
    let leDisplacedThresholdFt: Int?
    let heLatitudeDeg: Double?
    let heLongitudeDeg: Double?
    let heElevationFt: Int?
    let heHeadingDegT: Double?
    let heDisplacedThresholdFt: Int?
}

// MARK: - Procedure

/// Matches Python `ProcedureDetail` model
struct APIProcedure: Codable, Sendable {
    let name: String
    let procedureType: String
    let approachType: String?
    let runwayNumber: String?
    let runwayLetter: String?
    let runwayIdent: String?
    let source: String?
    let authority: String?
    let rawName: String?
    let data: [String: AnyCodable]?
    let createdAt: String?
    let updatedAt: String?
}

// MARK: - AIP Entry

/// Matches Python `AIPEntryResponse` model
struct APIAIPEntry: Codable, Sendable {
    let ident: String
    let section: String
    let field: String
    let value: String
    let stdField: String?
    let stdFieldId: Int?
    let mappingScore: Double?
    let altField: String?
    let altValue: String?
    let source: String?
    let createdAt: String?
}

// MARK: - GA Friendliness

/// Matches Python `GAFriendlySummary` model
struct APIGAFriendlySummary: Codable, Sendable {
    let features: [String: Double?]
    let personaScores: [String: Double?]
    let reviewCount: Int
    let lastReviewUtc: String?
    let tags: [String]?
    let summaryText: String?
    let notificationHassle: String?
}

// MARK: - Route Search Response

struct APIRouteSearchResponse: Codable, Sendable {
    let departure: APIAirportSummary?
    let destination: APIAirportSummary?
    let airports: [APIAirportSummary]
    let routeDistanceNm: Double?
}

// MARK: - Locate Response

struct APILocateResponse: Codable, Sendable {
    let center: APICoordinate
    let radiusNm: Int
    let airports: [APIAirportSummary]
}

struct APICoordinate: Codable, Sendable {
    let latitude: Double
    let longitude: Double
}

// MARK: - Helper for arbitrary JSON

/// Wrapper for encoding/decoding arbitrary JSON values
struct AnyCodable: Codable, Sendable {
    let value: Any
    
    init(_ value: Any) {
        self.value = value
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        
        if container.decodeNil() {
            self.value = NSNull()
        } else if let bool = try? container.decode(Bool.self) {
            self.value = bool
        } else if let int = try? container.decode(Int.self) {
            self.value = int
        } else if let double = try? container.decode(Double.self) {
            self.value = double
        } else if let string = try? container.decode(String.self) {
            self.value = string
        } else if let array = try? container.decode([AnyCodable].self) {
            self.value = array.map(\.value)
        } else if let dict = try? container.decode([String: AnyCodable].self) {
            self.value = dict.mapValues(\.value)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode AnyCodable")
        }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        
        switch value {
        case is NSNull:
            try container.encodeNil()
        case let bool as Bool:
            try container.encode(bool)
        case let int as Int:
            try container.encode(int)
        case let double as Double:
            try container.encode(double)
        case let string as String:
            try container.encode(string)
        case let array as [Any]:
            try container.encode(array.map { AnyCodable($0) })
        case let dict as [String: Any]:
            try container.encode(dict.mapValues { AnyCodable($0) })
        default:
            throw EncodingError.invalidValue(value, .init(codingPath: encoder.codingPath, debugDescription: "Cannot encode AnyCodable"))
        }
    }
}

