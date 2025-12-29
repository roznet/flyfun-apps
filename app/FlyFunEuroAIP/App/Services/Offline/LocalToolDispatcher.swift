//
//  LocalToolDispatcher.swift
//  FlyFunEuroAIP
//
//  Executes tool calls locally against bundled SQLite database and JSON files.
//  Replicates server-side tool functionality for offline use.
//  Matches Android LocalToolDispatcher.kt implementation.
//

import Foundation
import OSLog
import RZUtilsSwift
import RZFlight
import CoreLocation
import SQLite3

/// Executes tool calls locally against bundled SQLite database and JSON files.
/// Matches the Android `LocalToolDispatcher` implementation.
@MainActor
final class LocalToolDispatcher {
    
    // MARK: - State
    
    private var airportDataSource: LocalAirportDataSource?
    private var rulesData: [String: Any]?
    private var notificationsDb: OpaquePointer?
    private var isInitialized = false
    
    // MARK: - Tool Call Types
    
    /// Tool call request from the model
    struct ToolCallRequest {
        let name: String
        let arguments: [String: Any]
    }
    
    /// Result of a tool execution
    enum ToolResult {
        case success(String)
        case error(String)
        
        var value: String {
            switch self {
            case .success(let data): return data
            case .error(let message): return "Error: \(message)"
            }
        }
    }
    
    // MARK: - Init
    
    /// Initialize the dispatcher with data sources.
    /// Call this before dispatching any tool calls.
    func initialize(airportDataSource: LocalAirportDataSource) async throws {
        self.airportDataSource = airportDataSource
        try loadRulesJson()
        openNotificationsDatabase()
        isInitialized = true
        Logger.app.info("LocalToolDispatcher initialized")
    }
    
    /// Open the notifications SQLite database from bundle
    private func openNotificationsDatabase() {
        guard let dbURL = Bundle.main.url(forResource: "ga_notifications", withExtension: "db") else {
            Logger.app.warning("ga_notifications.db not found in bundle")
            return
        }
        
        if sqlite3_open(dbURL.path, &notificationsDb) == SQLITE_OK {
            Logger.app.info("Notifications database opened: \(dbURL.path)")
        } else {
            Logger.app.error("Failed to open notifications database")
            notificationsDb = nil
        }
    }
    
    deinit {
        if let db = notificationsDb {
            sqlite3_close(db)
        }
    }
    
    // MARK: - Tool Dispatch
    
    /// Dispatch a tool call to the appropriate handler
    func dispatch(request: ToolCallRequest) async -> ToolResult {
        guard isInitialized else {
            return .error("LocalToolDispatcher not initialized")
        }
        
        Logger.app.info("Dispatching tool: \(request.name)")
        
        do {
            switch request.name {
            case "search_airports":
                return try await searchAirports(request.arguments)
            case "get_airport_details":
                return try await getAirportDetails(request.arguments)
            case "find_airports_near_route":
                return try await findAirportsNearRoute(request.arguments)
            case "find_airports_near_location":
                return try await findAirportsNearLocation(request.arguments)
            case "get_border_crossing_airports":
                return try await getBorderCrossingAirports(request.arguments)
            case "list_rules_for_country":
                return listRulesForCountry(request.arguments)
            case "compare_rules_between_countries":
                return compareRules(request.arguments)
            case "find_airports_by_notification":
                return findAirportsByNotification(request.arguments)
            default:
                return .error("Unknown tool: \(request.name)")
            }
        } catch {
            Logger.app.error("Tool execution error: \(error.localizedDescription)")
            return .error("Tool execution failed: \(error.localizedDescription)")
        }
    }
    
