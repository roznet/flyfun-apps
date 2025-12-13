package me.zhaoqian.flyfun.ui.map;

import android.content.Context;
import androidx.compose.foundation.layout.*;
import androidx.compose.material.icons.Icons;
import androidx.compose.material.icons.filled.*;
import androidx.compose.material3.*;
import androidx.compose.runtime.*;
import androidx.compose.ui.Alignment;
import androidx.compose.ui.Modifier;
import me.zhaoqian.flyfun.data.models.Airport;
import me.zhaoqian.flyfun.ui.theme.*;
import me.zhaoqian.flyfun.viewmodel.MapViewModel;
import org.osmdroid.config.Configuration;
import org.osmdroid.tileprovider.tilesource.TileSourceFactory;
import org.osmdroid.util.GeoPoint;
import org.osmdroid.views.MapView;
import org.osmdroid.views.overlay.Marker;

@kotlin.Metadata(mv = {1, 9, 0}, k = 2, xi = 48, d1 = {"\u0000D\n\u0000\n\u0002\u0010\u0002\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0010 \n\u0002\u0018\u0002\n\u0000\n\u0002\u0010\u000e\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0010\u000b\n\u0002\b\u0003\n\u0002\u0010\b\n\u0002\b\u0002\u001a \u0010\u0000\u001a\u00020\u00012\f\u0010\u0002\u001a\b\u0012\u0004\u0012\u00020\u00010\u00032\b\b\u0002\u0010\u0004\u001a\u00020\u0005H\u0007\u001a<\u0010\u0006\u001a\u00020\u00012\f\u0010\u0007\u001a\b\u0012\u0004\u0012\u00020\t0\b2\u0006\u0010\n\u001a\u00020\u000b2\u0012\u0010\f\u001a\u000e\u0012\u0004\u0012\u00020\t\u0012\u0004\u0012\u00020\u00010\r2\b\b\u0002\u0010\u000e\u001a\u00020\u000fH\u0003\u001aF\u0010\u0010\u001a\u00020\u00012\b\b\u0002\u0010\u000e\u001a\u00020\u000f2\u0006\u0010\u0011\u001a\u00020\u00122\f\u0010\u0013\u001a\b\u0012\u0004\u0012\u00020\u00010\u00032\f\u0010\u0014\u001a\b\u0012\u0004\u0012\u00020\u00010\u00032\u0006\u0010\u0015\u001a\u00020\u00162\u0006\u0010\u0017\u001a\u00020\u0012H\u0003\u00a8\u0006\u0018"}, d2 = {"MapScreen", "", "onNavigateToChat", "Lkotlin/Function0;", "viewModel", "Lme/zhaoqian/flyfun/viewmodel/MapViewModel;", "OsmMapView", "airports", "", "Lme/zhaoqian/flyfun/data/models/Airport;", "selectedPersona", "", "onAirportClick", "Lkotlin/Function1;", "modifier", "Landroidx/compose/ui/Modifier;", "TopAppBar", "showFiltersDialog", "", "onFilterClick", "onSearchClick", "totalAirports", "", "isLoading", "app_debug"})
public final class MapScreenKt {
    
    @kotlin.OptIn(markerClass = {androidx.compose.material3.ExperimentalMaterial3Api.class})
    @androidx.compose.runtime.Composable()
    public static final void MapScreen(@org.jetbrains.annotations.NotNull()
    kotlin.jvm.functions.Function0<kotlin.Unit> onNavigateToChat, @org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.viewmodel.MapViewModel viewModel) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void OsmMapView(java.util.List<me.zhaoqian.flyfun.data.models.Airport> airports, java.lang.String selectedPersona, kotlin.jvm.functions.Function1<? super me.zhaoqian.flyfun.data.models.Airport, kotlin.Unit> onAirportClick, androidx.compose.ui.Modifier modifier) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void TopAppBar(androidx.compose.ui.Modifier modifier, boolean showFiltersDialog, kotlin.jvm.functions.Function0<kotlin.Unit> onFilterClick, kotlin.jvm.functions.Function0<kotlin.Unit> onSearchClick, int totalAirports, boolean isLoading) {
    }
}