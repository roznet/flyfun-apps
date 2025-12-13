package me.zhaoqian.flyfun.viewmodel;

import androidx.lifecycle.ViewModel;
import dagger.hilt.android.lifecycle.HiltViewModel;
import kotlinx.coroutines.flow.*;
import me.zhaoqian.flyfun.data.models.*;
import me.zhaoqian.flyfun.data.repository.FlyFunRepository;
import javax.inject.Inject;

/**
 * ViewModel for the Map screen - manages airport data and filtering.
 */
@kotlin.Metadata(mv = {1, 9, 0}, k = 1, xi = 48, d1 = {"\u0000J\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0010\u000e\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\r\n\u0002\u0010\u0002\n\u0002\b\r\b\u0007\u0018\u00002\u00020\u0001B\u000f\b\u0007\u0012\u0006\u0010\u0002\u001a\u00020\u0003\u00a2\u0006\u0002\u0010\u0004J\u0006\u0010 \u001a\u00020!J\u0006\u0010\"\u001a\u00020!J\u0010\u0010#\u001a\u00020!2\u0006\u0010$\u001a\u00020\u000fH\u0002J\u0006\u0010%\u001a\u00020!J\b\u0010&\u001a\u00020!H\u0002J\u000e\u0010\'\u001a\u00020!2\u0006\u0010(\u001a\u00020\u000fJ\u000e\u0010)\u001a\u00020!2\u0006\u0010*\u001a\u00020\rJ\u000e\u0010+\u001a\u00020!2\u0006\u0010,\u001a\u00020\u000fJ\u000e\u0010-\u001a\u00020!2\u0006\u0010\u0016\u001a\u00020\tR\u0016\u0010\u0005\u001a\n\u0012\u0006\u0012\u0004\u0018\u00010\u00070\u0006X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u0014\u0010\b\u001a\b\u0012\u0004\u0012\u00020\t0\u0006X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u0016\u0010\n\u001a\n\u0012\u0006\u0012\u0004\u0018\u00010\u000b0\u0006X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u0016\u0010\f\u001a\n\u0012\u0006\u0012\u0004\u0018\u00010\r0\u0006X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u0014\u0010\u000e\u001a\b\u0012\u0004\u0012\u00020\u000f0\u0006X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u0014\u0010\u0010\u001a\b\u0012\u0004\u0012\u00020\u00110\u0006X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u0019\u0010\u0012\u001a\n\u0012\u0006\u0012\u0004\u0018\u00010\u00070\u0013\u00a2\u0006\b\n\u0000\u001a\u0004\b\u0014\u0010\u0015R\u0017\u0010\u0016\u001a\b\u0012\u0004\u0012\u00020\t0\u0013\u00a2\u0006\b\n\u0000\u001a\u0004\b\u0017\u0010\u0015R\u0019\u0010\u0018\u001a\n\u0012\u0006\u0012\u0004\u0018\u00010\u000b0\u0013\u00a2\u0006\b\n\u0000\u001a\u0004\b\u0019\u0010\u0015R\u000e\u0010\u0002\u001a\u00020\u0003X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u0019\u0010\u001a\u001a\n\u0012\u0006\u0012\u0004\u0018\u00010\r0\u0013\u00a2\u0006\b\n\u0000\u001a\u0004\b\u001b\u0010\u0015R\u0017\u0010\u001c\u001a\b\u0012\u0004\u0012\u00020\u000f0\u0013\u00a2\u0006\b\n\u0000\u001a\u0004\b\u001d\u0010\u0015R\u0017\u0010\u001e\u001a\b\u0012\u0004\u0012\u00020\u00110\u0013\u00a2\u0006\b\n\u0000\u001a\u0004\b\u001f\u0010\u0015\u00a8\u0006."}, d2 = {"Lme/zhaoqian/flyfun/viewmodel/MapViewModel;", "Landroidx/lifecycle/ViewModel;", "repository", "Lme/zhaoqian/flyfun/data/repository/FlyFunRepository;", "(Lme/zhaoqian/flyfun/data/repository/FlyFunRepository;)V", "_airportDetail", "Lkotlinx/coroutines/flow/MutableStateFlow;", "Lme/zhaoqian/flyfun/data/models/AirportDetail;", "_filters", "Lme/zhaoqian/flyfun/viewmodel/AirportFilters;", "_gaConfig", "Lme/zhaoqian/flyfun/data/models/GAConfig;", "_selectedAirport", "Lme/zhaoqian/flyfun/data/models/Airport;", "_selectedPersona", "", "_uiState", "Lme/zhaoqian/flyfun/viewmodel/MapUiState;", "airportDetail", "Lkotlinx/coroutines/flow/StateFlow;", "getAirportDetail", "()Lkotlinx/coroutines/flow/StateFlow;", "filters", "getFilters", "gaConfig", "getGaConfig", "selectedAirport", "getSelectedAirport", "selectedPersona", "getSelectedPersona", "uiState", "getUiState", "clearFilters", "", "clearSelectedAirport", "loadAirportDetail", "icao", "loadAirports", "loadGAConfig", "searchAirports", "query", "selectAirport", "airport", "setSelectedPersona", "personaId", "updateFilters", "app_debug"})
@dagger.hilt.android.lifecycle.HiltViewModel()
public final class MapViewModel extends androidx.lifecycle.ViewModel {
    @org.jetbrains.annotations.NotNull()
    private final me.zhaoqian.flyfun.data.repository.FlyFunRepository repository = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.MutableStateFlow<me.zhaoqian.flyfun.viewmodel.MapUiState> _uiState = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.viewmodel.MapUiState> uiState = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.MutableStateFlow<me.zhaoqian.flyfun.data.models.Airport> _selectedAirport = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.data.models.Airport> selectedAirport = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.MutableStateFlow<me.zhaoqian.flyfun.data.models.AirportDetail> _airportDetail = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.data.models.AirportDetail> airportDetail = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.MutableStateFlow<me.zhaoqian.flyfun.viewmodel.AirportFilters> _filters = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.viewmodel.AirportFilters> filters = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.MutableStateFlow<me.zhaoqian.flyfun.data.models.GAConfig> _gaConfig = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.data.models.GAConfig> gaConfig = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.MutableStateFlow<java.lang.String> _selectedPersona = null;
    @org.jetbrains.annotations.NotNull()
    private final kotlinx.coroutines.flow.StateFlow<java.lang.String> selectedPersona = null;
    