    /// Parse a tool call from LLM response text
    func parseToolCall(from text: String) -> ToolCallRequest? {
        // Look for JSON-style tool call: {"name": "...", "arguments": {...}}
        // Use a safer approach to find JSON
        guard let startRange = text.range(of: "{\"name\"") else {
            return nil
        }
        
        // Find matching closing brace by counting braces
        var braceCount = 0
        var endIndex = startRange.lowerBound
        var foundStart = false
        
        for index in text[startRange.lowerBound...].indices {
            let char = text[index]
            if char == "{" {
                braceCount += 1
                foundStart = true
            } else if char == "}" {
                braceCount -= 1
                if foundStart && braceCount == 0 {
                    endIndex = index
                    break
                }
            }
        }
        
        guard foundStart && braceCount == 0 else {
            return nil
        }
        
        let jsonString = String(text[startRange.lowerBound...endIndex])
        
        guard let data = jsonString.data(using: .utf8),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let name = json["name"] as? String,
              let arguments = json["arguments"] as? [String: Any] else {
            return nil
        }
        
        return ToolCallRequest(name: name, arguments: arguments)
    }
    
    // MARK: - Airport Tools
    
    private func searchAirports(_ args: [String: Any]) async throws -> ToolResult {
        guard let dataSource = airportDataSource else {
            return .error("Airport data source not available")
        }
        
        let query = (args["query"] as? String)
            ?? (args["city"] as? String)
            ?? (args["name"] as? String)
            ?? (args["icao"] as? String)
            ?? ""
        
        let limit = (args["limit"] as? Int) ?? 10
        
        let airports = try await dataSource.searchAirports(query: query, limit: limit)
        
        return .success(formatAirportsAsText(airports))
    }
    
    private func getAirportDetails(_ args: [String: Any]) async throws -> ToolResult {
        guard let dataSource = airportDataSource else {
            return .error("Airport data source not available")
        }
        
        guard let icao = (args["icao"] as? String)?.uppercased() else {
            return .error("Missing 'icao' argument")
        }
        
        guard let airport = try await dataSource.airportDetail(icao: icao) else {
            return .error("Airport not found: \(icao)")
        }
        
        return .success(formatAirportDetail(airport))
    }
    
    private func findAirportsNearRoute(_ args: [String: Any]) async throws -> ToolResult {
        guard let dataSource = airportDataSource else {
            return .error("Airport data source not available")
        }
        
        guard let from = (args["from"] as? String)?.uppercased() else {
            return .error("Missing 'from' argument")
        }
        guard let to = (args["to"] as? String)?.uppercased() else {
            return .error("Missing 'to' argument")
        }
        
        let maxDistanceNm = (args["max_distance_nm"] as? Int) ?? 50
        
        let result = try await dataSource.airportsNearRoute(
            from: from,
            to: to,
            distanceNm: maxDistanceNm,
            filters: FilterConfig()
        )
        
        var output = "Airports along route \(from) → \(to) (within \(maxDistanceNm) nm):\n"
        for airport in result.airports.prefix(20) {
            output += "- \(airport.icao): \(airport.name) (\(airport.country))\n"
        }
        
        return .success(output)
    }
    
