package me.zhaoqian.flyfun.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.launch
import me.zhaoqian.flyfun.data.models.*
import me.zhaoqian.flyfun.data.repository.FlyFunRepository
import javax.inject.Inject

/**
 * ViewModel for the Map screen - manages airport data and filtering.
 */
@HiltViewModel
class MapViewModel @Inject constructor(
    private val repository: FlyFunRepository
) : ViewModel() {
    
    // UI State
    private val _uiState = MutableStateFlow(MapUiState())
    val uiState: StateFlow<MapUiState> = _uiState.asStateFlow()
    
    // Selected airport for detail view
    private val _selectedAirport = MutableStateFlow<Airport?>(null)
    val selectedAirport: StateFlow<Airport?> = _selectedAirport.asStateFlow()
    
    // Airport detail (full info)
    private val _airportDetail = MutableStateFlow<AirportDetail?>(null)
    val airportDetail: StateFlow<AirportDetail?> = _airportDetail.asStateFlow()
    
    // Filters
    private val _filters = MutableStateFlow(AirportFilters())
    val filters: StateFlow<AirportFilters> = _filters.asStateFlow()
    
    // GA Config
    private val _gaConfig = MutableStateFlow<GAConfig?>(null)
    val gaConfig: StateFlow<GAConfig?> = _gaConfig.asStateFlow()
    
    // Selected persona
    private val _selectedPersona = MutableStateFlow("ifr_touring_sr22")
    val selectedPersona: StateFlow<String> = _selectedPersona.asStateFlow()
    
    init {
        loadAirports()
        loadGAConfig()
    }
    
    fun loadAirports() {
        viewModelScope.launch {
            _uiState.update { it.copy(isLoading = true, error = null) }
            
            val currentFilters = _filters.value
            repository.getAirports(
                country = currentFilters.country,
                hasProcedure = currentFilters.procedureType,
                hasIls = currentFilters.hasIls,
                pointOfEntry = currentFilters.pointOfEntry,
                runwayMinLength = currentFilters.runwayMinLength,
                search = currentFilters.searchQuery
            ).fold(
                onSuccess = { response ->
                    _uiState.update { 
                        it.copy(
                            isLoading = false,
                            airports = response.airports,
                            totalCount = response.total
                        )
                    }
                },
                onFailure = { error ->
                    _uiState.update { 
                        it.copy(
                            isLoading = false,
                            error = error.message ?: "Failed to load airports"
                        )
                    }
                }
            )
        }
    }
    
    private fun loadGAConfig() {
        viewModelScope.launch {
            repository.getGAConfig().onSuccess { config ->
                _gaConfig.value = config
                _selectedPersona.value = config.defaultPersona
            }
        }
    }
    
    fun selectAirport(airport: Airport) {
        _selectedAirport.value = airport
        loadAirportDetail(airport.icao)
    }
    
    fun clearSelectedAirport() {
        _selectedAirport.value = null
        _airportDetail.value = null
    }
    
    private fun loadAirportDetail(icao: String) {
        viewModelScope.launch {
            repository.getAirportDetail(icao).onSuccess { detail ->
                _airportDetail.value = detail
            }
        }
    }
    
    fun updateFilters(filters: AirportFilters) {
        _filters.value = filters
        loadAirports()
    }
    
    fun clearFilters() {
        _filters.value = AirportFilters()
        loadAirports()
    }
    
    fun setSelectedPersona(personaId: String) {
        _selectedPersona.value = personaId
    }
    
    fun searchAirports(query: String) {
        viewModelScope.launch {
            if (query.length >= 2) {
                repository.searchAirports(query).onSuccess { results ->
                    _uiState.update { it.copy(searchResults = results) }
                }
            } else {
                _uiState.update { it.copy(searchResults = emptyList()) }
            }
        }
    }
}

data class MapUiState(
    val isLoading: Boolean = false,
    val airports: List<Airport> = emptyList(),
    val totalCount: Int = 0,
    val error: String? = null,
    val searchResults: List<Airport> = emptyList()
)

data class AirportFilters(
    val country: String? = null,
    val procedureType: String? = null,
    val hasIls: Boolean? = null,
    val pointOfEntry: Boolean? = null,
    val runwayMinLength: Int? = null,
    val searchQuery: String? = null
)