    @javax.inject.Inject()
    public MapViewModel(@org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.data.repository.FlyFunRepository repository) {
        super();
    }
    
    @org.jetbrains.annotations.NotNull()
    public final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.viewmodel.MapUiState> getUiState() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.data.models.Airport> getSelectedAirport() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.data.models.AirportDetail> getAirportDetail() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.viewmodel.AirportFilters> getFilters() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final kotlinx.coroutines.flow.StateFlow<me.zhaoqian.flyfun.data.models.GAConfig> getGaConfig() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final kotlinx.coroutines.flow.StateFlow<java.lang.String> getSelectedPersona() {
        return null;
    }
    
    public final void loadAirports() {
    }
    
    private final void loadGAConfig() {
    }
    
    public final void selectAirport(@org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.data.models.Airport airport) {
    }
    
    public final void clearSelectedAirport() {
    }
    
    private final void loadAirportDetail(java.lang.String icao) {
    }
    
    public final void updateFilters(@org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.viewmodel.AirportFilters filters) {
    }
    
    public final void clearFilters() {
    }
    
    public final void setSelectedPersona(@org.jetbrains.annotations.NotNull()
    java.lang.String personaId) {
    }
    
    public final void searchAirports(@org.jetbrains.annotations.NotNull()
    java.lang.String query) {
    }
}