    private func findAirportsNearLocation(_ args: [String: Any]) async throws -> ToolResult {
        guard let dataSource = airportDataSource else {
            return .error("Airport data source not available")
        }
        
        guard let locationQuery = (args["location_query"] as? String)
            ?? (args["location"] as? String)
            ?? (args["query"] as? String) else {
            return .error("Missing 'location_query' argument")
        }
        
        let maxDistanceNm = (args["max_distance_nm"] as? Int) ?? 50
        let maxHoursNotice = (args["max_hours_notice"] as? Int) ?? (args["max_hours"] as? Int)
        
        // First find the center point - try direct ICAO lookup for 4-letter codes
        var centerAirport: RZFlight.Airport?
        let query = locationQuery.uppercased()
        
        if query.count == 4, query.allSatisfy({ $0.isLetter }) {
            // Looks like an ICAO code - try direct lookup first
            centerAirport = try await dataSource.airportDetail(icao: query)
        }
        
        // Fall back to search if direct lookup failed
        if centerAirport == nil {
            let searchResults = try await dataSource.searchAirports(query: locationQuery, limit: 1)
            centerAirport = searchResults.first
        }
        
        guard let center = centerAirport else {
            return .error("Could not find location: \(locationQuery)")
        }
        
        let airports = try await dataSource.airportsNearLocation(
            center: center.coord,
            radiusNm: maxDistanceNm,
            filters: FilterConfig()
        )
        
        // Get notification details for filtering and display
        var notificationDetails: [String: Int] = [:]
        if let db = notificationsDb {
            notificationDetails = getNotificationDetails(db: db, maxHours: maxHoursNotice)
        }
        
        // If notification filter is requested, filter using notifications database
        var filteredAirports = airports
        if maxHoursNotice != nil {
            filteredAirports = airports.filter { notificationDetails[$0.icao] != nil }
        }
        
        var output = "Airports near \(locationQuery) (within \(maxDistanceNm) nm)"
        if let maxHours = maxHoursNotice {
            output += " with max \(maxHours)h notice"
        }
        output += ":\n"
        
        if filteredAirports.isEmpty {
            output += "No airports found matching the criteria.\n"
        } else {
            for airport in filteredAirports.prefix(20) {
                output += "- \(airport.icao): \(airport.name) (\(airport.country))"
                if let hours = notificationDetails[airport.icao] {
                    output += " - \(hours)h notice"
                }
                output += "\n"
            }
        }
        
        return .success(output)
    }
    
    /// Get notification hours for airports (optionally filtered by max hours)
    private func getNotificationDetails(db: OpaquePointer, maxHours: Int?) -> [String: Int] {
        var result: [String: Int] = [:]
        var sql = "SELECT icao, hours_notice FROM ga_notification_requirements WHERE hours_notice IS NOT NULL AND hours_notice > 0"
        if maxHours != nil {
            sql += " AND hours_notice <= ?"
        }
        
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else {
            return result
        }
        defer { sqlite3_finalize(statement) }
        
        if let maxHours = maxHours {
            sqlite3_bind_int(statement, 1, Int32(maxHours))
        }
        
        while sqlite3_step(statement) == SQLITE_ROW {
            let icao = String(cString: sqlite3_column_text(statement, 0))
            let hours = Int(sqlite3_column_int(statement, 1))
            result[icao] = hours
        }
        
        return result
    }
    
    /// Get ICAOs of airports with notification <= maxHours (legacy, kept for compatibility)
    private func getAirportsWithNotification(db: OpaquePointer, maxHours: Int) -> Set<String> {
        return Set(getNotificationDetails(db: db, maxHours: maxHours).keys)
    }
    
    private func getBorderCrossingAirports(_ args: [String: Any]) async throws -> ToolResult {
        guard let dataSource = airportDataSource else {
            return .error("Airport data source not available")
        }
        
        let country = (args["country"] as? String)?.uppercased()
        
        // Get all border crossing ICAOs
        let bcICAOs = try await dataSource.borderCrossingICAOs()
        
        // Get all airports with border crossing and optionally filter by country
        var filters = FilterConfig()
        filters.pointOfEntry = true
        if let country = country {
            filters.country = country
        }
        
        let airports = try await dataSource.airports(matching: filters, limit: 50)
        
        var output = "Border Crossing Airports"
        if let country = country {
            output += " in \(country)"
        }
        output += ":\n"
        
        for airport in airports {
            output += "- \(airport.icao): \(airport.name) (\(airport.city), \(airport.country))\n"
        }
        
        return .success(output)
    }
    
    // MARK: - Rules Tools
    
    private func loadRulesJson() throws {
        guard let rulesURL = Bundle.main.url(forResource: "rules", withExtension: "json") else {
            Logger.app.warning("rules.json not found in bundle - rules tools will not work")
            return
        }
        
        let data = try Data(contentsOf: rulesURL)
        rulesData = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        Logger.app.info("Rules JSON loaded")
    }
    
