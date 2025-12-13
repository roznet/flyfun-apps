package me.zhaoqian.flyfun.data.repository;

import kotlinx.coroutines.flow.Flow;
import me.zhaoqian.flyfun.data.api.ChatStreamingClient;
import me.zhaoqian.flyfun.data.api.FlyFunApiService;
import me.zhaoqian.flyfun.data.models.*;
import javax.inject.Inject;
import javax.inject.Named;
import javax.inject.Singleton;

/**
 * Main repository for FlyFun data access.
 * Wraps API calls with error handling and caching.
 */
@javax.inject.Singleton()
@kotlin.Metadata(mv = {1, 9, 0}, k = 1, xi = 48, d1 = {"\u0000\u009e\u0001\n\u0002\u0018\u0002\n\u0002\u0010\u0000\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0010\u000e\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0010 \n\u0002\u0018\u0002\n\u0002\b\u0005\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0010\u000b\n\u0002\b\u0002\n\u0002\u0010\b\n\u0002\b\u0006\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0004\n\u0002\u0018\u0002\n\u0002\u0018\u0002\n\u0000\b\u0007\u0018\u00002\u00020\u0001B!\b\u0007\u0012\u0006\u0010\u0002\u001a\u00020\u0003\u0012\u0006\u0010\u0004\u001a\u00020\u0005\u0012\b\b\u0001\u0010\u0006\u001a\u00020\u0007\u00a2\u0006\u0002\u0010\bJ$\u0010\t\u001a\b\u0012\u0004\u0012\u00020\u000b0\n2\u0006\u0010\f\u001a\u00020\rH\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b\u000e\u0010\u000fJ6\u0010\u0010\u001a\u000e\u0012\n\u0012\b\u0012\u0004\u0012\u00020\u00120\u00110\n2\u0006\u0010\u0013\u001a\u00020\u00072\n\b\u0002\u0010\u0014\u001a\u0004\u0018\u00010\u0007H\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b\u0015\u0010\u0016J$\u0010\u0017\u001a\b\u0012\u0004\u0012\u00020\u00180\n2\u0006\u0010\u0013\u001a\u00020\u0007H\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b\u0019\u0010\u001aJ*\u0010\u001b\u001a\u000e\u0012\n\u0012\b\u0012\u0004\u0012\u00020\u001c0\u00110\n2\u0006\u0010\u0013\u001a\u00020\u0007H\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b\u001d\u0010\u001aJ*\u0010\u001e\u001a\u000e\u0012\n\u0012\b\u0012\u0004\u0012\u00020\u001f0\u00110\n2\u0006\u0010\u0013\u001a\u00020\u0007H\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b \u0010\u001aJx\u0010!\u001a\b\u0012\u0004\u0012\u00020\"0\n2\n\b\u0002\u0010#\u001a\u0004\u0018\u00010\u00072\n\b\u0002\u0010$\u001a\u0004\u0018\u00010\u00072\n\b\u0002\u0010%\u001a\u0004\u0018\u00010&2\n\b\u0002\u0010\'\u001a\u0004\u0018\u00010&2\n\b\u0002\u0010(\u001a\u0004\u0018\u00010)2\n\b\u0002\u0010*\u001a\u0004\u0018\u00010\u00072\b\b\u0002\u0010+\u001a\u00020)2\b\b\u0002\u0010,\u001a\u00020)H\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b-\u0010.J$\u0010/\u001a\b\u0012\u0004\u0012\u0002000\n2\u0006\u00101\u001a\u00020\u0007H\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b2\u0010\u001aJ\u001c\u00103\u001a\b\u0012\u0004\u0012\u0002040\nH\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b5\u00106J\"\u00107\u001a\u000e\u0012\n\u0012\b\u0012\u0004\u0012\u0002080\u00110\nH\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b9\u00106J,\u0010:\u001a\b\u0012\u0004\u0012\u00020;0\n2\u0006\u0010\u0013\u001a\u00020\u00072\u0006\u0010<\u001a\u00020\u0007H\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\b=\u0010\u0016J4\u0010>\u001a\u000e\u0012\n\u0012\b\u0012\u0004\u0012\u00020?0\u00110\n2\u0006\u0010@\u001a\u00020\u00072\b\b\u0002\u0010+\u001a\u00020)H\u0086@\u00f8\u0001\u0000\u00f8\u0001\u0001\u00a2\u0006\u0004\bA\u0010BJ\u0014\u0010C\u001a\b\u0012\u0004\u0012\u00020E0D2\u0006\u0010\f\u001a\u00020\rR\u000e\u0010\u0002\u001a\u00020\u0003X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u000e\u0010\u0006\u001a\u00020\u0007X\u0082\u0004\u00a2\u0006\u0002\n\u0000R\u000e\u0010\u0004\u001a\u00020\u0005X\u0082\u0004\u00a2\u0006\u0002\n\u0000\u0082\u0002\u000b\n\u0002\b!\n\u0005\b\u00a1\u001e0\u0001\u00a8\u0006F"}, d2 = {"Lme/zhaoqian/flyfun/data/repository/FlyFunRepository;", "", "apiService", "Lme/zhaoqian/flyfun/data/api/FlyFunApiService;", "chatStreamingClient", "Lme/zhaoqian/flyfun/data/api/ChatStreamingClient;", "baseUrl", "", "(Lme/zhaoqian/flyfun/data/api/FlyFunApiService;Lme/zhaoqian/flyfun/data/api/ChatStreamingClient;Ljava/lang/String;)V", "chat", "Lkotlin/Result;", "Lme/zhaoqian/flyfun/data/models/ChatResponse;", "request", "Lme/zhaoqian/flyfun/data/models/ChatRequest;", "chat-gIAlu-s", "(Lme/zhaoqian/flyfun/data/models/ChatRequest;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getAirportAipEntries", "", "Lme/zhaoqian/flyfun/data/models/AipEntry;", "icao", "section", "getAirportAipEntries-0E7RQCE", "(Ljava/lang/String;Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getAirportDetail", "Lme/zhaoqian/flyfun/data/models/AirportDetail;", "getAirportDetail-gIAlu-s", "(Ljava/lang/String;Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getAirportProcedures", "Lme/zhaoqian/flyfun/data/models/Procedure;", "getAirportProcedures-gIAlu-s", "getAirportRunways", "Lme/zhaoqian/flyfun/data/models/Runway;", "getAirportRunways-gIAlu-s", "getAirports", "Lme/zhaoqian/flyfun/data/models/AirportsResponse;", "country", "hasProcedure", "hasIls", "", "pointOfEntry", "runwayMinLength", "", "search", "limit", "offset", "getAirports-tZkwj4A", "(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Boolean;Ljava/lang/Boolean;Ljava/lang/Integer;Ljava/lang/String;IILkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getCountryRules", "Lme/zhaoqian/flyfun/data/models/CountryRulesResponse;", "countryCode", "getCountryRules-gIAlu-s", "getGAConfig", "Lme/zhaoqian/flyfun/data/models/GAConfig;", "getGAConfig-IoAF18A", "(Lkotlin/coroutines/Continuation;)Ljava/lang/Object;", "getGAPersonas", "Lme/zhaoqian/flyfun/data/models/Persona;", "getGAPersonas-IoAF18A", "getGASummary", "Lme/zhaoqian/flyfun/data/models/GADetailedSummary;", "persona", "getGASummary-0E7RQCE", "searchAirports", "Lme/zhaoqian/flyfun/data/models/Airport;", "query", "searchAirports-0E7RQCE", "(Ljava/lang/String;ILkotlin/coroutines/Continuation;)Ljava/lang/Object;", "streamChat", "Lkotlinx/coroutines/flow/Flow;", "Lme/zhaoqian/flyfun/data/models/ChatStreamEvent;", "app_debug"})
public final class FlyFunRepository {
    @org.jetbrains.annotations.NotNull()
    private final me.zhaoqian.flyfun.data.api.FlyFunApiService apiService = null;
    @org.jetbrains.annotations.NotNull()
    private final me.zhaoqian.flyfun.data.api.ChatStreamingClient chatStreamingClient = null;
    @org.jetbrains.annotations.NotNull()
    private final java.lang.String baseUrl = null;
    
    @javax.inject.Inject()
    public FlyFunRepository(@org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.data.api.FlyFunApiService apiService, @org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.data.api.ChatStreamingClient chatStreamingClient, @javax.inject.Named(value = "baseUrl")
    @org.jetbrains.annotations.NotNull()
    java.lang.String baseUrl) {
        super();
    }
    
    @org.jetbrains.annotations.NotNull()
    public final kotlinx.coroutines.flow.Flow<me.zhaoqian.flyfun.data.models.ChatStreamEvent> streamChat(@org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.data.models.ChatRequest request) {
        return null;
    }
}