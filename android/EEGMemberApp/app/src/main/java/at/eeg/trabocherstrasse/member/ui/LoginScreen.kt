package at.eeg.trabocherstrasse.member.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.QrCodeScanner
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.platform.LocalContext
import at.eeg.trabocherstrasse.member.core.SessionManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import com.google.mlkit.vision.barcode.common.Barcode

@Composable fun LoginScreen(session: SessionManager, scope: CoroutineScope) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var email by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf<String?>(null) }
    val context = LocalContext.current
    val scanner = remember(context) {
        GmsBarcodeScanning.getClient(
            context,
            GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).enableAutoZoom().build(),
        )
    }

    fun run(action: suspend () -> Unit) {
        scope.launch {
            busy = true; message = null
            runCatching { action() }.onFailure { message = it.message ?: "Aktion fehlgeschlagen." }
            busy = false
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(horizontal = 24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Icon(Icons.Default.Bolt, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(58.dp))
        Spacer(Modifier.height(12.dp))
        Text("EEG Trabocherstraße", style = MaterialTheme.typography.headlineSmall)
        Text("Sicher mit Ihrem Mitgliedskonto verbinden", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(28.dp))
        OutlinedTextField(username, { username = it }, label = { Text("Benutzername oder E-Mail") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(
            password, { password = it }, label = { Text("Passwort") }, singleLine = true,
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Done),
            modifier = Modifier.fillMaxWidth(),
        )
        Button(
            onClick = { run { session.login(username, password) } },
            enabled = !busy && username.isNotBlank() && password.isNotBlank(),
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        ) { if (busy) CircularProgressIndicator(Modifier.size(18.dp)) else Text("Anmelden") }
        HorizontalDivider(Modifier.padding(vertical = 22.dp))
        OutlinedTextField(email, { email = it }, label = { Text("E-Mail für Verbindungslink") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedButton(
            onClick = { run { message = session.requestLink(email) } },
            enabled = !busy && email.contains('@'), modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        ) { Text("Verbindungslink senden") }
        OutlinedTextField(code, { code = it.filter(Char::isLetterOrDigit).take(12) }, label = { Text("Einmalcode") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedButton(
            onClick = { run { session.connect(code = code) } },
            enabled = !busy && code.length >= 6, modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        ) { Text("Mit Code verbinden") }
        OutlinedButton(
            onClick = {
                run {
                    val value = scanner.startScan().await().rawValue ?: error("Der QR-Code enthält keine Daten.")
                    if (value.startsWith("https://") || value.startsWith("eegtrabocherstrasse://")) session.connectFromUri(value)
                    else session.connect(code = value.filter(Char::isLetterOrDigit))
                }
            },
            enabled = !busy, modifier = Modifier.fillMaxWidth().padding(top = 8.dp),
        ) { Icon(Icons.Default.QrCodeScanner, null); Text(" QR-Code scannen") }
        message?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 12.dp)) }
    }
}
