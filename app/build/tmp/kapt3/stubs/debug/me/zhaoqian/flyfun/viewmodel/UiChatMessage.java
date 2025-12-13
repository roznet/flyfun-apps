package me.zhaoqian.flyfun.viewmodel;

import androidx.lifecycle.ViewModel;
import dagger.hilt.android.lifecycle.HiltViewModel;
import kotlinx.coroutines.flow.*;
import me.zhaoqian.flyfun.data.models.*;
import me.zhaoqian.flyfun.data.repository.FlyFunRepository;
import java.util.UUID;
import javax.inject.Inject;

@kotlin.Metadata(mv = {1, 9, 0}, k = 1, xi = 48, d1 = {"\u00002\n\u0002\u0018\u0002\n\u0002\u0010\u0000\n\u0000\n\u0002\u0010\u000e\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0010\u000b\n\u0000\n\u0002\u0010 \n\u0002\u0018\u0002\n\u0002\b\u0012\n\u0002\u0010\b\n\u0002\b\u0002\b\u0086\b\u0018\u00002\u00020\u0001B9\u0012\u0006\u0010\u0002\u001a\u00020\u0003\u0012\u0006\u0010\u0004\u001a\u00020\u0005\u0012\u0006\u0010\u0006\u001a\u00020\u0003\u0012\b\b\u0002\u0010\u0007\u001a\u00020\b\u0012\u0010\b\u0002\u0010\t\u001a\n\u0012\u0004\u0012\u00020\u000b\u0018\u00010\n\u00a2\u0006\u0002\u0010\fJ\t\u0010\u0015\u001a\u00020\u0003H\u00c6\u0003J\t\u0010\u0016\u001a\u00020\u0005H\u00c6\u0003J\t\u0010\u0017\u001a\u00020\u0003H\u00c6\u0003J\t\u0010\u0018\u001a\u00020\bH\u00c6\u0003J\u0011\u0010\u0019\u001a\n\u0012\u0004\u0012\u00020\u000b\u0018\u00010\nH\u00c6\u0003JC\u0010\u001a\u001a\u00020\u00002\b\b\u0002\u0010\u0002\u001a\u00020\u00032\b\b\u0002\u0010\u0004\u001a\u00020\u00052\b\b\u0002\u0010\u0006\u001a\u00020\u00032\b\b\u0002\u0010\u0007\u001a\u00020\b2\u0010\b\u0002\u0010\t\u001a\n\u0012\u0004\u0012\u00020\u000b\u0018\u00010\nH\u00c6\u0001J\u0013\u0010\u001b\u001a\u00020\b2\b\u0010\u001c\u001a\u0004\u0018\u00010\u0001H\u00d6\u0003J\t\u0010\u001d\u001a\u00020\u001eH\u00d6\u0001J\t\u0010\u001f\u001a\u00020\u0003H\u00d6\u0001R\u0011\u0010\u0006\u001a\u00020\u0003\u00a2\u0006\b\n\u0000\u001a\u0004\b\r\u0010\u000eR\u0011\u0010\u0002\u001a\u00020\u0003\u00a2\u0006\b\n\u0000\u001a\u0004\b\u000f\u0010\u000eR\u0011\u0010\u0007\u001a\u00020\b\u00a2\u0006\b\n\u0000\u001a\u0004\b\u0007\u0010\u0010R\u0011\u0010\u0004\u001a\u00020\u0005\u00a2\u0006\b\n\u0000\u001a\u0004\b\u0011\u0010\u0012R\u0019\u0010\t\u001a\n\u0012\u0004\u0012\u00020\u000b\u0018\u00010\n\u00a2\u0006\b\n\u0000\u001a\u0004\b\u0013\u0010\u0014\u00a8\u0006 "}, d2 = {"Lme/zhaoqian/flyfun/viewmodel/UiChatMessage;", "", "id", "", "role", "Lme/zhaoqian/flyfun/viewmodel/Role;", "content", "isStreaming", "", "toolCalls", "", "Lme/zhaoqian/flyfun/data/models/ToolCall;", "(Ljava/lang/String;Lme/zhaoqian/flyfun/viewmodel/Role;Ljava/lang/String;ZLjava/util/List;)V", "getContent", "()Ljava/lang/String;", "getId", "()Z", "getRole", "()Lme/zhaoqian/flyfun/viewmodel/Role;", "getToolCalls", "()Ljava/util/List;", "component1", "component2", "component3", "component4", "component5", "copy", "equals", "other", "hashCode", "", "toString", "app_debug"})
public final class UiChatMessage {
    @org.jetbrains.annotations.NotNull()
    private final java.lang.String id = null;
    @org.jetbrains.annotations.NotNull()
    private final me.zhaoqian.flyfun.viewmodel.Role role = null;
    @org.jetbrains.annotations.NotNull()
    private final java.lang.String content = null;
    private final boolean isStreaming = false;
    @org.jetbrains.annotations.Nullable()
    private final java.util.List<me.zhaoqian.flyfun.data.models.ToolCall> toolCalls = null;
    
    public UiChatMessage(@org.jetbrains.annotations.NotNull()
    java.lang.String id, @org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.viewmodel.Role role, @org.jetbrains.annotations.NotNull()
    java.lang.String content, boolean isStreaming, @org.jetbrains.annotations.Nullable()
    java.util.List<me.zhaoqian.flyfun.data.models.ToolCall> toolCalls) {
        super();
    }
    
    @org.jetbrains.annotations.NotNull()
    public final java.lang.String getId() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final me.zhaoqian.flyfun.viewmodel.Role getRole() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final java.lang.String getContent() {
        return null;
    }
    
    public final boolean isStreaming() {
        return false;
    }
    
    @org.jetbrains.annotations.Nullable()
    public final java.util.List<me.zhaoqian.flyfun.data.models.ToolCall> getToolCalls() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final java.lang.String component1() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final me.zhaoqian.flyfun.viewmodel.Role component2() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final java.lang.String component3() {
        return null;
    }
    
    public final boolean component4() {
        return false;
    }
    
    @org.jetbrains.annotations.Nullable()
    public final java.util.List<me.zhaoqian.flyfun.data.models.ToolCall> component5() {
        return null;
    }
    
    @org.jetbrains.annotations.NotNull()
    public final me.zhaoqian.flyfun.viewmodel.UiChatMessage copy(@org.jetbrains.annotations.NotNull()
    java.lang.String id, @org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.viewmodel.Role role, @org.jetbrains.annotations.NotNull()
    java.lang.String content, boolean isStreaming, @org.jetbrains.annotations.Nullable()
    java.util.List<me.zhaoqian.flyfun.data.models.ToolCall> toolCalls) {
        return null;
    }
    
    @java.lang.Override()
    public boolean equals(@org.jetbrains.annotations.Nullable()
    java.lang.Object other) {
        return false;
    }
    
    @java.lang.Override()
    public int hashCode() {
        return 0;
    }
    
    @java.lang.Override()
    @org.jetbrains.annotations.NotNull()
    public java.lang.String toString() {
        return null;
    }
}