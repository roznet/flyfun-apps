package me.zhaoqian.flyfun.ui.chat

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.hilt.navigation.compose.hiltViewModel
import kotlinx.coroutines.launch
import me.zhaoqian.flyfun.ui.theme.*
import me.zhaoqian.flyfun.data.models.SuggestedQuery
import me.zhaoqian.flyfun.offline.ModelManager
import me.zhaoqian.flyfun.viewmodel.ChatViewModel
import me.zhaoqian.flyfun.viewmodel.Role
import me.zhaoqian.flyfun.viewmodel.UiChatMessage

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(
    onNavigateToMap: () -> Unit,
    viewModel: ChatViewModel = hiltViewModel()
) {
    val messages by viewModel.messages.collectAsState()
    val isStreaming by viewModel.isStreaming.collectAsState()
    val currentThinking by viewModel.currentThinking.collectAsState()
    val error by viewModel.error.collectAsState()
    val suggestedQueries by viewModel.suggestedQueries.collectAsState()
    val personas by viewModel.personas.collectAsState()
    val selectedPersonaId by viewModel.selectedPersonaId.collectAsState()
    
    // Offline mode states
    val isOffline by viewModel.isOffline.collectAsState()
    val forceOfflineMode by viewModel.forceOfflineMode.collectAsState()
    val modelState by viewModel.modelState.collectAsState()
    
    var inputText by remember { mutableStateOf("") }
    var showPersonaMenu by remember { mutableStateOf(false) }
    var showOfflineMenu by remember { mutableStateOf(false) }
    var showDownloadDialog by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val coroutineScope = rememberCoroutineScope()
    
    // Scroll to bottom when new messages arrive
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }
    
    Scaffold(
        topBar = {
            TopAppBar(
                title = { 
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        // Airplane icon
                        Text(
                            text = "✈️",
                            style = MaterialTheme.typography.headlineMedium
                        )
                        Column {
                            Text(
                                text = "FlyFun Assistant",
                                style = MaterialTheme.typography.titleLarge
                            )
                            Text(
                                text = "Your intelligent aviation companion",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onNavigateToMap) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back to Map")
                    }
                },
                actions = {
                    // Persona dropdown
                    Box {
                        val selectedPersona = personas.find { it.id == selectedPersonaId }
                        TextButton(onClick = { showPersonaMenu = true }) {
                            Text(
                                text = selectedPersona?.label ?: "Select Persona",
                                style = MaterialTheme.typography.labelMedium,
                                maxLines = 1
                            )
                            Icon(
                                imageVector = Icons.Default.ArrowDropDown,
                                contentDescription = null
                            )
                        }
                        DropdownMenu(
                            expanded = showPersonaMenu,
                            onDismissRequest = { showPersonaMenu = false }
                        ) {
                            personas.forEach { persona ->
                                DropdownMenuItem(
                                    text = {
                                        Column {
                                            Text(
                                                text = persona.label,
                                                fontWeight = if (persona.id == selectedPersonaId) FontWeight.Bold else FontWeight.Normal
                                            )
                                        }
                                    },
                                    onClick = {
                                        viewModel.selectPersona(persona.id)
                                        showPersonaMenu = false
                                    },
                                    leadingIcon = {
                                        if (persona.id == selectedPersonaId) {
                                            Icon(
                                                imageVector = Icons.Default.Check,
                                                contentDescription = "Selected",
                                                tint = MaterialTheme.colorScheme.primary
                                            )
                                        }
                                    }
                                )
                            }
                        }
                    }
                    
                    // Offline mode toggle
                    Box {
                        IconButton(onClick = { showOfflineMenu = true }) {
                            Icon(
                                imageVector = if (isOffline) Icons.Default.CloudOff else Icons.Default.Cloud,
                                contentDescription = "Offline mode",
                                tint = if (forceOfflineMode) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                        DropdownMenu(
                            expanded = showOfflineMenu,
                            onDismissRequest = { showOfflineMenu = false }
                        ) {
                            // Header
                            Text(
                                text = "Offline Mode",
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                            )
                            
                            // Status
                            val statusText = when (modelState) {
                                is ModelManager.ModelState.Ready -> "Model ready"
                                is ModelManager.ModelState.Loaded -> "Model loaded"
                                is ModelManager.ModelState.NotDownloaded -> "Model not downloaded"
                                is ModelManager.ModelState.Downloading -> {
                                    val state = modelState as ModelManager.ModelState.Downloading
                                    "Downloading... ${(state.progress * 100).toInt()}%"
                                }
                                is ModelManager.ModelState.Loading -> "Loading model..."
                                is ModelManager.ModelState.Error -> "Error"
                                else -> "Checking..."
                            }
                            Text(
                                text = statusText,
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                            )
                            
                            HorizontalDivider(modifier = Modifier.padding(vertical = 8.dp))
                            
                            // Force offline toggle (for testing)
                            DropdownMenuItem(
                                text = {
                                    Row(
                                        verticalAlignment = Alignment.CenterVertically,
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        modifier = Modifier.fillMaxWidth()
                                    ) {
                                        Text("Force Offline")
                                        Switch(
                                            checked = forceOfflineMode,
                                            onCheckedChange = { viewModel.setForceOfflineMode(it) }
                                        )
                                    }
                                },
                                onClick = { viewModel.toggleForceOfflineMode() }
                            )
                            
                            // Download button if not ready
                            if (modelState is ModelManager.ModelState.NotDownloaded) {
                                DropdownMenuItem(
                                    text = { Text("Download Model (2.6 GB)") },
                                    onClick = {
                                        showOfflineMenu = false
                                        showDownloadDialog = true
                                    },
                                    leadingIcon = {
                                        Icon(Icons.Default.Download, contentDescription = null)
                                    }
                                )
                                
                                // Local test model for development (only shown if not downloaded)
                                HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                                Text(
                                    text = "Development",
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp)
                                )
                                DropdownMenuItem(
                                    text = { 
                                        Column {
                                            Text("Use Test Model")
                                            Text(
                                                text = "Load from dev path",
                                                style = MaterialTheme.typography.bodySmall,
                                                color = MaterialTheme.colorScheme.onSurfaceVariant
                                            )
                                        }
                                    },
                                    onClick = {
                                        // Use the local test path from companion object
                                        viewModel.setExternalModelPath(ModelManager.LOCAL_TEST_MODEL_PATH)
                                        showOfflineMenu = false
                                    },
                                    leadingIcon = {
                                        Icon(Icons.Default.Folder, contentDescription = null)
                                    }
                                )
                            }
                        }
                    }
                    
                    // Clear chat button
                    IconButton(onClick = { viewModel.clearChat() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "New conversation")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Offline mode indicator banner
            AnimatedVisibility(visible = isOffline) {
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    color = Color(0xFF6C5DD3).copy(alpha = 0.9f)
                ) {
                    Row(
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.CloudOff,
                            contentDescription = null,
                            tint = Color.White,
                            modifier = Modifier.size(16.dp)
                        )
                        Text(
                            text = if (forceOfflineMode) "Offline Mode (Testing)" else "Offline Mode (No Network)",
                            style = MaterialTheme.typography.labelMedium,
                            color = Color.White
                        )
                    }
                }
            }
            
            // Messages list
            LazyColumn(
                state = listState,
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Filter out streaming placeholder bubbles (empty content while streaming)
                items(messages.filter { !it.isStreaming || it.content.isNotBlank() }, key = { it.id }) { message ->
                    ChatBubble(message = message)
                }
                
                // Thinking/Loading indicator - show while streaming
                if (isStreaming) {
                    item {
                        ThinkingIndicator(thinking = currentThinking ?: "Processing your request...")
                    }
                }
                
                // Suggested follow-up questions
                if (!isStreaming && suggestedQueries.isNotEmpty()) {
                    item {
                        SuggestedQueriesSection(
                            suggestions = suggestedQueries,
                            onSuggestionClick = { suggestion ->
                                viewModel.sendMessage(suggestion.text)
                            }
                        )
                    }
                }
            }
            
            // Error message
            AnimatedVisibility(visible = error != null) {
                error?.let {
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(horizontal = 16.dp, vertical = 4.dp),
                        color = MaterialTheme.colorScheme.errorContainer,
                        shape = RoundedCornerShape(8.dp)
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = it,
                                modifier = Modifier.weight(1f),
                                color = MaterialTheme.colorScheme.onErrorContainer
                            )
                            IconButton(onClick = { viewModel.clearError() }) {
                                Icon(Icons.Default.Close, contentDescription = "Dismiss")
                            }
                        }
                    }
                }
            }
            
            // Input area - at the very bottom
            ChatInputArea(
                value = inputText,
                onValueChange = { inputText = it },
                onSend = {
                    if (inputText.isNotBlank()) {
                        viewModel.sendMessage(inputText)
                        inputText = ""
                    }
                },
                isEnabled = !isStreaming,
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, top = 8.dp, bottom = 0.dp)
            )
        }
    }
    
    // Model download dialog
    if (showDownloadDialog) {
        AlertDialog(
            onDismissRequest = { showDownloadDialog = false },
            title = {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Icon(
                        imageVector = Icons.Default.Download,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.primary
                    )
                    Text("Download Offline Model")
                }
            },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("The offline AI model allows you to use FlyFun without an internet connection.")
                    
                    Text(
                        text = "Model Details:",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text("• Size: ~2.6 GB")
                    Text("• Recommended: 4GB+ RAM")
                    Text("• Android 8.0+")
                    
                    val capability = remember { viewModel.getDeviceCapability() }
                    if (!capability.isSupported) {
                        Surface(
                            color = MaterialTheme.colorScheme.errorContainer,
                            shape = RoundedCornerShape(8.dp)
                        ) {
                            Row(
                                modifier = Modifier.padding(12.dp),
                                horizontalArrangement = Arrangement.spacedBy(8.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.Warning,
                                    contentDescription = null,
                                    tint = MaterialTheme.colorScheme.onErrorContainer
                                )
                                Text(
                                    text = capability.warningMessage ?: "Device not supported",
                                    color = MaterialTheme.colorScheme.onErrorContainer,
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                        }
                    }
                    
                    // Show download progress if downloading
                    if (modelState is ModelManager.ModelState.Downloading) {
                        val downloadState = modelState as ModelManager.ModelState.Downloading
                        Column {
                            Text(
                                text = "Downloading... ${(downloadState.progress * 100).toInt()}%",
                                style = MaterialTheme.typography.bodySmall
                            )
                            LinearProgressIndicator(
                                progress = { downloadState.progress },
                                modifier = Modifier.fillMaxWidth()
                            )
                        }
                    }
                }
            },
            confirmButton = {
                val isDownloading = modelState is ModelManager.ModelState.Downloading
                Button(
                    onClick = {
                        // TODO: Replace with actual model URL when hosting is decided
                        coroutineScope.launch {
                            viewModel.downloadModel("https://your-server.com/models/flyfun-gemma-3n-q4_k_m.gguf")
                        }
                    },
                    enabled = !isDownloading
                ) {
                    Text(if (isDownloading) "Downloading..." else "Download")
                }
            },
            dismissButton = {
                TextButton(onClick = { showDownloadDialog = false }) {
                    Text("Cancel")
                }
            }
        )
    }
}

