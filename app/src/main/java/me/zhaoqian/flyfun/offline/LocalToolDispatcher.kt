package me.zhaoqian.flyfun.offline

import android.content.Context
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import android.util.Log
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.serialization.json.*
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Executes tool calls locally against bundled SQLite database and JSON files.
 * 
 * This replicates the server-side tool functionality for offline use.
 */
@Singleton
class LocalToolDispatcher @Inject constructor(
    @ApplicationContext private val context: Context
) {
    companion object {
        private const val TAG = "LocalToolDispatcher"
        
        // Asset paths
        private const val AIRPORTS_DB_ASSET = "offline/airports.db"
        private const val NOTIFICATIONS_DB_ASSET = "offline/ga_notifications.db"
        private const val RULES_JSON_ASSET = "offline/rules.json"
        
        // Database file in app storage
        private const val AIRPORTS_DB_NAME = "airports.db"
        private const val NOTIFICATIONS_DB_NAME = "ga_notifications.db"
    }
    
    private var airportsDb: SQLiteDatabase? = null
    private var notificationsDb: SQLiteDatabase? = null
    private var rulesData: JsonObject? = null
    private val json = Json { ignoreUnknownKeys = true }
    
    /**
     * Tool call request from the model
     */
    data class ToolCallRequest(
        val name: String,
        val arguments: Map<String, Any?>
    )
    
    /**
     * Result of a tool execution
     */
    sealed class ToolResult {
        data class Success(val data: String) : ToolResult()
        data class Error(val message: String) : ToolResult()
    }
    
    /**
     * Initialize databases and load JSON data.
     * Call this before using the dispatcher.
     */
    suspend fun initialize(): Result<Unit> {
        return try {
            copyDatabaseFromAssets(AIRPORTS_DB_ASSET, AIRPORTS_DB_NAME)
            copyDatabaseFromAssets(NOTIFICATIONS_DB_ASSET, NOTIFICATIONS_DB_NAME)
            loadRulesJson()
            openDatabases()
            Log.i(TAG, "LocalToolDispatcher initialized")
            Result.success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize: ${e.message}", e)
            Result.failure(e)
        }
    }
    
    /**
     * Copy airports.db from assets to app storage if needed
     */
    private fun copyDatabaseFromAssets(assetPath: String, dbName: String) {
        val dbFile = context.getDatabasePath(dbName)
        
        // Skip if already exists
        if (dbFile.exists()) {
            Log.d(TAG, "Database already exists: ${dbFile.absolutePath}")
            return
        }
        
        // Ensure parent directory exists
        dbFile.parentFile?.mkdirs()
        
        try {
            context.assets.open(assetPath).use { input ->
                dbFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            }
            Log.i(TAG, "Database copied to: ${dbFile.absolutePath}")
        } catch (e: Exception) {
            Log.w(TAG, "Could not copy $assetPath: ${e.message}")
        }
    }
    
    /**
     * Load rules.json from assets
     */
    private fun loadRulesJson() {
        val jsonString = context.assets.open(RULES_JSON_ASSET).bufferedReader().use { it.readText() }
        rulesData = json.parseToJsonElement(jsonString).jsonObject
        Log.i(TAG, "Rules JSON loaded")
    }
    
    /**
     * Open the SQLite database
     */
    private fun openDatabases() {
        val airportsFile = context.getDatabasePath(AIRPORTS_DB_NAME)
        airportsDb = SQLiteDatabase.openDatabase(
            airportsFile.absolutePath,
            null,
            SQLiteDatabase.OPEN_READONLY
        )
        Log.i(TAG, "Airports database opened: ${airportsFile.absolutePath}")
        
        val notificationsFile = context.getDatabasePath(NOTIFICATIONS_DB_NAME)
        if (notificationsFile.exists()) {
            notificationsDb = SQLiteDatabase.openDatabase(
                notificationsFile.absolutePath,
                null,
                SQLiteDatabase.OPEN_READONLY
            )
            Log.i(TAG, "Notifications database opened: ${notificationsFile.absolutePath}")
        } else {
            Log.w(TAG, "Notifications database not found")
        }
    }
    
    /**
     * Dispatch a tool call to the appropriate handler
     */
    fun dispatch(request: ToolCallRequest): ToolResult {
        Log.d(TAG, "Dispatching tool: ${request.name} with args: ${request.arguments}")
        
        return try {
            when (request.name) {
                "search_airports" -> searchAirports(request.arguments)
                "get_airport_details" -> getAirportDetails(request.arguments)
                "get_airport_runways" -> getAirportRunways(request.arguments)
                "find_airports_near_route" -> findAirportsNearRoute(request.arguments)
                "find_airports_near_location" -> findAirportsNearLocation(request.arguments)
                "get_border_crossing_airports" -> getBorderCrossingAirports(request.arguments)
                "get_notification_for_airport" -> getNotificationForAirport(request.arguments)
                "find_airports_by_notification" -> findAirportsByNotification(request.arguments)
                "list_rules_for_country" -> listRulesForCountry(request.arguments)
                "compare_rules_between_countries" -> compareRules(request.arguments)
                else -> ToolResult.Error("Unknown tool: ${request.name}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Tool execution error: ${e.message}", e)
            ToolResult.Error("Tool execution failed: ${e.message}")
        }
    }
    
    // ========== Airport Tools ==========
    
    /**
     * Search airports by ICAO code, name, or city
     */
    private fun searchAirports(args: Map<String, Any?>): ToolResult {
        // Accept any argument - try known names first, then fallback to any value
        val query = args["query"]?.toString() 
            ?: args["city"]?.toString()
            ?: args["name"]?.toString()
            ?: args["iata"]?.toString()
            ?: args["icao"]?.toString()
            ?: args["code"]?.toString()
            ?: args.values.firstOrNull()?.toString()  // Fallback: use any argument value
            ?: return ToolResult.Error("Missing search argument")
        val limit = (args["limit"] as? Number)?.toInt() ?: 10
        
        val db = airportsDb ?: return ToolResult.Error("Database not initialized")
        
        // SQL uses actual column names from airport database schema
        val sql = """
            SELECT icao_code, name, municipality, iso_country, latitude_deg, longitude_deg, type
            FROM airports 
            WHERE icao_code LIKE ? 
               OR name LIKE ? 
               OR municipality LIKE ?
            LIMIT ?
        """.trimIndent()
        
        val searchPattern = "%$query%"
        val cursor = db.rawQuery(sql, arrayOf(searchPattern, searchPattern, searchPattern, limit.toString()))
        
        val airports = buildJsonArray {
            cursor.use {
                while (it.moveToNext()) {
                    add(buildJsonObject {
                        put("icao", it.getString(0))
                        put("name", it.getStringOrNull(1))
                        put("city", it.getStringOrNull(2))  // municipality -> city in output
                        put("country", it.getStringOrNull(3))  // iso_country -> country in output
                        put("latitude", it.getDoubleOrNull(4))
                        put("longitude", it.getDoubleOrNull(5))
                        put("type", it.getStringOrNull(6))
                    })
                }
            }
        }
        
        return ToolResult.Success(airports.toString())
    }
    
    /**
     * Get detailed information for a specific airport
     */
    private fun getAirportDetails(args: Map<String, Any?>): ToolResult {
        val icao = args["icao"]?.toString()?.uppercase() 
            ?: args["icao_code"]?.toString()?.uppercase()
            ?: return ToolResult.Error("Missing 'icao' argument")
        
        val db = airportsDb ?: return ToolResult.Error("Database not initialized")
        
        // SQL uses actual column names from airport database schema
        val sql = """
            SELECT icao_code, name, municipality, iso_country, latitude_deg, longitude_deg,
                   elevation_ft, type, iata_code, iso_region
            FROM airports 
            WHERE icao_code = ?
        """.trimIndent()
        
        val cursor = db.rawQuery(sql, arrayOf(icao))
        
        if (!cursor.moveToFirst()) {
            cursor.close()
            return ToolResult.Error("Airport not found: $icao")
        }
        
        val airport = buildJsonObject {
            put("icao", cursor.getString(0))
            put("name", cursor.getStringOrNull(1))
            put("city", cursor.getStringOrNull(2))  // municipality -> city
            put("country", cursor.getStringOrNull(3))  // iso_country -> country
            put("latitude", cursor.getDoubleOrNull(4))
            put("longitude", cursor.getDoubleOrNull(5))
            put("elevation_ft", cursor.getDoubleOrNull(6)?.toInt())
            put("type", cursor.getStringOrNull(7))
            put("iata", cursor.getStringOrNull(8))
            put("region", cursor.getStringOrNull(9))
        }
        
        cursor.close()
        return ToolResult.Success(airport.toString())
    }
    
    /**
     * Get runways for a specific airport
     */
    private fun getAirportRunways(args: Map<String, Any?>): ToolResult {
        val icao = args["icao"]?.toString()?.uppercase()
            ?: return ToolResult.Error("Missing 'icao' argument")
        
        val db = airportsDb ?: return ToolResult.Error("Database not initialized")
        
        val sql = """
            SELECT le_ident, he_ident, length_ft, width_ft, surface, lighted
            FROM runways 
            WHERE airport_icao = ?
        """.trimIndent()
        
        val cursor = db.rawQuery(sql, arrayOf(icao))
        
        val runways = buildJsonArray {
            cursor.use {
                while (it.moveToNext()) {
                    add(buildJsonObject {
                        put("le_ident", it.getStringOrNull(0))
                        put("he_ident", it.getStringOrNull(1))
                        put("length_ft", it.getIntOrNull(2))
                        put("width_ft", it.getIntOrNull(3))
                        put("surface", it.getStringOrNull(4))
                        put("lighted", it.getIntOrNull(5) == 1)
                    })
                }
            }
        }
        
        return ToolResult.Success(runways.toString())
    }
    
    // ========== Rules Tools ==========
    
    /**
     * List aviation rules for a specific country
     */
    private fun listRulesForCountry(args: Map<String, Any?>): ToolResult {
        val countryCode = args["country"]?.toString()?.uppercase()
            ?: args["country_code"]?.toString()?.uppercase()
            ?: return ToolResult.Error("Missing 'country' argument")
        
        val rules = rulesData ?: return ToolResult.Error("Rules data not loaded")
        
        val sb = StringBuilder()
        sb.appendLine("Aviation Rules for $countryCode:")
        
        var foundCount = 0
        rules["questions"]?.jsonArray?.forEach { questionElement ->
            val question = questionElement.jsonObject
            val answers = question["answers_by_country"]?.jsonObject
            val countryAnswerElement = answers?.get(countryCode)
            
            // Handle both primitive (String) and object answer types
            val countryAnswer = when {
                countryAnswerElement == null -> null
                countryAnswerElement is kotlinx.serialization.json.JsonPrimitive -> countryAnswerElement.content
                countryAnswerElement is kotlinx.serialization.json.JsonObject -> countryAnswerElement.toString()
                else -> countryAnswerElement.toString()
            }
            
            if (countryAnswer != null && countryAnswer.isNotBlank()) {
                val qText = question["question"]?.jsonPrimitive?.contentOrNull ?: "Unknown Rule"
                sb.appendLine("- $qText: $countryAnswer")
                foundCount++
            }
        }
        
        if (foundCount == 0) {
            return ToolResult.Error("No rules found for country: $countryCode")
        }
        
        return ToolResult.Success(sb.toString())
    }
    
    /**
     * Compare rules between two countries
     */
    private fun compareRules(args: Map<String, Any?>): ToolResult {
        val country1 = args["country1"]?.toString()?.uppercase()
            ?: return ToolResult.Error("Missing 'country1' argument")
        val country2 = args["country2"]?.toString()?.uppercase()
            ?: return ToolResult.Error("Missing 'country2' argument")
        
        val rules = rulesData ?: return ToolResult.Error("Rules data not loaded")
        
        val result = buildJsonObject {
            put("countries", buildJsonArray { add(country1); add(country2) })
            
            val comparisons = buildJsonArray {
                rules["questions"]?.jsonArray?.forEach { questionElement ->
                    val question = questionElement.jsonObject
                    val answers = question["answers_by_country"]?.jsonObject
                    val answer1 = answers?.get(country1)?.jsonPrimitive?.content
                    val answer2 = answers?.get(country2)?.jsonPrimitive?.content
                    
                    if (answer1 != null || answer2 != null) {
                        add(buildJsonObject {
                            put("question", question["question"]?.jsonPrimitive?.content)
                            put("category", question["category"]?.jsonPrimitive?.content)
                            put(country1, answer1 ?: "N/A")
                            put(country2, answer2 ?: "N/A")
                        })
                    }
                }
            }
            put("comparisons", comparisons)
        }
        
        return ToolResult.Success(result.toString())
    }
    
    /**
     * Close database and free resources
     */
    fun close() {
        airportsDb?.close()
        airportsDb = null
        notificationsDb?.close()
        notificationsDb = null
        rulesData = null
        Log.i(TAG, "LocalToolDispatcher closed")
    }
    
    // ========== Route & Location Tools ==========
    
    /**
     * Find airports along a route corridor between two airports
     */
    private fun findAirportsNearRoute(args: Map<String, Any?>): ToolResult {
        Log.d(TAG, "findAirportsNearRoute called with args: $args")
        
        val fromIcao = (args["from"]?.toString() ?: args["from_location"]?.toString())?.uppercase()
            ?: return ToolResult.Error("Missing 'from' argument")
        val toIcao = (args["to"]?.toString() ?: args["to_location"]?.toString())?.uppercase()
            ?: return ToolResult.Error("Missing 'to' argument")
        val maxDistanceNm = (args["max_distance_nm"] as? Number)?.toDouble() ?: 50.0
        val limit = (args["limit"] as? Number)?.toInt() ?: 100
        
        Log.d(TAG, "Route search: $fromIcao -> $toIcao, max distance: $maxDistanceNm nm")
        
        val db = airportsDb ?: return ToolResult.Error("Database not initialized")
        
        // Get departure airport coordinates
        val fromAirport = getAirportCoordinates(db, fromIcao)
        if (fromAirport == null) {
            Log.e(TAG, "Departure airport not found: $fromIcao")
            return ToolResult.Error("Departure airport not found: $fromIcao")
        }
        Log.d(TAG, "From airport $fromIcao: ${fromAirport.first}, ${fromAirport.second}")
        
        // Get destination airport coordinates
        val toAirport = getAirportCoordinates(db, toIcao)
        if (toAirport == null) {
            Log.e(TAG, "Destination airport not found: $toIcao")
            return ToolResult.Error("Destination airport not found: $toIcao")
        }
        Log.d(TAG, "To airport $toIcao: ${toAirport.first}, ${toAirport.second}")
        
        val routeLength = GeoUtils.haversineDistance(
            fromAirport.first, fromAirport.second,
            toAirport.first, toAirport.second
        )
        Log.d(TAG, "Route length: $routeLength nm")
        
        // Get all airports with coordinates, procedure count, and border crossing status
        val sql = """
            SELECT a.icao_code, a.name, a.municipality, a.iso_country, 
                   a.latitude_deg, a.longitude_deg, a.type,
                   (SELECT COUNT(*) FROM procedures p WHERE p.airport_icao = a.icao_code) as proc_count,
                   (SELECT COUNT(*) FROM border_crossing_points b WHERE b.icao_code = a.icao_code) as is_bcp
            FROM airports a
            WHERE a.latitude_deg IS NOT NULL AND a.longitude_deg IS NOT NULL
              AND a.icao_code != ? AND a.icao_code != ?
        """.trimIndent()
        
        val cursor = db.rawQuery(sql, arrayOf(fromIcao, toIcao))
        
        data class AirportWithDistance(
            val icao: String,
            val name: String?,
            val city: String?,
            val country: String?,
            val lat: Double,
            val lon: Double,
            val type: String?,
            val hasProcedures: Boolean,
            val isBorderCrossing: Boolean,
            val crossTrackNm: Double,
            val alongTrackNm: Double
        )
        
        val nearbyAirports = mutableListOf<AirportWithDistance>()
        
        cursor.use {
            while (it.moveToNext()) {
                val lat = it.getDoubleOrNull(4) ?: continue
                val lon = it.getDoubleOrNull(5) ?: continue
                
                // Calculate cross-track distance
                val crossTrackNm = GeoUtils.crossTrackDistance(
                    lat, lon,
                    fromAirport.first, fromAirport.second,
                    toAirport.first, toAirport.second
                )
                
                if (crossTrackNm <= maxDistanceNm) {
                    // Check if within route segment
                    val alongTrackNm = GeoUtils.alongTrackDistance(
                        lat, lon,
                        fromAirport.first, fromAirport.second,
                        toAirport.first, toAirport.second
                    )
                    
                    val routeLength = GeoUtils.haversineDistance(
                        fromAirport.first, fromAirport.second,
                        toAirport.first, toAirport.second
                    )
                    
                    // Only include if along-track is within route + some buffer
                    if (alongTrackNm >= -10 && alongTrackNm <= routeLength + 10) {
                        val procedureCount = it.getIntOrNull(7) ?: 0
                        val borderCount = it.getIntOrNull(8) ?: 0
                        
                        nearbyAirports.add(AirportWithDistance(
                            icao = it.getString(0),
                            name = it.getStringOrNull(1),
                            city = it.getStringOrNull(2),
                            country = it.getStringOrNull(3),
                            lat = lat,
                            lon = lon,
                            type = it.getStringOrNull(6),
                            hasProcedures = procedureCount > 0,
                            isBorderCrossing = borderCount > 0,
                            crossTrackNm = crossTrackNm,
                            alongTrackNm = alongTrackNm
                        ))
                    }
                }
            }
        }
        
        // Priority scoring matching web PersonaOptimizedStrategy:
        // Priority 1: has procedures + border crossing (best)
        // Priority 2: has procedures only
        // Priority 3: border crossing only  
        // Priority 4: neither
        // Then sort by airport type (large > medium > small)
        // Then by along-track distance
        fun priorityScore(airport: AirportWithDistance): Int {
            val procBorderScore = when {
                airport.hasProcedures && airport.isBorderCrossing -> 0
                airport.hasProcedures -> 1
                airport.isBorderCrossing -> 2
                else -> 3
            }
            val typeScore = when (airport.type) {
                "large_airport" -> 0
                "medium_airport" -> 10
                "small_airport" -> 20
                else -> 30
            }
            return procBorderScore * 100 + typeScore
        }
        
        // Filter out closed airports and heliports, sort by priority then along-track distance
        val sortedAirports = nearbyAirports
            .filter { it.type != "closed" && it.type != "heliport" }
            .sortedWith(compareBy({ priorityScore(it) }, { it.alongTrackNm }))
            .take(limit)
        
        Log.d(TAG, "Found ${sortedAirports.size} airports along route (from ${nearbyAirports.size} candidates)")
        
        val result = buildJsonObject {
            put("from", fromIcao)
            put("to", toIcao)
            put("max_distance_nm", maxDistanceNm)
            put("count", sortedAirports.size)
            put("airports", buildJsonArray {
                sortedAirports.forEach { airport ->
                    add(buildJsonObject {
                        put("icao", airport.icao)
                        put("name", airport.name)
                        put("city", airport.city)
                        put("country", airport.country)
                        put("latitude", airport.lat)
                        put("longitude", airport.lon)
                        put("type", airport.type)
                        put("distance_from_route_nm", String.format("%.1f", airport.crossTrackNm).toDouble())
                        put("distance_along_route_nm", String.format("%.1f", airport.alongTrackNm).toDouble())
                    })
                }
            })
        }
        
        Log.d(TAG, "findAirportsNearRoute returning result with ${sortedAirports.size} airports")
        return ToolResult.Success(result.toString())
    }
    
    private fun getAirportCoordinates(db: SQLiteDatabase, icao: String): Pair<Double, Double>? {
        val cursor = db.rawQuery(
            "SELECT latitude_deg, longitude_deg FROM airports WHERE icao_code = ?",
            arrayOf(icao)
        )
        return cursor.use {
            if (it.moveToFirst()) {
                val lat = it.getDoubleOrNull(0)
                val lon = it.getDoubleOrNull(1)
                if (lat != null && lon != null) Pair(lat, lon) else null
            } else null
        }
    }
    
    /**
     * Find airports near a location (city name or airport) with optional filters
     */
    private fun findAirportsNearLocation(args: Map<String, Any?>): ToolResult {
        val locationQuery = (args["location_query"]?.toString() ?: args["location"]?.toString() 
            ?: args["query"]?.toString() ?: args["near"]?.toString())
            ?: return ToolResult.Error("Missing 'location_query' argument")
        
        val maxDistanceNm = (args["max_distance_nm"] as? Number)?.toDouble() ?: 50.0
        val limit = (args["limit"] as? Number)?.toInt() ?: 20
        
        // Parse filters from args - handle both Number and String types
        val maxHoursNotice = when (val hoursArg = args["max_hours_notice"]) {
            is Number -> hoursArg.toInt()
            is String -> hoursArg.toIntOrNull()
            else -> (args["filters"] as? Map<*, *>)?.get("max_hours_notice")?.toString()?.toIntOrNull()
        }
        
        Log.d(TAG, "findAirportsNearLocation: query=$locationQuery, maxDist=$maxDistanceNm, maxHours=$maxHoursNotice, argsKeys=${args.keys}")
        
        val db = airportsDb ?: return ToolResult.Error("Database not initialized")
        
        // First try to find the center point - could be ICAO or city name
        val centerPoint: Pair<Double, Double>
        var centerName = locationQuery
        
        // Try as ICAO first
        val icaoUpper = locationQuery.uppercase()
        var centerCoords = getAirportCoordinates(db, icaoUpper)
        
        if (centerCoords != null) {
            centerPoint = centerCoords
        } else {
            // Search by city/name - find first matching airport
            val searchCursor = db.rawQuery("""
                SELECT icao_code, name, municipality, latitude_deg, longitude_deg
                FROM airports 
                WHERE municipality LIKE ? OR name LIKE ?
                LIMIT 1
            """.trimIndent(), arrayOf("%$locationQuery%", "%$locationQuery%"))
            
            centerCoords = searchCursor.use {
                if (it.moveToFirst()) {
                    val lat = it.getDoubleOrNull(3)
                    val lon = it.getDoubleOrNull(4)
                    centerName = "${it.getStringOrNull(2) ?: it.getStringOrNull(1)}"
                    if (lat != null && lon != null) Pair(lat, lon) else null
                } else null
            }
            
            if (centerCoords == null) {
                return ToolResult.Error("Could not find location: $locationQuery")
            }
            centerPoint = centerCoords
        }
        
        Log.d(TAG, "Center point: $centerName at ${centerPoint.first}, ${centerPoint.second}")
        
        // Get airports with notification data
        val sql = """
            SELECT a.icao_code, a.name, a.municipality, a.iso_country, 
                   a.latitude_deg, a.longitude_deg, a.type
            FROM airports a
            WHERE a.latitude_deg IS NOT NULL AND a.longitude_deg IS NOT NULL
        """.trimIndent()
        
        val cursor = db.rawQuery(sql, arrayOf())
        
        data class NearbyAirport(
            val icao: String,
            val name: String?,
            val city: String?,
            val country: String?,
            val lat: Double,
            val lon: Double,
            val type: String?,
            val distanceNm: Double,
            var hoursNotice: Int? = null,
            var notifSummary: String? = null
        )
        
        val nearbyAirports = mutableListOf<NearbyAirport>()
        
        cursor.use {
            while (it.moveToNext()) {
                val lat = it.getDoubleOrNull(4) ?: continue
                val lon = it.getDoubleOrNull(5) ?: continue
                
                val distanceNm = GeoUtils.haversineDistance(
                    centerPoint.first, centerPoint.second, lat, lon
                )
                
                if (distanceNm <= maxDistanceNm) {
                    nearbyAirports.add(NearbyAirport(
                        icao = it.getString(0),
                        name = it.getStringOrNull(1),
                        city = it.getStringOrNull(2),
                        country = it.getStringOrNull(3),
                        lat = lat,
                        lon = lon,
                        type = it.getStringOrNull(6),
                        distanceNm = distanceNm
                    ))
                }
            }
        }
        
        // Get notification data for nearby airports if available
        val notifDb = notificationsDb
        if (notifDb != null) {
            Log.d(TAG, "Querying notification data for ${nearbyAirports.size} airports")
            var foundCount = 0
            for (airport in nearbyAirports) {
                val notifCursor = notifDb.rawQuery(
                    "SELECT hours_notice, summary FROM ga_notification_requirements WHERE icao = ?",
                    arrayOf(airport.icao)
                )
                notifCursor.use {
                    if (it.moveToFirst()) {
                        airport.hoursNotice = it.getIntOrNull(0)
                        airport.notifSummary = it.getStringOrNull(1)
                        
                        // If hours_notice is NULL, try to parse it from summary text
                        if (airport.hoursNotice == null && airport.notifSummary != null) {
                            airport.hoursNotice = parseHoursFromSummary(airport.notifSummary!!)
                        }
                        
                        if (airport.hoursNotice != null || airport.notifSummary != null) {
                            foundCount++
                        }
                    }
                }
            }
            Log.d(TAG, "Found notification data for $foundCount of ${nearbyAirports.size} airports")
        } else {
            Log.w(TAG, "Notifications database is NULL - cannot query notification data")
        }
        
        // Apply max_hours_notice filter if specified
        var filteredAirports = nearbyAirports.filter { 
            it.type != "closed" && it.type != "heliport" 
        }
        
        if (maxHoursNotice != null) {
            filteredAirports = filteredAirports.filter { 
                it.hoursNotice != null && it.hoursNotice!! <= maxHoursNotice 
            }
        }
        
        // Sort by distance and limit
        val sortedAirports = filteredAirports.sortedBy { it.distanceNm }.take(limit)
        
        Log.d(TAG, "Found ${sortedAirports.size} airports near $centerName")
        
        val result = buildJsonObject {
            put("location", centerName)
            put("max_distance_nm", maxDistanceNm)
            if (maxHoursNotice != null) put("max_hours_notice_filter", maxHoursNotice)
            put("count", sortedAirports.size)
            put("airports", buildJsonArray {
                sortedAirports.forEach { airport ->
                    add(buildJsonObject {
                        put("icao", airport.icao)
                        put("name", airport.name)
                        // Put notification data early so it survives truncation
                        if (airport.hoursNotice != null) {
                            put("hours_notice", airport.hoursNotice)
                        }
                        if (airport.notifSummary != null) {
                            put("notice", airport.notifSummary)
                        }
                        put("distance_nm", String.format("%.1f", airport.distanceNm).toDouble())
                        put("country", airport.country)
                    })
                }
            })
        }
        
        return ToolResult.Success(result.toString())
    }
    
    /**
     * Get border crossing (customs) airports, optionally filtered by country
     */
    private fun getBorderCrossingAirports(args: Map<String, Any?>): ToolResult {
        val country = args["country"]?.toString()?.uppercase()
        val limit = (args["limit"] as? Number)?.toInt() ?: 50
        
        val db = airportsDb ?: return ToolResult.Error("Database not initialized")
        
        val sql = if (country != null) {
            """
                SELECT DISTINCT a.icao_code, a.name, a.municipality, a.iso_country, a.latitude_deg, a.longitude_deg
                FROM airports a
                INNER JOIN border_crossing_points bcp ON a.icao_code = bcp.icao_code
                WHERE bcp.country_iso = ?
                LIMIT ?
            """.trimIndent()
        } else {
            """
                SELECT DISTINCT a.icao_code, a.name, a.municipality, a.iso_country, a.latitude_deg, a.longitude_deg
                FROM airports a
                INNER JOIN border_crossing_points bcp ON a.icao_code = bcp.icao_code
                LIMIT ?
            """.trimIndent()
        }
        
        val cursor = if (country != null) {
            db.rawQuery(sql, arrayOf(country, limit.toString()))
        } else {
            db.rawQuery(sql, arrayOf(limit.toString()))
        }
        
        // Build simple text output instead of JSON to prevent LLM hallucinations
        val sb = StringBuilder()
        val countryName = country ?: "All Countries"
        sb.appendLine("Border Crossing Airports in $countryName:")
        sb.appendLine()
        
        var count = 0
        cursor.use {
            while (it.moveToNext()) {
                val icao = it.getString(0)
                val name = it.getStringOrNull(1) ?: "Unknown"
                val city = it.getStringOrNull(2) ?: ""
                val countryCode = it.getStringOrNull(3) ?: ""
                
                // Format: "ICAO - Name (City, Country)"
                val cityCountry = listOfNotNull(
                    city.takeIf { c -> c.isNotBlank() },
                    countryCode.takeIf { c -> c.isNotBlank() }
                ).joinToString(", ")
                
                if (cityCountry.isNotBlank()) {
                    sb.appendLine("- $icao - $name ($cityCountry)")
                } else {
                    sb.appendLine("- $icao - $name")
                }
                count++
            }
        }
        
        sb.appendLine()
        sb.appendLine("Total: $count airports with customs/border crossing facilities.")
        
        return ToolResult.Success(sb.toString())
    }
    
    /**
     * Get customs/immigration notification requirements for a specific airport
     */
    private fun getNotificationForAirport(args: Map<String, Any?>): ToolResult {
        // Accept both 'icao' and 'airport' parameter names (model uses both)
        val icao = (args["icao"]?.toString() ?: args["airport"]?.toString())?.uppercase()
            ?: return ToolResult.Error("Missing 'icao' or 'airport' argument")
        
        val db = notificationsDb
        
        // If notifications DB not available, fall back to AIP entries
        if (db == null) {
            return getAipCustomsInfo(icao)
        }
        
        val sql = """
            SELECT notification_type, hours_notice, summary, 
                   operating_hours_start, operating_hours_end,
                   weekday_rules, contact_info, confidence
            FROM ga_notification_requirements
            WHERE icao = ?
        """.trimIndent()
        
        val cursor = db.rawQuery(sql, arrayOf(icao))
        
        if (!cursor.moveToFirst()) {
            cursor.close()
            // Fall back to AIP customs info
            return getAipCustomsInfo(icao)
        }
        
        val result = buildJsonObject {
            put("icao", icao)
            put("found", true)
            put("notification_type", cursor.getStringOrNull(0))
            put("hours_notice", cursor.getIntOrNull(1))
            put("summary", cursor.getStringOrNull(2))
            put("operating_hours_start", cursor.getStringOrNull(3))
            put("operating_hours_end", cursor.getStringOrNull(4))
            put("weekday_rules", cursor.getStringOrNull(5))
            put("contact_info", cursor.getStringOrNull(6))
            put("confidence", cursor.getDoubleOrNull(7))
        }
        
        cursor.close()
        return ToolResult.Success(result.toString())
    }
    
    /**
     * Fallback: get customs info from AIP entries if notifications DB not available
     */
    private fun getAipCustomsInfo(icao: String): ToolResult {
        val db = airportsDb ?: return ToolResult.Error("Database not initialized")
        
        val sql = """
            SELECT value FROM aip_entries 
            WHERE airport_icao = ? AND std_field = 'Customs and immigration'
        """.trimIndent()
        
        val cursor = db.rawQuery(sql, arrayOf(icao))
        
        val customsInfo = if (cursor.moveToFirst()) {
            cursor.getStringOrNull(0)
        } else null
        
        cursor.close()
        
        val result = buildJsonObject {
            put("icao", icao)
            put("found", customsInfo != null)
            put("customs_info", customsInfo ?: "No customs information available")
            put("source", "aip_entries")
        }
        
        return ToolResult.Success(result.toString())
    }
    
    /**
     * Find airports by notification requirements (e.g., max hours notice, specific country)
     */
    private fun findAirportsByNotification(args: Map<String, Any?>): ToolResult {
        val maxHoursNotice = (args["max_hours"]?.toString() ?: args["max_hours_notice"]?.toString())?.toIntOrNull()
        val country = args["country"]?.toString()?.uppercase()
        val nearLocation = args["near"]?.toString() ?: args["location"]?.toString()
        val limit = (args["limit"] as? Number)?.toInt() ?: 20
        
        Log.d(TAG, "findAirportsByNotification: maxHours=$maxHoursNotice, country=$country, near=$nearLocation")
        
        val notifDb = notificationsDb
        val airportDb = airportsDb ?: return ToolResult.Error("Database not initialized")
        
        if (notifDb == null) {
            return ToolResult.Error("Notifications database not available")
        }
        
        // Build query for notifications - filter by hours_notice if specified
        val sqlNotif = if (maxHoursNotice != null) {
            """
                SELECT icao, hours_notice, summary, operating_hours_start, operating_hours_end
                FROM ga_notification_requirements
                WHERE hours_notice IS NOT NULL AND hours_notice > 0 AND hours_notice <= ?
                ORDER BY hours_notice ASC
                LIMIT ?
            """.trimIndent()
        } else {
            """
                SELECT icao, hours_notice, summary, operating_hours_start, operating_hours_end
                FROM ga_notification_requirements
                WHERE hours_notice IS NOT NULL AND hours_notice > 0
                ORDER BY hours_notice ASC
                LIMIT ?
            """.trimIndent()
        }
        
        val notifCursor = if (maxHoursNotice != null) {
            notifDb.rawQuery(sqlNotif, arrayOf(maxHoursNotice.toString(), limit.toString()))
        } else {
            notifDb.rawQuery(sqlNotif, arrayOf(limit.toString()))
        }
        
        data class NotifAirport(
            val icao: String,
            val hoursNotice: Int?,
            val summary: String?,
            val hoursStart: String?,
            val hoursEnd: String?
        )
        
        val notifAirports = mutableListOf<NotifAirport>()
        notifCursor.use {
            while (it.moveToNext()) {
                val icao = it.getString(0)
                
                // If country filter, check it
                if (country != null && !icao.startsWith(country.take(2))) {
                    continue  // Simple country filter by ICAO prefix
                }
                
                notifAirports.add(NotifAirport(
                    icao = icao,
                    hoursNotice = it.getIntOrNull(1),
                    summary = it.getStringOrNull(2),
                    hoursStart = it.getStringOrNull(3),
                    hoursEnd = it.getStringOrNull(4)
                ))
            }
        }
        
        // Now get airport details for each
        val airports = buildJsonArray {
            for (notif in notifAirports.take(limit)) {
                val airportCursor = airportDb.rawQuery(
                    "SELECT name, municipality, iso_country FROM airports WHERE icao_code = ?",
                    arrayOf(notif.icao)
                )
                
                val (name, city, countryCode) = airportCursor.use {
                    if (it.moveToFirst()) {
                        Triple(it.getStringOrNull(0), it.getStringOrNull(1), it.getStringOrNull(2))
                    } else {
                        Triple(null, null, null)
                    }
                }
                
                add(buildJsonObject {
                    put("icao", notif.icao)
                    put("name", name)
                    put("city", city)
                    put("country", countryCode)
                    put("hours_notice", notif.hoursNotice)
                    put("summary", notif.summary)
                    put("operating_hours", "${notif.hoursStart ?: ""}-${notif.hoursEnd ?: ""}")
                })
            }
        }
        
        val result = buildJsonObject {
            if (maxHoursNotice != null) put("max_hours_notice", maxHoursNotice)
            if (country != null) put("country_filter", country)
            put("count", airports.size)
            put("airports", airports)
        }
        
        Log.d(TAG, "findAirportsByNotification returning ${airports.size} airports")
        return ToolResult.Success(result.toString())
    }
    
    // ========== Cursor Extension Functions ==========
    
    private fun Cursor.getStringOrNull(columnIndex: Int): String? =
        if (isNull(columnIndex)) null else getString(columnIndex)
    
    private fun Cursor.getIntOrNull(columnIndex: Int): Int? =
        if (isNull(columnIndex)) null else getInt(columnIndex)
    
    private fun Cursor.getDoubleOrNull(columnIndex: Int): Double? =
        if (isNull(columnIndex)) null else getDouble(columnIndex)
    
    /**
     * Parse hours notice from summary text patterns like "24h notice", "2h notice", etc.
     * Returns the minimum hours found, or null if none found.
     */
    private fun parseHoursFromSummary(summary: String): Int? {
        // Look for patterns like "24h notice", "2h notice", "48h notice"
        val hourPattern = Regex("(\\d+)h\\s*notice", RegexOption.IGNORE_CASE)
        val matches = hourPattern.findAll(summary)
        val hours = matches.mapNotNull { it.groupValues[1].toIntOrNull() }.toList()
        
        // Return minimum hours if any found
        return hours.minOrNull()
    }
}
