package at.eeg.trabocherstrasse.member.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.Euro
import androidx.compose.material.icons.filled.Home
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import at.eeg.trabocherstrasse.member.core.SessionManager
import at.eeg.trabocherstrasse.member.core.SessionState
import at.eeg.trabocherstrasse.member.push.registerCurrentDeviceForPush

@Composable fun EEGApp(session: SessionManager, initialLink: String?, initialMessageId: Int?, consumeLink: () -> Unit) {
    EEGTheme {
        val state by session.state.collectAsState()
        val scope = rememberCoroutineScope()
        val context = LocalContext.current
        val notificationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { }

        LaunchedEffect(initialLink) {
            if (!initialLink.isNullOrBlank()) {
                runCatching { session.connectFromUri(initialLink) }
                consumeLink()
            }
        }
        LaunchedEffect(state) {
            if (state is SessionState.SignedIn && Build.VERSION.SDK_INT >= 33) {
                notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
            if (state is SessionState.SignedIn) registerCurrentDeviceForPush(context, session)
        }
        LaunchedEffect(state, initialMessageId) {
            if (state is SessionState.SignedIn && initialMessageId != null) {
                runCatching { session.empty("messages/$initialMessageId/read") }
            }
        }

        when (val current = state) {
            SessionState.Restoring -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            SessionState.SignedOut -> LoginScreen(session, scope)
            is SessionState.SignedIn -> BiometricGate(session) { MainShell(session, current.memberName) }
        }
    }
}

private data class MainDestination(val label: String, val icon: @Composable () -> Unit)

@Composable private fun MainShell(session: SessionManager, memberName: String) {
    var selected by remember { mutableIntStateOf(0) }
    val destinations = listOf(
        MainDestination("Übersicht") { Icon(Icons.Default.Home, null) },
        MainDestination("Energie") { Icon(Icons.Default.Bolt, null) },
        MainDestination("Preise") { Icon(Icons.Default.Euro, null) },
        MainDestination("Mein Konto") { Icon(Icons.Default.AccountCircle, null) },
    )
    Scaffold(
        bottomBar = {
            NavigationBar {
                destinations.forEachIndexed { index, item ->
                    NavigationBarItem(
                        selected = selected == index,
                        onClick = { selected = index },
                        icon = item.icon,
                        label = { Text(item.label, maxLines = 1) },
                    )
                }
            }
        },
    ) { padding ->
        when (selected) {
            0 -> OverviewScreen(session, memberName, padding)
            1 -> EnergyScreen(session, padding)
            2 -> PricesScreen(session, padding)
            else -> AccountScreen(session, padding)
        }
    }
}