@Composable
private fun WelcomeCard() {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = "✈️",
                style = MaterialTheme.typography.displayMedium
            )
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = "Welcome to FlyFun Assistant",
                style = MaterialTheme.typography.titleMedium
            )
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = "Ask me about airports, aviation rules, flight planning, and more!",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.8f)
            )
            
            Spacer(modifier = Modifier.height(16.dp))
            
            // Quick actions
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                SuggestionChip(
                    onClick = { /* TODO */ },
                    label = { Text("Find airports") }
                )
                SuggestionChip(
                    onClick = { /* TODO */ },
                    label = { Text("Border crossing") }
                )
            }
        }
    }
}

@Composable
private fun ChatBubble(message: UiChatMessage) {
    val isUser = message.role == Role.USER
    
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
    ) {
        Box(
            modifier = Modifier
                .fillMaxWidth(0.9f)  // Use 90% of width for wider bubbles on tablets
                .clip(
                    RoundedCornerShape(
                        topStart = 16.dp,
                        topEnd = 16.dp,
                        bottomStart = if (isUser) 16.dp else 4.dp,
                        bottomEnd = if (isUser) 4.dp else 16.dp
                    )
                )
                .background(
                    if (isUser) {
                        // Gradient background matching web UI
                        Brush.linearGradient(
                            colors = listOf(PrimaryGradientStart, PrimaryGradientEnd)
                        )
                    } else {
                        // Light gray for assistant (matching web's #f1f3f5)
                        Brush.linearGradient(
                            colors = listOf(ChatAssistantBubble, ChatAssistantBubble)
                        )
                    }
                )
                .padding(12.dp)
        ) {
            Column {
                if (isUser) {
                    // User messages - plain text
                    Text(
                        text = message.content.ifBlank { "..." },
                        color = androidx.compose.ui.graphics.Color.White
                    )
                } else {
                    // Assistant messages - render as formatted markdown
                    Text(
                        text = parseMarkdown(message.content.ifBlank { "..." }),
                        color = LightOnSurface
                    )
                }
            }
        }
    }
}

