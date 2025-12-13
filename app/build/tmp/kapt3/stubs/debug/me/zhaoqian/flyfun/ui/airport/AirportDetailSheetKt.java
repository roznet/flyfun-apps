package me.zhaoqian.flyfun.ui.airport;

import androidx.compose.foundation.layout.*;
import androidx.compose.material.icons.Icons;
import androidx.compose.material.icons.filled.*;
import androidx.compose.material3.*;
import androidx.compose.runtime.*;
import androidx.compose.ui.Alignment;
import androidx.compose.ui.Modifier;
import androidx.compose.ui.text.font.FontWeight;
import me.zhaoqian.flyfun.data.models.*;
import me.zhaoqian.flyfun.ui.theme.*;

@kotlin.Metadata(mv = {1, 9, 0}, k = 2, xi = 48, d1 = {"\u0000R\n\u0000\n\u0002\u0010\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0010\u000e\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0006\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0002\b\b\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0010\u0006\n\u0000\u001a\u0012\u0010\u0000\u001a\u00020\u00012\b\u0010\u0002\u001a\u0004\u0018\u00010\u0003H\u0003\u001a\u0010\u0010\u0004\u001a\u00020\u00012\u0006\u0010\u0005\u001a\u00020\u0006H\u0003\u001aD\u0010\u0007\u001a\u00020\u00012\u0006\u0010\b\u001a\u00020\t2\b\u0010\n\u001a\u0004\u0018\u00010\u00032\u0006\u0010\u000b\u001a\u00020\f2\u0012\u0010\r\u001a\u000e\u0012\u0004\u0012\u00020\f\u0012\u0004\u0012\u00020\u00010\u000e2\f\u0010\u000f\u001a\b\u0012\u0004\u0012\u00020\u00010\u0010H\u0007\u001a\u0018\u0010\u0011\u001a\u00020\u00012\u0006\u0010\u0012\u001a\u00020\f2\u0006\u0010\u0013\u001a\u00020\fH\u0003\u001a.\u0010\u0014\u001a\u00020\u00012\u0006\u0010\u0015\u001a\u00020\f2\u001c\u0010\u0016\u001a\u0018\u0012\u0004\u0012\u00020\u0017\u0012\u0004\u0012\u00020\u00010\u000e\u00a2\u0006\u0002\b\u0018\u00a2\u0006\u0002\b\u0019H\u0003\u001a\u001a\u0010\u001a\u001a\u00020\u00012\u0006\u0010\b\u001a\u00020\t2\b\u0010\u0002\u001a\u0004\u0018\u00010\u0003H\u0003\u001a\u0010\u0010\u001b\u001a\u00020\u00012\u0006\u0010\u001c\u001a\u00020\fH\u0003\u001a,\u0010\u001d\u001a\u00020\u00012\u0006\u0010\b\u001a\u00020\t2\u0006\u0010\u000b\u001a\u00020\f2\u0012\u0010\r\u001a\u000e\u0012\u0004\u0012\u00020\f\u0012\u0004\u0012\u00020\u00010\u000eH\u0003\u001a\u0010\u0010\u001e\u001a\u00020\u00012\u0006\u0010\u001f\u001a\u00020\fH\u0003\u001a\u0010\u0010 \u001a\u00020\u00012\u0006\u0010!\u001a\u00020\"H\u0003\u001a\u0010\u0010#\u001a\u00020\u00012\u0006\u0010$\u001a\u00020%H\u0003\u00a8\u0006&"}, d2 = {"AipDataTab", "", "detail", "Lme/zhaoqian/flyfun/data/models/AirportDetail;", "AipEntryCard", "entry", "Lme/zhaoqian/flyfun/data/models/AipEntry;", "AirportDetailSheet", "airport", "Lme/zhaoqian/flyfun/data/models/Airport;", "airportDetail", "selectedPersona", "", "onPersonaChange", "Lkotlin/Function1;", "onDismiss", "Lkotlin/Function0;", "DetailRow", "label", "value", "DetailSection", "title", "content", "Landroidx/compose/foundation/layout/ColumnScope;", "Landroidx/compose/runtime/Composable;", "Lkotlin/ExtensionFunctionType;", "DetailsTab", "EmptyTabContent", "message", "RelevanceTab", "RulesTab", "countryCode", "RunwayCard", "runway", "Lme/zhaoqian/flyfun/data/models/Runway;", "ScoreBadge", "score", "", "app_debug"})
public final class AirportDetailSheetKt {
    
    @kotlin.OptIn(markerClass = {androidx.compose.material3.ExperimentalMaterial3Api.class, androidx.compose.foundation.layout.ExperimentalLayoutApi.class})
    @androidx.compose.runtime.Composable()
    public static final void AirportDetailSheet(@org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.data.models.Airport airport, @org.jetbrains.annotations.Nullable()
    me.zhaoqian.flyfun.data.models.AirportDetail airportDetail, @org.jetbrains.annotations.NotNull()
    java.lang.String selectedPersona, @org.jetbrains.annotations.NotNull()
    kotlin.jvm.functions.Function1<? super java.lang.String, kotlin.Unit> onPersonaChange, @org.jetbrains.annotations.NotNull()
    kotlin.jvm.functions.Function0<kotlin.Unit> onDismiss) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void ScoreBadge(double score) {
    }
    
    @kotlin.OptIn(markerClass = {androidx.compose.foundation.layout.ExperimentalLayoutApi.class})
    @androidx.compose.runtime.Composable()
    private static final void DetailsTab(me.zhaoqian.flyfun.data.models.Airport airport, me.zhaoqian.flyfun.data.models.AirportDetail detail) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void DetailSection(java.lang.String title, kotlin.jvm.functions.Function1<? super androidx.compose.foundation.layout.ColumnScope, kotlin.Unit> content) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void DetailRow(java.lang.String label, java.lang.String value) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void RunwayCard(me.zhaoqian.flyfun.data.models.Runway runway) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void AipDataTab(me.zhaoqian.flyfun.data.models.AirportDetail detail) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void AipEntryCard(me.zhaoqian.flyfun.data.models.AipEntry entry) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void RulesTab(java.lang.String countryCode) {
    }
    
    @kotlin.OptIn(markerClass = {androidx.compose.foundation.layout.ExperimentalLayoutApi.class})
    @androidx.compose.runtime.Composable()
    private static final void RelevanceTab(me.zhaoqian.flyfun.data.models.Airport airport, java.lang.String selectedPersona, kotlin.jvm.functions.Function1<? super java.lang.String, kotlin.Unit> onPersonaChange) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void EmptyTabContent(java.lang.String message) {
    }
}