    private func listRulesForCountry(_ args: [String: Any]) -> ToolResult {
        guard let countryCode = (args["country"] as? String)?.uppercased()
            ?? (args["country_code"] as? String)?.uppercased() else {
            return .error("Missing 'country' argument")
        }
        
        guard let rules = rulesData,
              let questions = rules["questions"] as? [[String: Any]] else {
            return .error("Rules data not loaded")
        }
        
        var output = "Aviation Rules for \(countryCode):\n"
        var foundCount = 0
        
        for question in questions {
            guard let answers = question["answers_by_country"] as? [String: Any],
                  let countryAnswer = answers[countryCode] else {
                continue
            }
            
            let answerStr: String
            if let str = countryAnswer as? String {
                answerStr = str
            } else if let dict = countryAnswer as? [String: Any] {
                answerStr = String(describing: dict)
            } else {
                answerStr = String(describing: countryAnswer)
            }
            
            if !answerStr.isEmpty {
                let qText = (question["question"] as? String) ?? "Unknown Rule"
                output += "- \(qText): \(answerStr)\n"
                foundCount += 1
            }
        }
        
        if foundCount == 0 {
            return .error("No rules found for country: \(countryCode)")
        }
        
        return .success(output)
    }
    
    private func compareRules(_ args: [String: Any]) -> ToolResult {
        guard let country1 = (args["country1"] as? String)?.uppercased() else {
            return .error("Missing 'country1' argument")
        }
        guard let country2 = (args["country2"] as? String)?.uppercased() else {
            return .error("Missing 'country2' argument")
        }
        
        guard let rules = rulesData,
              let questions = rules["questions"] as? [[String: Any]] else {
            return .error("Rules data not loaded")
        }
        
        var output = "Rule Comparison: \(country1) vs \(country2)\n\n"
        
        for question in questions {
            guard let answers = question["answers_by_country"] as? [String: Any] else {
                continue
            }
            
            let answer1 = (answers[country1] as? String) ?? "N/A"
            let answer2 = (answers[country2] as? String) ?? "N/A"
            
            if answer1 != "N/A" || answer2 != "N/A" {
                let qText = (question["question"] as? String) ?? "Unknown"
                output += "**\(qText)**\n"
                output += "- \(country1): \(answer1)\n"
                output += "- \(country2): \(answer2)\n\n"
            }
        }
        
        return .success(output)
    }
    
    // MARK: - Formatting Helpers
    
    private func formatAirportsAsText(_ airports: [RZFlight.Airport]) -> String {
        if airports.isEmpty {
            return "No airports found."
        }
        
        var output = ""
        for airport in airports {
            output += "- \(airport.icao): \(airport.name)"
            if !airport.city.isEmpty {
                output += " (\(airport.city)"
                if !airport.country.isEmpty {
                    output += ", \(airport.country)"
                }
                output += ")"
            }
            output += "\n"
        }
        return output
    }
    
    private func formatAirportDetail(_ airport: RZFlight.Airport) -> String {
        var output = "\(airport.icao) - \(airport.name)\n"
        output += "Location: \(airport.city), \(airport.country)\n"
        output += "Coordinates: \(String(format: "%.4f", airport.coord.latitude)), \(String(format: "%.4f", airport.coord.longitude))\n"
        output += "Elevation: \(airport.elevation_ft) ft\n"
        output += "Type: \(airport.type.rawValue)\n"
        
        if !airport.runways.isEmpty {
            output += "Runways:\n"
            for runway in airport.runways {
                output += "  - \(runway.le.ident)/\(runway.he.ident): \(runway.length_ft)ft x \(runway.width_ft)ft"
                if !runway.surface.isEmpty {
                    output += " (\(runway.surface))"
                }
                output += "\n"
            }
        }
        
        return output
    }
    
    // MARK: - Notification Tool
    