@Composable
private fun ThinkingIndicator(thinking: String) {
    // Animated airplane position (0f to 1f)
    val infiniteTransition = rememberInfiniteTransition(label = "airplane")
    val airplaneProgress by infiniteTransition.animateFloat(
        initialValue = 0f,
        targetValue = 1f,
        animationSpec = infiniteRepeatable(
            animation = tween(2500, easing = LinearEasing),
            repeatMode = RepeatMode.Restart
        ),
        label = "airplanePosition"
    )
    
    // Simple airplane flying on blue gradient line
    BoxWithConstraints(
        modifier = Modifier
            .fillMaxWidth()
            .height(40.dp)
            .padding(vertical = 8.dp)
    ) {
        val maxWidthPx = constraints.maxWidth.toFloat()
        
        // Flight path background (light gray)
        Box(
            modifier = Modifier
                .align(Alignment.Center)
                .fillMaxWidth()
                .height(4.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(MaterialTheme.colorScheme.outline.copy(alpha = 0.3f))
        )
        
        // Progress trail (gradient blue-purple)
        Box(
            modifier = Modifier
                .align(Alignment.CenterStart)
                .fillMaxWidth(airplaneProgress)
                .height(4.dp)
                .clip(RoundedCornerShape(2.dp))
                .background(
                    Brush.horizontalGradient(
                        colors = listOf(
                            PrimaryGradientStart,
                            PrimaryGradientEnd
                        )
                    )
                )
        )
        
        // Flying airplane
        val offsetPx = (airplaneProgress * (maxWidthPx - 30)).toInt()
        Text(
            text = "✈️",
            fontSize = 20.sp,
            modifier = Modifier
                .offset { IntOffset(offsetPx, 0) }
                .align(Alignment.CenterStart)
        )
    }
}

@Composable
private fun ChatInputArea(
    value: String,
    onValueChange: (String) -> Unit,
    onSend: () -> Unit,
    isEnabled: Boolean,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        tonalElevation = 2.dp,
        shape = RoundedCornerShape(24.dp)
    ) {
        Row(
            modifier = Modifier.padding(4.dp),
            verticalAlignment = Alignment.Bottom
        ) {
            OutlinedTextField(
                value = value,
                onValueChange = onValueChange,
                modifier = Modifier.weight(1f),
                placeholder = { Text("Ask about airports, rules...") },
                enabled = isEnabled,
                maxLines = 4,
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = { onSend() }),
                shape = RoundedCornerShape(20.dp),
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = MaterialTheme.colorScheme.primary,
                    unfocusedBorderColor = MaterialTheme.colorScheme.outline.copy(alpha = 0.3f)
                )
            )
            
            Spacer(modifier = Modifier.width(8.dp))
            
            FilledIconButton(
                onClick = onSend,
                enabled = isEnabled && value.isNotBlank(),
                modifier = Modifier.size(48.dp)
            ) {
                Icon(
                    imageVector = Icons.Default.Send,
                    contentDescription = "Send"
                )
            }
        }
    }
}

