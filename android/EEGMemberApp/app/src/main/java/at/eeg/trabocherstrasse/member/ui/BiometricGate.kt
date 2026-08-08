package at.eeg.trabocherstrasse.member.ui

import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import at.eeg.trabocherstrasse.member.core.SessionManager

@Composable fun BiometricGate(session: SessionManager, content: @Composable () -> Unit) {
    val activity = LocalContext.current as FragmentActivity
    val lifecycle = LocalLifecycleOwner.current
    var locked by remember { mutableStateOf(session.biometricEnabled()) }
    var error by remember { mutableStateOf<String?>(null) }

    fun unlock() {
        if (!session.biometricEnabled()) { locked = false; return }
        val allowed = BiometricManager.Authenticators.BIOMETRIC_STRONG or BiometricManager.Authenticators.DEVICE_CREDENTIAL
        if (BiometricManager.from(activity).canAuthenticate(allowed) != BiometricManager.BIOMETRIC_SUCCESS) {
            error = "Auf diesem Gerät ist keine Displaysperre oder Biometrie eingerichtet."
            return
        }
        BiometricPrompt(
            activity,
            ContextCompat.getMainExecutor(activity),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) { locked = false; error = null }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) { error = errString.toString() }
            },
        ).authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle("EEG-App entsperren")
                .setSubtitle("Persönliche Energie- und Abrechnungsdaten schützen")
                .setAllowedAuthenticators(allowed)
                .build(),
        )
    }

    DisposableEffect(lifecycle, session.biometricEnabled()) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_STOP && session.biometricEnabled()) locked = true
            if (event == Lifecycle.Event.ON_START && locked) unlock()
        }
        lifecycle.lifecycle.addObserver(observer)
        if (locked) unlock()
        onDispose { lifecycle.lifecycle.removeObserver(observer) }
    }

    if (!locked) content() else Column(
        Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Default.Lock, null, tint = MaterialTheme.colorScheme.primary)
        Text("EEG-App gesperrt", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(12.dp))
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(bottom = 8.dp)) }
        Button(onClick = ::unlock) { Text("Entsperren") }
    }
}
