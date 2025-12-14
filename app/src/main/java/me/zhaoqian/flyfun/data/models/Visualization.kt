package me.zhaoqian.flyfun.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

/**
 * Wrapper for the ui_payload SSE event data.
 * The actual payload is nested: {"ui_payload": {...}}
 */
@Serializable
data class UiPayloadWrapper(
    @SerialName("ui_payload")
    val uiPayload: VisualizationPayload? = null
)

/**
 * Payload from ui_payload SSE event containing visualization instructions.
 */
@Serializable
data class VisualizationPayload(
    val kind: String? = null,
    @SerialName("mcp_raw")
    val mcpRaw: McpRaw? = null,
    val visualization: VisualizationData? = null,
    val airports: List<MarkerData>? = null
)

@Serializable
data class McpRaw(
    val count: Int? = null,
    val airports: List<MarkerData>? = null
)

@Serializable
data class VisualizationData(
    val type: String? = null,
    val route: RouteData? = null,
    val markers: List<MarkerData>? = null,
    @SerialName("filter_profile")
    val filterProfile: FilterProfile? = null
)

@Serializable
data class RouteData(
    val from: RoutePoint? = null,
    val to: RoutePoint? = null
)

@Serializable
data class RoutePoint(
    val icao: String? = null,
    val lat: Double? = null,
    val lon: Double? = null
)

@Serializable
data class MarkerData(
    val icao: String? = null,
    val ident: String? = null,
    val name: String? = null,
    @SerialName("latitude_deg")
    val latitude: Double? = null,
    @SerialName("longitude_deg")
    val longitude: Double? = null,
    val country: String? = null,
    @SerialName("distance_nm")
    val distanceNm: Double? = null,
    @SerialName("enroute_distance_nm")
    val enrouteDistanceNm: Double? = null,
    @SerialName("point_of_entry")
    val pointOfEntry: Boolean? = null,
    @SerialName("has_procedures")
    val hasProcedures: Boolean? = null,
    @SerialName("has_hard_runway")
    val hasHardRunway: Boolean? = null
)

@Serializable
data class FilterProfile(
    @SerialName("route_distance")
    val routeDistance: Double? = null,
    @SerialName("has_avgas")
    val hasAvgas: Boolean? = null,
    @SerialName("has_hard_runway")
    val hasHardRunway: Boolean? = null,
    @SerialName("point_of_entry")
    val pointOfEntry: Boolean? = null
)

/**
 * Simplified route visualization for the map.
 */
/**
 * Simplified route visualization for the map.
 */
data class RouteVisualization(
    val fromLat: Double,
    val fromLon: Double,
    val toLat: Double,
    val toLon: Double,
    val fromIcao: String,
    val toIcao: String,
    val highlightedAirports: List<String> = emptyList(),
    val airports: List<me.zhaoqian.flyfun.data.models.Airport> = emptyList()
)
