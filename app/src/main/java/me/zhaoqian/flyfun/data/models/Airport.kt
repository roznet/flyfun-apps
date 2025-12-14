package me.zhaoqian.flyfun.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Airport data models matching the API responses.
 */

@Serializable
data class Airport(
    @SerialName("ident") val icao: String,
    val name: String? = null,
    @SerialName("iso_country") val country: String? = null,
    @SerialName("latitude_deg") val latitude: Double? = null,
    @SerialName("longitude_deg") val longitude: Double? = null,
    val municipality: String? = null,
    @SerialName("point_of_entry") val pointOfEntry: Boolean? = null,
    @SerialName("has_procedures") val hasProcedures: Boolean = false,
    @SerialName("has_runways") val hasRunways: Boolean = false,
    @SerialName("has_aip_data") val hasAipData: Boolean = false,
    @SerialName("has_hard_runway") val hasHardRunway: Boolean = false,
    @SerialName("has_lighted_runway") val hasLightedRunway: Boolean = false,
    @SerialName("has_soft_runway") val hasSoftRunway: Boolean = false,
    @SerialName("has_water_runway") val hasWaterRunway: Boolean = false,
    @SerialName("has_snow_runway") val hasSnowRunway: Boolean = false,
    @SerialName("longest_runway_length_ft") val longestRunwayLengthFt: Int? = null,
    @SerialName("procedure_count") val procedureCount: Int = 0,
    @SerialName("runway_count") val runwayCount: Int = 0,
    @SerialName("aip_entry_count") val aipEntryCount: Int = 0,
    val ga: GASummary? = null
)

@Serializable
data class GASummary(
    @SerialName("has_data") val hasData: Boolean = false,
    val score: Double? = null,
    val features: Map<String, Double?>? = null,
    @SerialName("review_count") val reviewCount: Int = 0,
    val tags: List<String>? = null,
    @SerialName("summary_text") val summaryText: String? = null,
    @SerialName("hassle_level") val hassleLevel: String? = null
)

@Serializable
data class AirportDetail(
    val icao: String,
    val name: String,
    val country: String,
    val latitude: Double,
    val longitude: Double,
    @SerialName("elevation_ft") val elevationFt: Int? = null,
    val runways: List<Runway> = emptyList(),
    val procedures: List<Procedure> = emptyList(),
    @SerialName("aip_entries") val aipEntries: List<AipEntry> = emptyList()
)

@Serializable
data class Runway(
    val identifier: String,
    @SerialName("length_ft") val lengthFt: Int? = null,
    @SerialName("width_ft") val widthFt: Int? = null,
    val surface: String? = null,
    val lighted: Boolean = false
)

@Serializable
data class Procedure(
    val type: String,
    val name: String,
    val runway: String? = null
)

@Serializable
data class AipEntry(
    val section: String,
    @SerialName("std_field") val stdField: String? = null,
    val content: String,
    val source: String? = null
)

@Serializable
data class AirportsResponse(
    val airports: List<Airport>,
    val total: Int,
    val offset: Int,
    val limit: Int
)
