package me.zhaoqian.flyfun.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * GA Friendliness data models.
 */

@Serializable
data class GAConfig(
    @SerialName("feature_names") val featureNames: List<String>,
    @SerialName("feature_display_names") val featureDisplayNames: Map<String, String>,
    @SerialName("feature_descriptions") val featureDescriptions: Map<String, String>,
    @SerialName("relevance_buckets") val relevanceBuckets: List<RelevanceBucket>,
    val personas: List<Persona>,
    @SerialName("default_persona") val defaultPersona: String,
    val version: String
)

@Serializable
data class RelevanceBucket(
    val id: String,
    val label: String,
    val color: String,
    @SerialName("min_score") val minScore: Double,
    @SerialName("max_score") val maxScore: Double
)

@Serializable
data class Persona(
    val id: String,
    val label: String,
    val description: String,
    val weights: Map<String, Double>
)

@Serializable
data class GADetailedSummary(
    val icao: String,
    @SerialName("has_data") val hasData: Boolean = false,
    val score: Double? = null,
    val features: Map<String, Double?>? = null,
    @SerialName("review_count") val reviewCount: Int = 0,
    val tags: List<String>? = null,
    @SerialName("summary_text") val summaryText: String? = null,
    @SerialName("notification_summary") val notificationSummary: String? = null,
    @SerialName("hassle_level") val hassleLevel: String? = null,
    @SerialName("hotel_info") val hotelInfo: String? = null,
    @SerialName("restaurant_info") val restaurantInfo: String? = null
)
