package me.zhaoqian.flyfun.ui

import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.Map
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import me.zhaoqian.flyfun.ui.map.MapScreen
import me.zhaoqian.flyfun.ui.chat.ChatScreen

/**
 * Main app composable with navigation.
 */
@Composable
fun FlyFunApp() {
    val navController = rememberNavController()
    var selectedTab by remember { mutableIntStateOf(0) }
    
    Scaffold(
        bottomBar = {
            NavigationBar {
                NavigationBarItem(
                    icon = { Icon(imageVector = Icons.Default.Map, contentDescription = "Map") },
                    label = { Text("Map") },
                    selected = selectedTab == 0,
                    onClick = { 
                        selectedTab = 0
                        navController.navigate("map") {
                            popUpTo("map") { inclusive = true }
                        }
                    }
                )
                NavigationBarItem(
                    icon = { Icon(imageVector = Icons.Default.Chat, contentDescription = "Chat") },
                    label = { Text("Assistant") },
                    selected = selectedTab == 1,
                    onClick = { 
                        selectedTab = 1
                        navController.navigate("chat") {
                            popUpTo("map")
                        }
                    }
                )
            }
        }
    ) { paddingValues ->
        NavHost(
            navController = navController,
            startDestination = "map",
            modifier = Modifier.padding(paddingValues)
        ) {
            composable("map") {
                MapScreen(
                    onNavigateToChat = {
                        selectedTab = 1
                        navController.navigate("chat")
                    }
                )
            }
            composable("chat") {
                ChatScreen(
                    onNavigateToMap = {
                        selectedTab = 0
                        navController.navigate("map") {
                            popUpTo("map") { inclusive = true }
                        }
                    }
                )
            }
        }
    }
}
