package me.zhaoqian.flyfun.data.repository

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import me.zhaoqian.flyfun.data.models.RouteVisualization
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Shared state holder for route visualization from chat.
 * Used to communicate route data between ChatViewModel and MapViewModel.
 */
@Singleton
class RouteStateHolder @Inject constructor() {
    
    private val _routeVisualization = MutableStateFlow<RouteVisualization?>(null)
    val routeVisualization: StateFlow<RouteVisualization?> = _routeVisualization.asStateFlow()
    
    fun setRouteVisualization(route: RouteVisualization?) {
        _routeVisualization.value = route
    }
    
    fun clearRouteVisualization() {
        _routeVisualization.value = null
    }
}
