package me.zhaoqian.flyfun.data.api;

import me.zhaoqian.flyfun.data.models.*;
import retrofit2.http.*;

/**
 * FlyFun API service interface for all endpoints.
 */
@kotlin.Metadata(mv = {1, 9, 0}, k = 1, xi = 48, d1 = {"\u0000~\n\u0002\u0018\u0002\n\u0002\u0010\u0000\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0010 \n\u0002\u0018\u0002\n\u0000\n\u0002\u0010\u000e\n\u0002\b\u0004\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0010\u000b\n\u0002\b\u0002\n\u0002\u0010\b\n\u0002\b\u0006\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0003\bf\u0018\u00002\u00020\u0001J\u0018\u0010\u0002\u001a\u00020\u00032\b\b\u0001\u0010\u0004\u001a\u00020\u0005H\u00a7@\u00a2\u0006\u0002\u0010\u0006J6\u0010\u0007\u001a\b\u0012\u0004\u0012\u00020\t0\b2\b\b\u0001\u0010\n\u001a\u00020\u000b2\n\b\u0003\u0010\f\u001a\u0004\u0018\u00010\u000b2\n\b\u0003\u0010\r\u001a\u0004\u0018\u00010\u000bH\u00a7@\u00a2\u0006\u0002\u0010\u000eJ\u0018\u0010\u000f\u001a\u00020\u00102\b\b\u0001\u0010\n\u001a\u00020\u000bH\u00a7@\u00a2\u0006\u0002\u0010\u0011J6\u0010\u0012\u001a\b\u0012\u0004\u0012\u00020\u00130\b2\b\b\u0001\u0010\n\u001a\u00020\u000b2\n\b\u0003\u0010\u0014\u001a\u0004\u0018\u00010\u000b2\n\b\u0003\u0010\u0015\u001a\u0004\u0018\u00010\u000bH\u00a7@\u00a2\u0006\u0002\u0010\u000eJ\u001e\u0010\u0016\u001a\b\u0012\u0004\u0012\u00020\u00170\b2\b\b\u0001\u0010\n\u001a\u00020\u000bH\u00a7@\u00a2\u0006\u0002\u0010\u0011Jt\u0010\u0018\u001a\u00020\u00192\n\b\u0003\u0010\u001a\u001a\u0004\u0018\u00010\u000b2\n\b\u0003\u0010\u001b\u001a\u0004\u0018\u00010\u000b2\n\b\u0003\u0010\u001c\u001a\u0004\u0018\u00010\u001d2\n\b\u0003\u0010\u001e\u001a\u0004\u0018\u00010\u001d2\n\b\u0003\u0010\u001f\u001a\u0004\u0018\u00010 2\n\b\u0003\u0010!\u001a\u0004\u0018\u00010\u000b2\b\b\u0003\u0010\"\u001a\u00020 2\b\b\u0003\u0010#\u001a\u00020 2\b\b\u0003\u0010$\u001a\u00020\u001dH\u00a7@\u00a2\u0006\u0002\u0010%J\u0018\u0010&\u001a\u00020\'2\b\b\u0001\u0010(\u001a\u00020\u000bH\u00a7@\u00a2\u0006\u0002\u0010\u0011J\u000e\u0010)\u001a\u00020*H\u00a7@\u00a2\u0006\u0002\u0010+J\u0014\u0010,\u001a\b\u0012\u0004\u0012\u00020-0\bH\u00a7@\u00a2\u0006\u0002\u0010+J\"\u0010.\u001a\u00020/2\b\b\u0001\u0010\n\u001a\u00020\u000b2\b\b\u0003\u00100\u001a\u00020\u000bH\u00a7@\u00a2\u0006\u0002\u00101J(\u00102\u001a\b\u0012\u0004\u0012\u0002030\b2\b\b\u0001\u00104\u001a\u00020\u000b2\b\b\u0003\u0010\"\u001a\u00020 H\u00a7@\u00a2\u0006\u0002\u00105\u00a8\u00066"}, d2 = {"Lme/zhaoqian/flyfun/data/api/FlyFunApiService;", "", "chat", "Lme/zhaoqian/flyfun/data/models/ChatResponse;", "request", "Lme/zhaoqian/flyfun/data/models/ChatRequest;", "(Lme/zhaoqian/flyfun/data/models/ChatRequest;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getAirportAipEntries", "", "Lme/zhaoqian/flyfun/data/models/AipEntry;", "icao", "", "section", "stdField", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getAirportDetail", "Lme/zhaoqian/flyfun/data/models/AirportDetail;", "(Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getAirportProcedures", "Lme/zhaoqian/flyfun/data/models/Procedure;", "procedureType", "runway", "getAirportRunways", "Lme/zhaoqian/flyfun/data/models/Runway;", "getAirports", "Lme/zhaoqian/flyfun/data/models/AirportsResponse;", "country", "hasProcedure", "hasIls", "", "pointOfEntry", "runwayMinLength", "", "search", "limit", "offset", "includeGa", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Boolean;Ljava/lang/Boolean;Ljava/lang/Integer;Ljava/lang/String;IIZLkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getCountryRules", "Lme/zhaoqian/flyfun/data/models/CountryRulesResponse;", "countryCode", "getGAConfig", "Lme/zhaoqian/flyfun/data/models/GAConfig;", "(Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getGAPersonas", "Lme/zhaoqian/flyfun/data/models/Persona;", "getGASummary", "Lme/zhaoqian/flyfun/data/models/GADetailedSummary;", "persona", "(Ljava/lang/String;Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "searchAirports", "Lme/zhaoqian/flyfun/data/models/Airport;", "query", "(Ljava/lang/String;ILkotlin/coroutines/Continuation;)Ljava/lang/Object;", "app_debug"})
public abstract interface FlyFunApiService {
    
    @retrofit2.http.GET(value = "airports")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getAirports(@retrofit2.http.Query(value = "country")
    @org.jetbrains.annotations.Nullable()
    java.lang.String country, @retrofit2.http.Query(value = "has_procedure")
    @org.jetbrains.annotations.Nullable()
    java.lang.String hasProcedure, @retrofit2.http.Query(value = "has_ils")
    @org.jetbrains.annotations.Nullable()
    java.lang.Boolean hasIls, @retrofit2.http.Query(value = "point_of_entry")
    @org.jetbrains.annotations.Nullable()
    java.lang.Boolean pointOfEntry, @retrofit2.http.Query(value = "runway_min_length")
    @org.jetbrains.annotations.Nullable()
    java.lang.Integer runwayMinLength, @retrofit2.http.Query(value = "search")
    @org.jetbrains.annotations.Nullable()
    java.lang.String search, @retrofit2.http.Query(value = "limit")
    int limit, @retrofit2.http.Query(value = "offset")
    int offset, @retrofit2.http.Query(value = "include_ga")
    boolean includeGa, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super me.zhaoqian.flyfun.data.models.AirportsResponse> $completion);
    
    @retrofit2.http.GET(value = "airports/{icao}")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getAirportDetail(@retrofit2.http.Path(value = "icao")
    @org.jetbrains.annotations.NotNull()
    java.lang.String icao, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super me.zhaoqian.flyfun.data.models.AirportDetail> $completion);
    
    @retrofit2.http.GET(value = "airports/{icao}/aip")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getAirportAipEntries(@retrofit2.http.Path(value = "icao")
    @org.jetbrains.annotations.NotNull()
    java.lang.String icao, @retrofit2.http.Query(value = "section")
    @org.jetbrains.annotations.Nullable()
    java.lang.String section, @retrofit2.http.Query(value = "std_field")
    @org.jetbrains.annotations.Nullable()
    java.lang.String stdField, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super java.util.List<me.zhaoqian.flyfun.data.models.AipEntry>> $completion);
    
    @retrofit2.http.GET(value = "airports/{icao}/procedures")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getAirportProcedures(@retrofit2.http.Path(value = "icao")
    @org.jetbrains.annotations.NotNull()
    java.lang.String icao, @retrofit2.http.Query(value = "procedure_type")
    @org.jetbrains.annotations.Nullable()
    java.lang.String procedureType, @retrofit2.http.Query(value = "runway")
    @org.jetbrains.annotations.Nullable()
    java.lang.String runway, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super java.util.List<me.zhaoqian.flyfun.data.models.Procedure>> $completion);
    
    @retrofit2.http.GET(value = "airports/{icao}/runways")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getAirportRunways(@retrofit2.http.Path(value = "icao")
    @org.jetbrains.annotations.NotNull()
    java.lang.String icao, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super java.util.List<me.zhaoqian.flyfun.data.models.Runway>> $completion);
    
    @retrofit2.http.GET(value = "airports/search/{query}")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object searchAirports(@retrofit2.http.Path(value = "query")
    @org.jetbrains.annotations.NotNull()
    java.lang.String query, @retrofit2.http.Query(value = "limit")
    int limit, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super java.util.List<me.zhaoqian.flyfun.data.models.Airport>> $completion);
    
    @retrofit2.http.GET(value = "rules/{country_code}")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getCountryRules(@retrofit2.http.Path(value = "country_code")
    @org.jetbrains.annotations.NotNull()
    java.lang.String countryCode, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super me.zhaoqian.flyfun.data.models.CountryRulesResponse> $completion);
    
    @retrofit2.http.GET(value = "ga/config")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getGAConfig(@org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super me.zhaoqian.flyfun.data.models.GAConfig> $completion);
    
    @retrofit2.http.GET(value = "ga/personas")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getGAPersonas(@org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super java.util.List<me.zhaoqian.flyfun.data.models.Persona>> $completion);
    
    @retrofit2.http.GET(value = "ga/summary/{icao}")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object getGASummary(@retrofit2.http.Path(value = "icao")
    @org.jetbrains.annotations.NotNull()
    java.lang.String icao, @retrofit2.http.Query(value = "persona")
    @org.jetbrains.annotations.NotNull()
    java.lang.String persona, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super me.zhaoqian.flyfun.data.models.GADetailedSummary> $completion);
    
    @retrofit2.http.POST(value = "aviation-agent/chat")
    @org.jetbrains.annotations.Nullable()
    public abstract java.lang.Object chat(@retrofit2.http.Body()
    @org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.data.models.ChatRequest request, @org.jetbrains.annotations.NotNull()
    kotlin.coroutines.Continuation<? super me.zhaoqian.flyfun.data.models.ChatResponse> $completion);
    
    /**
     * FlyFun API service interface for all endpoints.
     */
    @kotlin.Metadata(mv = {1, 9, 0}, k = 3, xi = 48)
    public static final class DefaultImpls {
    }
}