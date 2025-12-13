package me.zhaoqian.flyfun.ui.chat;

import androidx.compose.foundation.layout.*;
import androidx.compose.foundation.text.KeyboardOptions;
import androidx.compose.material.icons.Icons;
import androidx.compose.material.icons.filled.*;
import androidx.compose.material3.*;
import androidx.compose.runtime.*;
import androidx.compose.ui.Alignment;
import androidx.compose.ui.Modifier;
import androidx.compose.ui.graphics.Brush;
import androidx.compose.ui.text.input.ImeAction;
import me.zhaoqian.flyfun.ui.theme.*;
import me.zhaoqian.flyfun.viewmodel.ChatViewModel;
import me.zhaoqian.flyfun.viewmodel.Role;
import me.zhaoqian.flyfun.viewmodel.UiChatMessage;

@kotlin.Metadata(mv = {1, 9, 0}, k = 2, xi = 48, d1 = {"\u00008\n\u0000\n\u0002\u0010\u0002\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0002\n\u0002\u0010\u000e\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0018\u0002\n\u0000\n\u0002\u0010\u000b\n\u0000\n\u0002\u0018\u0002\n\u0002\b\u0003\n\u0002\u0018\u0002\n\u0002\b\u0004\u001a\u0010\u0010\u0000\u001a\u00020\u00012\u0006\u0010\u0002\u001a\u00020\u0003H\u0003\u001aD\u0010\u0004\u001a\u00020\u00012\u0006\u0010\u0005\u001a\u00020\u00062\u0012\u0010\u0007\u001a\u000e\u0012\u0004\u0012\u00020\u0006\u0012\u0004\u0012\u00020\u00010\b2\f\u0010\t\u001a\b\u0012\u0004\u0012\u00020\u00010\n2\u0006\u0010\u000b\u001a\u00020\f2\b\b\u0002\u0010\r\u001a\u00020\u000eH\u0003\u001a \u0010\u000f\u001a\u00020\u00012\f\u0010\u0010\u001a\b\u0012\u0004\u0012\u00020\u00010\n2\b\b\u0002\u0010\u0011\u001a\u00020\u0012H\u0007\u001a\u0010\u0010\u0013\u001a\u00020\u00012\u0006\u0010\u0014\u001a\u00020\u0006H\u0003\u001a\b\u0010\u0015\u001a\u00020\u0001H\u0003\u00a8\u0006\u0016"}, d2 = {"ChatBubble", "", "message", "Lme/zhaoqian/flyfun/viewmodel/UiChatMessage;", "ChatInputArea", "value", "", "onValueChange", "Lkotlin/Function1;", "onSend", "Lkotlin/Function0;", "isEnabled", "", "modifier", "Landroidx/compose/ui/Modifier;", "ChatScreen", "onNavigateToMap", "viewModel", "Lme/zhaoqian/flyfun/viewmodel/ChatViewModel;", "ThinkingIndicator", "thinking", "WelcomeCard", "app_debug"})
public final class ChatScreenKt {
    
    @kotlin.OptIn(markerClass = {androidx.compose.material3.ExperimentalMaterial3Api.class})
    @androidx.compose.runtime.Composable()
    public static final void ChatScreen(@org.jetbrains.annotations.NotNull()
    kotlin.jvm.functions.Function0<kotlin.Unit> onNavigateToMap, @org.jetbrains.annotations.NotNull()
    me.zhaoqian.flyfun.viewmodel.ChatViewModel viewModel) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void WelcomeCard() {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void ChatBubble(me.zhaoqian.flyfun.viewmodel.UiChatMessage message) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void ThinkingIndicator(java.lang.String thinking) {
    }
    
    @androidx.compose.runtime.Composable()
    private static final void ChatInputArea(java.lang.String value, kotlin.jvm.functions.Function1<? super java.lang.String, kotlin.Unit> onValueChange, kotlin.jvm.functions.Function0<kotlin.Unit> onSend, boolean isEnabled, androidx.compose.ui.Modifier modifier) {
    }
}