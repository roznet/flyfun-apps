package me.zhaoqian.flyfun.data.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Rules data models matching the API responses.
 */

@Serializable
data class CountryRulesResponse(
    val country: String,
    @SerialName("total_rules") val totalRules: Int,
    val categories: List<RuleCategory>
)

@Serializable
data class RuleCategory(
    val name: String,
    val count: Int,
    val rules: List<RuleEntry>
)

@Serializable
data class RuleEntry(
    @SerialName("question_id") val questionId: String,
    @SerialName("question_text") val questionText: String? = null,
    val category: String,
    val tags: List<String> = emptyList(),
    @SerialName("answer_html") val answerHtml: String? = null,
    val links: List<String> = emptyList(),
    @SerialName("last_reviewed") val lastReviewed: String? = null,
    val confidence: String? = null
)