/**
 * Parse markdown text into AnnotatedString with styling
 * Supports: **bold**, *italic*, `inline code`, headers (#), bullet points, and tables
 */
private fun parseMarkdown(text: String): AnnotatedString {
    // Pre-process: convert markdown tables to readable list format
    val processedText = convertMarkdownTables(text)
    
    return buildAnnotatedString {
        var i = 0
        val lines = processedText.lines()
        
        lines.forEachIndexed { lineIndex, line ->
            var processedLine = line
            
            // Skip table separator lines (|---|---|)
            if (processedLine.matches(Regex("^\\|?[-:|\\s]+\\|?$"))) {
                // Skip separator lines
                return@forEachIndexed
            }
            
            // Handle headers (# Header)
            when {
                processedLine.startsWith("### ") -> {
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = 16.sp)) {
                        append(processedLine.removePrefix("### "))
                    }
                }
                processedLine.startsWith("## ") -> {
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = 18.sp)) {
                        append(processedLine.removePrefix("## "))
                    }
                }
                processedLine.startsWith("# ") -> {
                    withStyle(SpanStyle(fontWeight = FontWeight.Bold, fontSize = 20.sp)) {
                        append(processedLine.removePrefix("# "))
                    }
                }
                processedLine.startsWith("- ") || processedLine.startsWith("* ") -> {
                    // Bullet points
                    append("  • ")
                    parseInlineMarkdown(this, processedLine.substring(2))
                }
                processedLine.matches(Regex("^\\d+\\.\\s.*")) -> {
                    // Numbered list
                    val num = processedLine.takeWhile { it.isDigit() || it == '.' || it == ' ' }
                    append("  $num")
                    parseInlineMarkdown(this, processedLine.removePrefix(num))
                }
                else -> {
                    parseInlineMarkdown(this, processedLine)
                }
            }
            
            if (lineIndex < lines.size - 1) {
                append("\n")
            }
        }
    }
}

