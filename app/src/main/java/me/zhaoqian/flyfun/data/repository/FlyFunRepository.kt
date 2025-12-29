package me.zhaoqian.flyfun.data.repository

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import me.zhaoqian.flyfun.data.api.ChatStreamingClient
import me.zhaoqian.flyfun.data.api.FlyFunApiService
import me.zhaoqian.flyfun.data.models.*
import me.zhaoqian.flyfun.offline.ModelManager
import me.zhaoqian.flyfun.offline.OfflineChatClient
import javax.inject.Inject
import javax.inject.Named
import javax.inject.Singleton

/**
 * Main repository for FlyFun data access.
 * Wraps API calls with error handling and caching.
 * Supports offline mode with local LLM inference.
 */
@Singleton
class FlyFunRepository @Inject constructor(
    private val apiService: FlyFunApiService,
    private val chatStreamingClient: ChatStreamingClient,
    private val offlineChatClient: OfflineChatClient,
    private val modelManager: ModelManager,
    @ApplicationContext private val context: Context,
    @Named("baseUrl") private val baseUrl: String
) {
    
    // ========== Offline Mode ==========
    
    /** Force offline mode for testing (overrides network detection) */
    private val _forceOfflineMode = MutableStateFlow(false)
    val forceOfflineMode: StateFlow<Boolean> = _forceOfflineMode.asStateFlow()
    
    /** Current effective offline state (forced or network unavailable) */
    private val _isOffline = MutableStateFlow(false)
    val isOffline: StateFlow<Boolean> = _isOffline.asStateFlow()
    
    /**
     * Toggle forced offline mode for testing.
     * When enabled, uses local model even if network is available.
     */
    fun setForceOfflineMode(enabled: Boolean) {
        _forceOfflineMode.value = enabled
        updateOfflineState()
    }
    
    /**
     * Check if offline mode is available (model downloaded + device supported)
     */
    fun isOfflineModeAvailable(): Boolean {
        return modelManager.isOfflineModeAvailable()
    }
    
    /**
     * Check current network connectivity
     */
    fun isNetworkAvailable(): Boolean {
        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivityManager.activeNetwork ?: return false
        val capabilities = connectivityManager.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
    }
    
    /**
     * Update the offline state based on network and force toggle
     */
    private fun updateOfflineState() {
        val shouldUseOffline = _forceOfflineMode.value || !isNetworkAvailable()
        _isOffline.value = shouldUseOffline && isOfflineModeAvailable()
    }
    
    // ========== Airports ==========
    
    suspend fun getAirports(
        country: String? = null,
        hasProcedure: String? = null,
        hasIls: Boolean? = null,
        pointOfEntry: Boolean? = null,
        runwayMinLength: Int? = null,
        search: String? = null,
        hasProcedures: Boolean? = null,
        hasAipData: Boolean? = null,
        hasHardRunway: Boolean? = null,
        aipField: String? = null,
        aipValue: String? = null,
        aipOperator: String? = null,
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
            hasProcedures = hasProcedures,
            hasAipData = hasAipData,
            hasHardRunway = hasHardRunway,
            aipField = aipField,
            aipValue = aipValue,
            aipOperator = aipOperator,
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
    
    suspend fun searchAirportsNearRoute(
        airports: List<String>,
        distanceNm: Double = 50.0
    ): Result<RouteSearchResponse> = runCatching {
        apiService.searchAirportsNearRoute(
            airports = airports.joinToString(","),
            distanceNm = distanceNm
        )
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
    
    /**
     * Stream chat with automatic offline fallback.
     * 
     * Uses local model if:
     * - forceOfflineMode is enabled (for testing)
     * - Network is unavailable AND offline mode is available
     */
    fun streamChat(request: ChatRequest): Flow<ChatStreamEvent> {
        updateOfflineState()
        
        return if (_isOffline.value) {
            // Use offline local inference
            offlineChatClient.streamChat(request)
        } else {
            // Use online API
            chatStreamingClient.streamChat(baseUrl, request)
        }
    }
}

