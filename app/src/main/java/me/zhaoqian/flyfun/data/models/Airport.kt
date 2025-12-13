package me.zhaoqian.flyfun.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Airport data models matching the API responses.
 */

@Serializable
data class Airport(
    val icao: String,
    val name: String,
    val country: String,
    val latitude: Double,
    val longitude: Double,
    @SerialName("elevation_ft") val elevationFt: Int? = null,
    @SerialName("has_ils") val hasIls: Boolean = false,
    @SerialName("has_vor") val hasVor: Boolean = false,
    @SerialName("point_of_entry") val pointOfEntry: Boolean = false,
    @SerialName("ga_scores") val gaScores: Map<String, Double>? = null,
    @SerialName("ga_summary") val gaSummary: GASummary? = null
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