/**
 * Convert markdown tables to a more readable list format
 * Since Text composables can't render tables, we format them as labeled entries
 */
private fun convertMarkdownTables(text: String): String {
    val lines = text.lines().toMutableList()
    val result = StringBuilder()
    var i = 0
    var headers: List<String>? = null
    
    while (i < lines.size) {
        val line = lines[i]
        
        // Check if this is a table row (contains | and is not just separators)
        if (line.contains("|") && !line.matches(Regex("^\\|?[-:|\\s]+\\|?$"))) {
            val cells = line.split("|")
                .map { it.trim() }
                .filter { it.isNotEmpty() }
            
            // Check if next line is separator (this is header row)
            if (i + 1 < lines.size && lines[i + 1].matches(Regex("^\\|?[-:|\\s]+\\|?$"))) {
                headers = cells
                i += 2 // Skip header and separator
                continue
            }
            
            // This is a data row - format it nicely
            if (headers != null && cells.size >= headers.size) {
                // Format as: "• ICAO: EDDR | Name: Saarbrücken | Distance: 0nm"
                val formattedRow = cells.mapIndexed { index, cell ->
                    if (index < headers.size) {
                        "${headers[index]}: $cell"
                    } else {
                        cell
                    }
                }.joinToString(" | ")
                result.appendLine("• $formattedRow")
            } else if (cells.isNotEmpty()) {
                // No headers - just format cells
                result.appendLine("• ${cells.joinToString(" | ")}")
            }
        } else if (!line.matches(Regex("^\\|?[-:|\\s]+\\|?$"))) {
            // Not a table row and not a separator - keep as is
            result.appendLine(line)
        }
        // Skip separator lines silently
        
        i++
    }
    
    return result.toString().trimEnd()
}

/**
 * Parse inline markdown: **bold**, *italic*, `code`
 */
