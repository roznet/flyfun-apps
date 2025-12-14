package me.zhaoqian.flyfun.data.api

import me.zhaoqian.flyfun.data.models.*
import retrofit2.http.*

/**
 * FlyFun API service interface for all endpoints.
 */
interface FlyFunApiService {
    
    // ========== Airports ==========
    
    @GET("api/airports/")
    suspend fun getAirports(
        @Query("country") country: String? = null,
        @Query("has_procedure") hasProcedure: String? = null,
        @Query("has_ils") hasIls: Boolean? = null,
        @Query("point_of_entry") pointOfEntry: Boolean? = null,
        @Query("runway_min_length") runwayMinLength: Int? = null,
        @Query("search") search: String? = null,
        @Query("limit") limit: Int = 10000,
        @Query("offset") offset: Int = 0,
        @Query("include_ga") includeGa: Boolean = true
    ): List<Airport>
    
    @GET("api/airports/{icao}/")
    suspend fun getAirportDetail(
        @Path("icao") icao: String
    ): AirportDetail
    
    @GET("api/airports/{icao}/aip/")
    suspend fun getAirportAipEntries(
        @Path("icao") icao: String,
        @Query("section") section: String? = null,
        @Query("std_field") stdField: String? = null
    ): List<AipEntry>
    
    @GET("api/airports/{icao}/procedures/")
    suspend fun getAirportProcedures(
        @Path("icao") icao: String,
        @Query("procedure_type") procedureType: String? = null,
        @Query("runway") runway: String? = null
    ): List<Procedure>
    
    @GET("api/airports/{icao}/runways/")
    suspend fun getAirportRunways(
        @Path("icao") icao: String
    ): List<Runway>
    
    @GET("api/airports/search/{query}/")
    suspend fun searchAirports(
        @Path("query") query: String,
        @Query("limit") limit: Int = 20
    ): List<Airport>
    
    // ========== Rules ==========
    
    @GET("api/rules/{country_code}/")
    suspend fun getCountryRules(
        @Path("country_code") countryCode: String
    ): CountryRulesResponse
    
    // ========== GA Friendliness ==========
    
    @GET("api/ga/config/")
    suspend fun getGAConfig(): GAConfig
    
    @GET("api/ga/personas/")
    suspend fun getGAPersonas(): List<Persona>
    
    @GET("api/ga/summary/{icao}/")
    suspend fun getGASummary(
        @Path("icao") icao: String,
        @Query("persona") persona: String = "ifr_touring_sr22"
    ): GADetailedSummary
    
    // ========== Chat ==========
    
    @POST("api/aviation-agent/chat")
    suspend fun chat(
        @Body request: ChatRequest
    ): ChatResponse
}
