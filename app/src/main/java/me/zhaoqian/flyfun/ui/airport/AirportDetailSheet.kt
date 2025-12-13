package me.zhaoqian.flyfun.ui.airport

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import me.zhaoqian.flyfun.data.models.*
import me.zhaoqian.flyfun.ui.theme.*

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun AirportDetailSheet(
    airport: Airport,
    airportDetail: AirportDetail?,
    selectedPersona: String,
    onPersonaChange: (String) -> Unit,
    onDismiss: () -> Unit
) {
    var selectedTab by remember { mutableIntStateOf(0) }
    val tabs = listOf("Details", "AIP Data", "Rules", "Relevance")
    
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(bottom = 32.dp)
    ) {
        // Header
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column {
                Text(
                    text = airport.name,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "${airport.icao} • ${airport.country}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            
            // GA Score badge
            airport.gaScores?.get(selectedPersona)?.let { score ->
                ScoreBadge(score = score)
            }
        }
        
        // Tabs
        TabRow(selectedTabIndex = selectedTab) {
            tabs.forEachIndexed { index, title ->
                Tab(
                    selected = selectedTab == index,
                    onClick = { selectedTab = index },
                    text = { Text(title) }
                )
            }
        }
        
        // Tab content
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .heightIn(min = 300.dp, max = 500.dp)
        ) {
            when (selectedTab) {
                0 -> DetailsTab(airport, airportDetail)
                1 -> AipDataTab(airportDetail)
                2 -> RulesTab(airport.country)
                3 -> RelevanceTab(airport, selectedPersona, onPersonaChange)
            }
        }
    }
}

@Composable
private fun ScoreBadge(score: Double) {
    val (color, label) = when {
        score >= 0.8 -> ScoreExcellent to "Excellent"
        score >= 0.6 -> ScoreGood to "Good"
        score >= 0.4 -> ScoreModerate to "Moderate"
        else -> ScorePoor to "Poor"
    }
    
    Surface(
        shape = MaterialTheme.shapes.small,
        color = color.copy(alpha = 0.2f)
    ) {
        Text(
            text = "${(score * 100).toInt()}% $label",
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            style = MaterialTheme.typography.labelMedium,
            color = color
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DetailsTab(airport: Airport, detail: AirportDetail?) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Basic info
        item {
            DetailSection(title = "Location") {
                DetailRow("Coordinates", "${airport.latitude}, ${airport.longitude}")
                airport.elevationFt?.let { DetailRow("Elevation", "$it ft") }
            }
        }
        
        // Runways
        detail?.runways?.let { runways ->
            if (runways.isNotEmpty()) {
                item {
                    DetailSection(title = "Runways") {
                        runways.forEach { runway ->
                            RunwayCard(runway)
                        }
                    }
                }
            }
        }
        
        // Procedures
        detail?.procedures?.let { procedures ->
            if (procedures.isNotEmpty()) {
                item {
                    DetailSection(title = "Procedures") {
                        procedures.groupBy { it.type }.forEach { (type, procs) ->
                            Text(
                                text = type,
                                style = MaterialTheme.typography.labelLarge,
                                fontWeight = FontWeight.Medium
                            )
                            FlowRow(
                                horizontalArrangement = Arrangement.spacedBy(4.dp),
                                modifier = Modifier.padding(vertical = 4.dp)
                            ) {
                                procs.forEach { proc ->
                                    AssistChip(
                                        onClick = {},
                                        label = { Text(proc.name) }
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
        
        // Features
        item {
            DetailSection(title = "Features") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (airport.hasIls) {
                        AssistChip(
                            onClick = {},
                            label = { Text("ILS") },
                            leadingIcon = { Icon(imageVector = Icons.Default.FlightLand, contentDescription = null, Modifier.size(16.dp)) }
                        )
                    }
                    if (airport.hasVor) {
                        AssistChip(onClick = {}, label = { Text("VOR") })
                    }
                    if (airport.pointOfEntry) {
                        AssistChip(
                            onClick = {},
                            label = { Text("Border Crossing") },
                            leadingIcon = { Icon(imageVector = Icons.Default.Flag, contentDescription = null, Modifier.size(16.dp)) }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun DetailSection(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column {
        Text(
            text = title,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        content()
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, fontWeight = FontWeight.Medium)
    }
}

@Composable
private fun RunwayCard(runway: Runway) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column {
                Text(runway.identifier, fontWeight = FontWeight.Bold)
                runway.surface?.let { 
                    Text(it, style = MaterialTheme.typography.bodySmall) 
                }
            }
            Column(horizontalAlignment = Alignment.End) {
                runway.lengthFt?.let { Text("$it ft") }
                if (runway.lighted) {
                    Text("Lighted", style = MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}

@Composable
private fun AipDataTab(detail: AirportDetail?) {
    if (detail?.aipEntries.isNullOrEmpty()) {
        EmptyTabContent("No AIP data available")
    } else {
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            val grouped = detail!!.aipEntries.groupBy { it.section }
            grouped.forEach { (section, entries) ->
                item {
                    Text(
                        text = section,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(vertical = 8.dp)
                    )
                }
                items(entries) { entry ->
                    AipEntryCard(entry)
                }
            }
        }
    }
}

@Composable
private fun AipEntryCard(entry: AipEntry) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            entry.stdField?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.primary
                )
            }
            Text(entry.content, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun RulesTab(countryCode: String) {
    // TODO: Implement rules fetching via ViewModel
    EmptyTabContent("Rules for $countryCode - Coming soon")
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun RelevanceTab(
    airport: Airport,
    selectedPersona: String,
    onPersonaChange: (String) -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp)
    ) {
        // GA Summary
        airport.gaSummary?.let { summary ->
            if (summary.hasData) {
                summary.summaryText?.let { 
                    Text(it, style = MaterialTheme.typography.bodyMedium)
                }
                Spacer(modifier = Modifier.height(16.dp))
                
                // Tags
                summary.tags?.let { tags ->
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        tags.forEach { tag ->
                            SuggestionChip(onClick = {}, label = { Text(tag) })
                        }
                    }
                }
                
                summary.hassleLevel?.let {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("Hassle Level: $it", fontWeight = FontWeight.Medium)
                }
            } else {
                EmptyTabContent("No GA friendliness data available")
            }
        } ?: EmptyTabContent("No GA friendliness data available")
    }
}

@Composable
private fun EmptyTabContent(message: String) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Text(
            text = message,
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}