    private func findAirportsByNotification(_ args: [String: Any]) -> ToolResult {
        guard let db = notificationsDb else {
            return .error("Notifications database not available. Please ensure ga_notifications.db is bundled.")
        }
        
        let maxHours = (args["max_hours"] as? Int) ?? (args["max_hours_notice"] as? Int)
        let country = (args["country"] as? String)?.uppercased()
        let limit = (args["limit"] as? Int) ?? 20
        
        Logger.app.info("findAirportsByNotification: maxHours=\(String(describing: maxHours)), country=\(String(describing: country))")
        
        // Build SQL query
        var sql = """
            SELECT icao, hours_notice, summary, operating_hours_start, operating_hours_end
            FROM ga_notification_requirements
            WHERE hours_notice IS NOT NULL AND hours_notice > 0
        """
        
        if maxHours != nil {
            sql += " AND hours_notice <= ?"
        }
        sql += " ORDER BY hours_notice ASC LIMIT ?"
        
        var statement: OpaquePointer?
        guard sqlite3_prepare_v2(db, sql, -1, &statement, nil) == SQLITE_OK else {
            return .error("Failed to prepare SQL query")
        }
        defer { sqlite3_finalize(statement) }
        
        // Bind parameters
        var paramIndex: Int32 = 1
        if let hours = maxHours {
            sqlite3_bind_int(statement, paramIndex, Int32(hours))
            paramIndex += 1
        }
        sqlite3_bind_int(statement, paramIndex, Int32(limit * 3)) // Get more to filter by country
        
        // Collect results
        struct NotifAirport {
            let icao: String
            let hoursNotice: Int?
            let summary: String?
            let hoursStart: String?
            let hoursEnd: String?
        }
        
        var airports: [NotifAirport] = []
        while sqlite3_step(statement) == SQLITE_ROW {
            let icao = String(cString: sqlite3_column_text(statement, 0))
            
            // Filter by country if specified (using ICAO prefix)
            if let country = country {
                let prefix = country.prefix(2)
                if !icao.hasPrefix(prefix) {
                    continue
                }
            }
            
            let hoursNotice = sqlite3_column_type(statement, 1) != SQLITE_NULL 
                ? Int(sqlite3_column_int(statement, 1)) : nil
            
            let summary = sqlite3_column_type(statement, 2) != SQLITE_NULL
                ? String(cString: sqlite3_column_text(statement, 2)) : nil
            
            let hoursStart = sqlite3_column_type(statement, 3) != SQLITE_NULL
                ? String(cString: sqlite3_column_text(statement, 3)) : nil
            
            let hoursEnd = sqlite3_column_type(statement, 4) != SQLITE_NULL
                ? String(cString: sqlite3_column_text(statement, 4)) : nil
            
            airports.append(NotifAirport(
                icao: icao,
                hoursNotice: hoursNotice,
                summary: summary,
                hoursStart: hoursStart,
                hoursEnd: hoursEnd
            ))
            
            if airports.count >= limit {
                break
            }
        }
        
        if airports.isEmpty {
            var msg = "No airports found with notification requirements"
            if let hours = maxHours {
                msg += " under \(hours) hours"
            }
            if let c = country {
                msg += " in \(c)"
            }
            return .error(msg)
        }
        
        // Format output
        var output = "Airports with notification requirements"
        if let hours = maxHours {
            output += " (max \(hours)h notice)"
        }
        if let c = country {
            output += " in \(c)"
        }
        output += ":\n\n"
        
        for airport in airports {
            output += "• \(airport.icao)"
            if let hours = airport.hoursNotice {
                output += " - \(hours)h notice"
            }
            if let summary = airport.summary, !summary.isEmpty {
                output += ", \(summary)"
            }
            if let start = airport.hoursStart, let end = airport.hoursEnd, !start.isEmpty || !end.isEmpty {
                output += " (hours: \(start)-\(end))"
            }
            output += "\n"
        }
        
        return .success(output)
    }
}
