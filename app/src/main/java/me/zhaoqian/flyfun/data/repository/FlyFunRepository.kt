package me.zhaoqian.flyfun.data.repository

import kotlinx.coroutines.flow.Flow
import me.zhaoqian.flyfun.data.api.ChatStreamingClient
import me.zhaoqian.flyfun.data.api.FlyFunApiService
import me.zhaoqian.flyfun.data.models.*
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton

/**
 * Main repository for FlyFun data access.
 * Wraps API calls with error handling and caching.
 */
@Singleton
class FlyFunRepository @Inject constructor(
    private val apiService: FlyFunApiService,
    private val chatStreamingClient: ChatStreamingClient,
    @Named("baseUrl") private val baseUrl: String
) {
    
    // ========== Airports ==========
    
    suspend fun getAirports(
        country: String? = null,
        hasProcedure: String? = null,
        hasIls: Boolean? = null,
        pointOfEntry: Boolean? = null,
        runwayMinLength: Int? = null,
        search: String? = null,
        limit: Int = 10000,
        offset: Int = 0
    ): Result<List<Airport>> = runCatching {
        apiService.getAirports(
            country = country,
            hasProcedure = hasProcedure,
            hasIls = hasIls,
            pointOfEntry = pointOfEntry,
            runwayMinLength = runwayMinLength,
            search = search,
            limit = limit,
            offset = offset
        )
    }
    
    suspend fun getAirportDetail(icao: String): Result<AirportDetail> = runCatching {
        apiService.getAirportDetail(icao)
    }
    
    suspend fun getAirportAipEntries(
        icao: String,
        section: String? = null
    ): Result<List<AipEntry>> = runCatching {
        apiService.getAirportAipEntries(icao, section)
    }
    
    suspend fun getAirportProcedures(icao: String): Result<List<Procedure>> = runCatching {
        apiService.getAirportProcedures(icao)
    }
    
    suspend fun getAirportRunways(icao: String): Result<List<Runway>> = runCatching {
        apiService.getAirportRunways(icao)
    }
    
    suspend fun searchAirports(query: String, limit: Int = 20): Result<List<Airport>> = runCatching {
        apiService.searchAirports(query, limit)
    }
    
    // ========== Rules ==========
    
    suspend fun getCountryRules(countryCode: String): Result<CountryRulesResponse> = runCatching {
        apiService.getCountryRules(countryCode)
    }
    
    // ========== GA Friendliness ==========
    
    suspend fun getGAConfig(): Result<GAConfig> = runCatching {
        apiService.getGAConfig()
    }
    
    suspend fun getGAPersonas(): Result<List<Persona>> = runCatching {
        apiService.getGAPersonas()
    }
    
    suspend fun getGASummary(icao: String, persona: String): Result<GADetailedSummary> = runCatching {
        apiService.getGASummary(icao, persona)
    }
    
    // ========== Chat ==========
    
    suspend fun chat(request: ChatRequest): Result<ChatResponse> = runCatching {
        apiService.chat(request)
    }
    
    fun streamChat(request: ChatRequest): Flow<ChatStreamEvent> {
        return chatStreamingClient.streamChat(baseUrl, request)
    }
}