private fun parseInlineMarkdown(builder: AnnotatedString.Builder, text: String) {
    var remaining = text
    
    while (remaining.isNotEmpty()) {
        when {
            // Bold: **text**
            remaining.startsWith("**") -> {
                val endIndex = remaining.indexOf("**", 2)
                if (endIndex > 2) {
                    builder.withStyle(SpanStyle(fontWeight = FontWeight.Bold)) {
                        append(remaining.substring(2, endIndex))
                    }
                    remaining = remaining.substring(endIndex + 2)
                } else {
                    builder.append("**")
                    remaining = remaining.substring(2)
                }
            }
            // Italic: *text*
            remaining.startsWith("*") && !remaining.startsWith("**") -> {
                val endIndex = remaining.indexOf("*", 1)
                if (endIndex > 1) {
                    builder.withStyle(SpanStyle(fontStyle = FontStyle.Italic)) {
                        append(remaining.substring(1, endIndex))
                    }
                    remaining = remaining.substring(endIndex + 1)
                } else {
                    builder.append("*")
                    remaining = remaining.substring(1)
                }
            }
            // Inline code: `code`
            remaining.startsWith("`") -> {
                val endIndex = remaining.indexOf("`", 1)
                if (endIndex > 1) {
                    builder.withStyle(SpanStyle(
                        fontFamily = FontFamily.Monospace,
                        background = androidx.compose.ui.graphics.Color(0xFFE8E8E8)
                    )) {
                        append(" ${remaining.substring(1, endIndex)} ")
                    }
                    remaining = remaining.substring(endIndex + 1)
                } else {
                    builder.append("`")
                    remaining = remaining.substring(1)
                }
            }
            else -> {
                // Regular text - find next special character
                val nextBold = remaining.indexOf("**").takeIf { it >= 0 } ?: Int.MAX_VALUE
                val nextItalic = remaining.indexOf("*").takeIf { it >= 0 } ?: Int.MAX_VALUE
                val nextCode = remaining.indexOf("`").takeIf { it >= 0 } ?: Int.MAX_VALUE
                val nextSpecial = minOf(nextBold, nextItalic, nextCode)
                
                if (nextSpecial == Int.MAX_VALUE) {
                    builder.append(remaining)
                    remaining = ""
                } else {
                    builder.append(remaining.substring(0, nextSpecial))
                    remaining = remaining.substring(nextSpecial)
                }
            }
        }
    }
}

/**
 * Section displaying suggested follow-up questions from the AI.
 * Matches web UI design: vertical list with colored category badges.
 */
@Composable
private fun SuggestedQueriesSection(
    suggestions: List<SuggestedQuery>,
    onSuggestionClick: (SuggestedQuery) -> Unit
) {
    Surface(
        modifier = Modifier.fillMaxWidth(),
        color = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f),
        shape = RoundedCornerShape(12.dp)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Header with lightbulb icon
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "💡",
                    style = MaterialTheme.typography.titleMedium
                )
                Text(
                    text = "You might also want to ask:",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }
            
            // Vertical list of suggestions (like web UI)
            suggestions.forEach { suggestion ->
                Surface(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onSuggestionClick(suggestion) },
                    color = MaterialTheme.colorScheme.surface,
                    shape = RoundedCornerShape(8.dp),
                    border = androidx.compose.foundation.BorderStroke(
                        1.dp,
                        androidx.compose.ui.graphics.Color(0xFF4285F4).copy(alpha = 0.3f)
                    )
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        // Category badge with vibrant color
                        suggestion.category?.let { category ->
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = getCategoryColor(category)
                            ) {
                                Text(
                                    text = category.uppercase(),
                                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                    style = MaterialTheme.typography.labelSmall,
                                    fontWeight = FontWeight.Bold,
                                    color = androidx.compose.ui.graphics.Color.White
                                )
                            }
                        }
                        // Query text
                        Text(
                            text = suggestion.text,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurface
                        )
                    }
                }
            }
        }
    }
}

/**
 * Get color for suggestion category badge - matches web UI colors exactly.
 */
@Composable
private fun getCategoryColor(category: String): androidx.compose.ui.graphics.Color {
    return when (category.lowercase()) {
        "route", "routing" -> androidx.compose.ui.graphics.Color(0xFF6C5DD3) // Purple
        "rules" -> androidx.compose.ui.graphics.Color(0xFF4285F4) // Blue
        "details" -> androidx.compose.ui.graphics.Color(0xFF27AE60) // Green
        "pricing" -> androidx.compose.ui.graphics.Color(0xFFE67E22) // Orange
        "airports" -> androidx.compose.ui.graphics.Color(0xFF4285F4) // Blue
        "weather" -> androidx.compose.ui.graphics.Color(0xFF3498DB) // Light blue
        else -> MaterialTheme.colorScheme.secondary
    }
}
