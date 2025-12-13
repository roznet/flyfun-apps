package me.zhaoqian.flyfun.ui.map

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import me.zhaoqian.flyfun.viewmodel.AirportFilters

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun FiltersDialog(
    currentFilters: AirportFilters,
    onApply: (AirportFilters) -> Unit,
    onClear: () -> Unit,
    onDismiss: () -> Unit
) {
    var filters by remember { mutableStateOf(currentFilters) }
    
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Filter Airports") },
        text = {
            Column(
                modifier = Modifier
                    .verticalScroll(rememberScrollState())
                    .padding(vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Search field
                OutlinedTextField(
                    value = filters.searchQuery ?: "",
                    onValueChange = { filters = filters.copy(searchQuery = it.ifBlank { null }) },
                    label = { Text("Search") },
                    placeholder = { Text("Airport name or ICAO") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                // Country filter
                OutlinedTextField(
                    value = filters.country ?: "",
                    onValueChange = { filters = filters.copy(country = it.uppercase().ifBlank { null }) },
                    label = { Text("Country Code") },
                    placeholder = { Text("e.g., DE, FR, IT") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                // Procedure type dropdown
                var procedureExpanded by remember { mutableStateOf(false) }
                val procedureOptions = listOf("", "ILS", "VOR", "NDB", "RNAV", "VISUAL")
                
                ExposedDropdownMenuBox(
                    expanded = procedureExpanded,
                    onExpandedChange = { procedureExpanded = !procedureExpanded }
                ) {
                    OutlinedTextField(
                        value = filters.procedureType ?: "Any",
                        onValueChange = {},
                        readOnly = true,
                        label = { Text("Procedure Type") },
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = procedureExpanded) },
                        modifier = Modifier
                            .menuAnchor()
                            .fillMaxWidth()
                    )
                    ExposedDropdownMenu(
                        expanded = procedureExpanded,
                        onDismissRequest = { procedureExpanded = false }
                    ) {
                        procedureOptions.forEach { option ->
                            DropdownMenuItem(
                                text = { Text(option.ifBlank { "Any" }) },
                                onClick = {
                                    filters = filters.copy(procedureType = option.ifBlank { null })
                                    procedureExpanded = false
                                }
                            )
                        }
                    }
                }
                
                // Runway minimum length
                OutlinedTextField(
                    value = filters.runwayMinLength?.toString() ?: "",
                    onValueChange = { 
                        filters = filters.copy(runwayMinLength = it.toIntOrNull()) 
                    },
                    label = { Text("Min Runway Length (ft)") },
                    placeholder = { Text("e.g., 3000") },
                    modifier = Modifier.fillMaxWidth(),
                    singleLine = true
                )
                
                // Toggle filters
                Divider(modifier = Modifier.padding(vertical = 8.dp))
                
                // Has ILS
                FilterCheckbox(
                    checked = filters.hasIls == true,
                    onCheckedChange = { 
                        filters = filters.copy(hasIls = if (it) true else null) 
                    },
                    label = "Has ILS Approach"
                )
                
                // Point of Entry
                FilterCheckbox(
                    checked = filters.pointOfEntry == true,
                    onCheckedChange = { 
                        filters = filters.copy(pointOfEntry = if (it) true else null) 
                    },
                    label = "Border Crossing (Point of Entry)"
                )
            }
        },
        confirmButton = {
            Button(onClick = { onApply(filters) }) {
                Text("Apply")
            }
        },
        dismissButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                TextButton(onClick = onClear) {
                    Text("Clear All")
                }
                TextButton(onClick = onDismiss) {
                    Text("Cancel")
                }
            }
        }
    )
}

@Composable
private fun FilterCheckbox(
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    label: String
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .toggleable(
                value = checked,
                onValueChange = onCheckedChange,
                role = Role.Checkbox
            )
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Checkbox(
            checked = checked,
            onCheckedChange = null
        )
        Spacer(modifier = Modifier.width(12.dp))
        Text(label)
    }
}
