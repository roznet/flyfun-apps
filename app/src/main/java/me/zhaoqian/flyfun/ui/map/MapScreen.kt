package me.zhaoqian.flyfun.ui.map

import android.content.Context
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.hilt.navigation.compose.hiltViewModel
import me.zhaoqian.flyfun.data.models.Airport
import me.zhaoqian.flyfun.ui.airport.AirportDetailSheet
import me.zhaoqian.flyfun.ui.theme.*
import me.zhaoqian.flyfun.viewmodel.MapViewModel
import org.osmdroid.config.Configuration
import org.osmdroid.tileprovider.tilesource.TileSourceFactory
import org.osmdroid.util.GeoPoint
import org.osmdroid.views.MapView
import org.osmdroid.views.overlay.Marker

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MapScreen(
    onNavigateToChat: () -> Unit,
    viewModel: MapViewModel = hiltViewModel()
) {
    val context = LocalContext.current
    val uiState by viewModel.uiState.collectAsState()
    val selectedAirport by viewModel.selectedAirport.collectAsState()
    val airportDetail by viewModel.airportDetail.collectAsState()
    val filters by viewModel.filters.collectAsState()
    val selectedPersona by viewModel.selectedPersona.collectAsState()
    val gaConfig by viewModel.gaConfig.collectAsState()
    
    // Sheet state for airport details
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = false)
    
    var showFiltersDialog by remember { mutableStateOf(false) }
    
    // Initialize osmdroid configuration
    LaunchedEffect(Unit) {
        Configuration.getInstance().load(context, context.getSharedPreferences("osmdroid", Context.MODE_PRIVATE))
        Configuration.getInstance().userAgentValue = "FlyFun/1.0"
    }
    
    Box(modifier = Modifier.fillMaxSize()) {
        // OpenStreetMap using osmdroid
        OsmMapView(
            airports = uiState.airports,
            selectedPersona = selectedPersona,
            onAirportClick = { airport -> viewModel.selectAirport(airport) },
            modifier = Modifier.fillMaxSize()
        )
        
        // Top bar with search and filters
        TopAppBar(
            modifier = Modifier.align(Alignment.TopCenter),
            showFiltersDialog = showFiltersDialog,
            onFilterClick = { showFiltersDialog = true },
            onSearchClick = { /* TODO: Show search */ },
            totalAirports = uiState.totalCount,
            isLoading = uiState.isLoading
        )
        
        // Floating action button for chat
        FloatingActionButton(
            onClick = onNavigateToChat,
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .padding(16.dp),
            containerColor = MaterialTheme.colorScheme.primary
        ) {
            Icon(
                imageVector = Icons.Default.Chat,
                contentDescription = "Open Assistant"
            )
        }
        
        // Loading indicator
        if (uiState.isLoading) {
            CircularProgressIndicator(
                modifier = Modifier
                    .align(Alignment.Center)
                    .padding(16.dp)
            )
        }
        
        // Error message
        uiState.error?.let { error ->
            Snackbar(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .padding(16.dp)
            ) {
                Text(error)
            }
        }
    }
    
    // Airport detail bottom sheet
    if (selectedAirport != null) {
        ModalBottomSheet(
            onDismissRequest = { viewModel.clearSelectedAirport() },
            sheetState = sheetState
        ) {
            AirportDetailSheet(
                airport = selectedAirport!!,
                airportDetail = airportDetail,
                selectedPersona = selectedPersona,
                onPersonaChange = { viewModel.setSelectedPersona(it) },
                onDismiss = { viewModel.clearSelectedAirport() }
            )
        }
    }
    
    // Filters dialog
    if (showFiltersDialog) {
        FiltersDialog(
            currentFilters = filters,
            onApply = { newFilters ->
                viewModel.updateFilters(newFilters)
                showFiltersDialog = false
            },
            onClear = {
                viewModel.clearFilters()
                showFiltersDialog = false
            },
            onDismiss = { showFiltersDialog = false }
        )
    }
}

@Composable
private fun OsmMapView(
    airports: List<Airport>,
    selectedPersona: String,
    onAirportClick: (Airport) -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    
    // Remember map view to avoid recreation
    val mapView = remember {
        MapView(context).apply {
            setTileSource(TileSourceFactory.MAPNIK)
            setMultiTouchControls(true)
            controller.setZoom(5.0)
            controller.setCenter(GeoPoint(48.8, 9.0)) // Center on Europe
        }
    }
    
    // Update markers when airports change
    LaunchedEffect(airports, selectedPersona) {
        mapView.overlays.clear()
        
        airports.forEach { airport ->
            val marker = Marker(mapView).apply {
                position = GeoPoint(airport.latitude, airport.longitude)
                title = airport.name
                snippet = airport.icao
                setAnchor(Marker.ANCHOR_CENTER, Marker.ANCHOR_BOTTOM)
                
                // Set marker color based on features/score
                // Note: osmdroid uses default markers, but we can customize
                setOnMarkerClickListener { _, _ ->
                    onAirportClick(airport)
                    true
                }
            }
            mapView.overlays.add(marker)
        }
        mapView.invalidate()
    }
    
    // Cleanup
    DisposableEffect(Unit) {
        onDispose {
            mapView.onDetach()
        }
    }
    
    AndroidView(
        factory = { mapView },
        modifier = modifier
    )
}

@Composable
private fun TopAppBar(
    modifier: Modifier = Modifier,
    showFiltersDialog: Boolean,
    onFilterClick: () -> Unit,
    onSearchClick: () -> Unit,
    totalAirports: Int,
    isLoading: Boolean
) {
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .padding(16.dp),
        shape = RoundedCornerShape(12.dp),
        tonalElevation = 4.dp
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            // App title
            Text(
                text = "✈️ FlyFun",
                style = MaterialTheme.typography.titleLarge
            )
            
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                // Airport count
                Text(
                    text = if (isLoading) "Loading..." else "$totalAirports airports",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                
                // Search button
                IconButton(onClick = onSearchClick) {
                    Icon(Icons.Default.Search, contentDescription = "Search")
                }
                
                // Filter button
                IconButton(onClick = onFilterClick) {
                    Icon(Icons.Default.FilterList, contentDescription = "Filters")
                }
            }
        }
    }
}
