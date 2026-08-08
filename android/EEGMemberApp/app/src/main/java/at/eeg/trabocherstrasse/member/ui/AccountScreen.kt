package at.eeg.trabocherstrasse.member.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.location.Location
import android.media.MediaPlayer
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.AddAPhoto
import androidx.compose.material.icons.filled.AccountCircle
import androidx.compose.material.icons.filled.AttachFile
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Description
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Notifications
import androidx.compose.material.icons.filled.PermMedia
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import at.eeg.trabocherstrasse.member.BuildConfig
import at.eeg.trabocherstrasse.member.R
import at.eeg.trabocherstrasse.member.core.AccountResponse
import at.eeg.trabocherstrasse.member.core.AccountSummary
import at.eeg.trabocherstrasse.member.core.Contract
import at.eeg.trabocherstrasse.member.core.ContractsResponse
import at.eeg.trabocherstrasse.member.core.Invoice
import at.eeg.trabocherstrasse.member.core.InvoiceDetailResponse
import at.eeg.trabocherstrasse.member.core.InvoicesResponse
import at.eeg.trabocherstrasse.member.core.MeResponse
import at.eeg.trabocherstrasse.member.core.Member
import at.eeg.trabocherstrasse.member.core.MemberFeedbackResponse
import at.eeg.trabocherstrasse.member.core.NotificationPreferences
import at.eeg.trabocherstrasse.member.core.NotificationPreferencesResponse
import at.eeg.trabocherstrasse.member.core.OrganizationInfo
import at.eeg.trabocherstrasse.member.core.ProfileUpdate
import at.eeg.trabocherstrasse.member.core.SessionManager
import at.eeg.trabocherstrasse.member.core.UpdateResponse
import at.eeg.trabocherstrasse.member.core.UploadAttachment
import at.eeg.trabocherstrasse.member.core.dateText
import at.eeg.trabocherstrasse.member.core.euro
import at.eeg.trabocherstrasse.member.core.kwh
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import kotlinx.coroutines.launch
import kotlinx.coroutines.tasks.await
import java.io.File
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

private enum class AccountSection(val title: String) {
    CARD("Ausweis"), BALANCE("Kontostand"), INVOICES("Rechnungen"), CONTRACTS("Verträge"), PROFILE("Meine Daten"), SETTINGS("Einstellungen")
}

@Composable fun AccountScreen(session: SessionManager, contentPadding: PaddingValues) {
    var section by remember { mutableStateOf(AccountSection.CARD) }
    Column(Modifier.fillMaxSize().padding(contentPadding)) {
        Text("Mein Konto", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(horizontal = 12.dp, vertical = 10.dp))
        Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            AccountSection.entries.forEach { item -> FilterChip(selected = section == item, onClick = { section = item }, label = { Text(item.title) }) }
        }
        when (section) {
            AccountSection.CARD -> MemberCardAndFeedback(session)
            AccountSection.BALANCE -> BalanceSection(session)
            AccountSection.INVOICES -> InvoicesSection(session)
            AccountSection.CONTRACTS -> ContractsSection(session)
            AccountSection.PROFILE -> ProfileSection(session)
            AccountSection.SETTINGS -> SettingsSection(session)
        }
    }
}

@Composable private fun MemberCardAndFeedback(session: SessionManager) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var me by remember { mutableStateOf<MeResponse?>(null) }
    var contracts by remember { mutableStateOf<List<Contract>>(emptyList()) }
    var photo by remember { mutableStateOf<ByteArray?>(null) }
    var message by remember { mutableStateOf("") }
    var attachments by remember { mutableStateOf<List<UploadAttachment>>(emptyList()) }
    var result by remember { mutableStateOf<String?>(null) }
    var sending by remember { mutableStateOf(false) }
    var pendingSend by remember { mutableStateOf(false) }
    var cameraUri by remember { mutableStateOf<Uri?>(null) }

    fun add(uri: Uri) {
        val item = readAttachment(context, uri) ?: run { result = "Die Datei konnte nicht gelesen werden."; return }
        if (attachments.size >= 5 || attachments.sumOf { it.bytes.size } + item.bytes.size > 15 * 1024 * 1024) {
            result = "Maximal fünf Anlagen und insgesamt 15 MB sind erlaubt."
        } else attachments = attachments + item
    }
    val photos = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(5)) { uris -> uris.forEach(::add) }
    val documents = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris -> uris.forEach(::add) }
    val camera = rememberLauncherForActivityResult(ActivityResultContracts.TakePicture()) { ok -> if (ok) cameraUri?.let(::add) }
    val cameraPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) cameraUri = createCameraUri(context).also(camera::launch) else result = "Der Kamerazugriff wurde nicht erlaubt."
    }
    val locationPermission = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { permissions ->
        if (permissions.values.any { it }) pendingSend = true else result = "Zum Senden ist der Standortzugriff erforderlich."
    }

    suspend fun send() {
        sending = true
        runCatching {
            val location = currentLocation(context)
            val response: MemberFeedbackResponse = session.multipart(
                "member-feedback",
                mapOf(
                    "message" to message.trim(), "latitude" to location.latitude.toString(),
                    "longitude" to location.longitude.toString(), "location_accuracy_m" to location.accuracy.toString(),
                ), attachments,
            )
            message = ""; attachments = emptyList()
            result = "Nachricht #${response.id} wurde sicher an die EEG übermittelt."
        }.onFailure { result = it.message ?: "Nachricht konnte nicht gesendet werden." }
        sending = false
    }
    LaunchedEffect(pendingSend) { if (pendingSend) { pendingSend = false; send() } }
    LaunchedEffect(Unit) {
        me = runCatching { session.get<MeResponse>("me") }.getOrNull()
        contracts = runCatching { session.get<ContractsResponse>("contracts").contracts }.getOrDefault(emptyList())
        photo = runCatching { session.bytes("me/photo", "image/*") }.getOrNull()
    }

    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        me?.let { MembershipCard(it.member, it.organization, contracts, photo) } ?: CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally))
        Card {
            Column(Modifier.padding(13.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("Nachricht an die EEG", style = MaterialTheme.typography.titleMedium)
                OutlinedTextField(message, { message = it.take(4000) }, label = { Text("Nachricht, Frage oder Dokumentation") }, minLines = 3, maxLines = 7, modifier = Modifier.fillMaxWidth())
                attachments.forEachIndexed { index, file ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(if (file.mimeType == "application/pdf") Icons.Default.PictureAsPdf else Icons.Default.PermMedia, null, tint = MaterialTheme.colorScheme.primary)
                        Text(file.filename, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f).padding(start = 8.dp))
                        IconButton(onClick = { attachments = attachments.filterIndexed { i, _ -> i != index } }) { Icon(Icons.Default.Delete, "Anlage entfernen") }
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    OutlinedButton(onClick = { photos.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, enabled = attachments.size < 5) { Icon(Icons.Default.PermMedia, null); Text("Fotos") }
                    OutlinedButton(onClick = {
                        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED) {
                            cameraUri = createCameraUri(context).also(camera::launch)
                        } else cameraPermission.launch(Manifest.permission.CAMERA)
                    }, enabled = attachments.size < 5) { Icon(Icons.Default.CameraAlt, null); Text("Kamera") }
                    OutlinedButton(onClick = { documents.launch(arrayOf("application/pdf", "image/jpeg", "image/png")) }, enabled = attachments.size < 5) { Icon(Icons.Default.AttachFile, null); Text("Datei") }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.LocationOn, null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
                    Text("Standort und Verbindungs-IP werden beim Senden beigefügt.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant, modifier = Modifier.padding(start = 5.dp))
                }
                Button(
                    onClick = {
                        if (ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED ||
                            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
                        ) pendingSend = true else locationPermission.launch(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.ACCESS_COARSE_LOCATION))
                    },
                    enabled = !sending && (message.isNotBlank() || attachments.isNotEmpty()), modifier = Modifier.fillMaxWidth(),
                ) { if (sending) CircularProgressIndicator(Modifier.size(18.dp)) else Icon(Icons.AutoMirrored.Filled.Send, null); Text(" Sicher an die EEG senden") }
            }
        }
        result?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = if (it.contains("übermittelt")) EEGCommunity else MaterialTheme.colorScheme.error) }
    }
}

@Composable private fun MembershipCard(member: Member, organization: OrganizationInfo?, contracts: List<Contract>, photo: ByteArray?) {
    var back by remember { mutableStateOf(false) }
    val rotation by animateFloatAsState(if (back) 180f else 0f, label = "cardFlip")
    val active = member.active != false
    val gradient = if (active) Brush.linearGradient(listOf(Color(0xFF0F5D59), Color(0xFF319B91), Color(0xFF174542))) else Brush.linearGradient(listOf(Color(0xFF5F1E20), Color(0xFFB1343A)))
    Card(
        modifier = Modifier.fillMaxWidth().aspectRatio(1.586f).graphicsLayer {
            rotationY = rotation; cameraDistance = 14f * density
        }.clickable { back = !back },
        shape = RoundedCornerShape(20.dp), elevation = CardDefaults.cardElevation(10.dp),
    ) {
        Box(Modifier.fillMaxSize().background(gradient).graphicsLayer { if (rotation > 90f) rotationY = 180f }.padding(18.dp)) {
            if (rotation <= 90f) CardFront(member, organization, photo, active) else CardBack(member, organization, contracts)
            if (!active) Text("INAKTIV", color = Color.White.copy(alpha = .7f), style = MaterialTheme.typography.displaySmall, textDecoration = TextDecoration.LineThrough, modifier = Modifier.align(Alignment.Center).graphicsLayer { rotationZ = -16f })
        }
    }
}

@Composable private fun CardFront(member: Member, organization: OrganizationInfo?, photo: ByteArray?, active: Boolean) {
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.SpaceBetween) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Image(painterResource(R.drawable.eeg_app_icon), null, Modifier.size(28.dp).clip(RoundedCornerShape(6.dp)))
            Text("  MITGLIEDSAUSWEIS", color = Color.White, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f)); Text(if (active) "AKTIV" else "INAKTIV", color = Color.White, style = MaterialTheme.typography.labelMedium)
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            val bitmap = photo?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }
            if (bitmap != null) Image(bitmap.asImageBitmap(), null, Modifier.size(56.dp).clip(CircleShape), contentScale = ContentScale.Crop)
            else Icon(Icons.Default.AccountCircle, null, tint = Color.White, modifier = Modifier.size(56.dp))
            Column(Modifier.padding(start = 12.dp)) {
                Text(member.name, color = Color.White, style = MaterialTheme.typography.titleMedium, maxLines = 2)
                Text(organization?.name ?: "EEG Trabocherstraße", color = Color.White.copy(alpha = .9f), style = MaterialTheme.typography.bodySmall)
                Text("Verein · ${organization?.zvr ?: "ZVR"}", color = Color.White.copy(alpha = .72f), style = MaterialTheme.typography.bodySmall)
            }
        }
        Row {
            Column { Text("MITGLIEDSNUMMER", color = Color.White.copy(alpha = .7f), style = MaterialTheme.typography.labelMedium); Text("%06d".format(member.id), color = Color.White, fontFamily = FontFamily.Monospace) }
            Spacer(Modifier.weight(1f))
            Text("Gültig bis ${LocalDate.now().plusYears(1).format(DateTimeFormatter.ofPattern("MM/yyyy"))}", color = Color.White.copy(alpha = .8f), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable private fun CardBack(member: Member, organization: OrganizationInfo?, contracts: List<Contract>) {
    val role = when { !member.consumptionMeter.isNullOrBlank() && !member.generationMeter.isNullOrBlank() -> "Bezieher und Einspeiser"; !member.consumptionMeter.isNullOrBlank() -> "Bezieher"; !member.generationMeter.isNullOrBlank() -> "Einspeiser"; else -> "Mitglied" }
    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Text("MITGLIEDSDETAILS", color = Color.White, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
        HorizontalDivider(color = Color.White.copy(alpha = .35f))
        CardLine("Rolle", role)
        CardLine("Teilnahme", member.teilnahme?.let { "${String.format(Locale.forLanguageTag("de-AT"), "%.0f", it * 100)} %" } ?: "–")
        CardLine("Verträge", "${contracts.size} PDF-Dokument(e)")
        val city = listOfNotNull(member.addressZip, member.addressCity).joinToString(" ")
        if (!member.addressStreet.isNullOrBlank()) CardLine("Adresse", "${member.addressStreet}\n$city")
        if (!organization?.address.isNullOrBlank()) CardLine("EEG", organization!!.address)
    }
}

@Composable private fun CardLine(label: String, value: String) {
    Row(Modifier.fillMaxWidth()) { Text(label, color = Color.White.copy(alpha = .68f), style = MaterialTheme.typography.bodySmall); Spacer(Modifier.weight(1f)); Text(value, color = Color.White, style = MaterialTheme.typography.bodySmall, maxLines = 2) }
}

@Composable private fun BalanceSection(session: SessionManager) {
    var account by remember { mutableStateOf<AccountSummary?>(null) }; var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { runCatching { account = session.get<AccountResponse>("account").account }.onFailure { error = it.message } }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        account?.let { data ->
            Card { Column(Modifier.padding(16.dp)) { Text("Aktueller Kontostand", style = MaterialTheme.typography.labelLarge); Text(data.balance.euro(), style = MaterialTheme.typography.displaySmall, color = if (data.balance >= 0) EEGCommunity else MaterialTheme.colorScheme.error); Text("Offene Forderungen ${data.openClaims.euro()} · Gutschriften ${data.openCredits.euro()}", style = MaterialTheme.typography.bodySmall) } }
            Text("Buchungen", style = MaterialTheme.typography.titleMedium)
            data.history.forEach { event -> Card { Row(Modifier.fillMaxWidth().padding(12.dp)) { Column(Modifier.weight(1f)) { Text(event.label, fontWeight = FontWeight.Medium); Text(dateText(event.date), style = MaterialTheme.typography.bodySmall) }; Text(event.amount.euro(), fontFamily = FontFamily.Monospace, fontWeight = FontWeight.SemiBold) } } }
        } ?: CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally))
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    }
}

@Composable private fun InvoicesSection(session: SessionManager) {
    var invoices by remember { mutableStateOf<List<Invoice>>(emptyList()) }; var selected by remember { mutableStateOf<Invoice?>(null) }; var detail by remember { mutableStateOf<InvoiceDetailResponse?>(null) }; var pdf by remember { mutableStateOf<ByteArray?>(null) }; var error by remember { mutableStateOf<String?>(null) }; val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { runCatching { invoices = session.get<InvoicesResponse>("invoices").invoices.sortedByDescending { it.createdAt } }.onFailure { error = it.message } }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        invoices.forEach { invoice -> Card(Modifier.fillMaxWidth().clickable { selected = invoice; detail = null; scope.launch { runCatching { detail = session.get<InvoiceDetailResponse>("invoices/${invoice.id}") }.onFailure { error = it.message } } }) { Row(Modifier.padding(13.dp), verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Default.Description, null, tint = MaterialTheme.colorScheme.primary); Column(Modifier.weight(1f).padding(start = 10.dp)) { Text("Abrechnung ${dateText(invoice.periodFrom)} – ${dateText(invoice.periodTo)}", fontWeight = FontWeight.SemiBold); Text(if (invoice.isPreliminary) "VORLÄUFIG" else if (invoice.paid) "Bezahlt" else invoice.status, style = MaterialTheme.typography.bodySmall, color = if (invoice.isPreliminary) MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant) }; Text(invoice.netTotal.euro(), fontFamily = FontFamily.Monospace) } }
        }
        if (invoices.isEmpty()) Text("Keine Abrechnungen vorhanden.")
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    }
    selected?.let { invoice ->
        AlertDialog(onDismissRequest = { selected = null }, title = { Text("Abrechnung") }, text = { Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) { Text("${dateText(invoice.periodFrom)} – ${dateText(invoice.periodTo)}"); Text(invoice.netTotal.euro(), style = MaterialTheme.typography.headlineSmall); if (invoice.isPreliminary) Text("Diese Abrechnung ist vorläufig. Bitte noch keine Überweisung tätigen; Beträge können sich ändern.", color = MaterialTheme.colorScheme.error); detail?.items?.forEach { item -> Row(Modifier.fillMaxWidth()) { Text(if (item.type == "consumption") "Strombezug" else "Einspeisung", modifier = Modifier.weight(1f)); Text("${item.kwh.kwh()} · ${item.amountEur.euro()}", fontFamily = FontFamily.Monospace) } } ?: CircularProgressIndicator(Modifier.size(20.dp)) } }, confirmButton = { Button(onClick = { scope.launch { runCatching { pdf = session.bytes("invoices/${invoice.id}/pdf", "application/pdf") }.onFailure { error = it.message } } }) { Text("PDF öffnen") } }, dismissButton = { OutlinedButton(onClick = { selected = null }) { Text("Schließen") } })
    }
    pdf?.let { PdfPreviewDialog("EEG-Abrechnung.pdf", it, onDismiss = { pdf = null }) }
}

@Composable private fun ContractsSection(session: SessionManager) {
    var contracts by remember { mutableStateOf<List<Contract>>(emptyList()) }; var pdf by remember { mutableStateOf<ByteArray?>(null) }; var pdfName by remember { mutableStateOf("Vertrag.pdf") }; val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { contracts = runCatching { session.get<ContractsResponse>("contracts").contracts }.getOrDefault(emptyList()) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        contracts.forEach { contract -> Card(Modifier.fillMaxWidth().clickable { scope.launch { pdfName = contract.filename; pdf = runCatching { session.bytes("contracts/${contract.id}/pdf", "application/pdf") }.getOrNull() } }) { Row(Modifier.padding(13.dp), verticalAlignment = Alignment.CenterVertically) { Icon(Icons.Default.PictureAsPdf, null, tint = MaterialTheme.colorScheme.primary); Column(Modifier.padding(start = 10.dp)) { Text(contract.filename, fontWeight = FontWeight.SemiBold); Text("${contract.type} · ${dateText(contract.uploadedAt)}", style = MaterialTheme.typography.bodySmall) } } } }
        if (contracts.isEmpty()) Text("Keine Verträge hinterlegt.")
    }
    pdf?.let { PdfPreviewDialog(pdfName, it, onDismiss = { pdf = null }) }
}

@Composable private fun ProfileSection(session: SessionManager) {
    val context = LocalContext.current; val scope = rememberCoroutineScope(); var member by remember { mutableStateOf<Member?>(null) }; var message by remember { mutableStateOf<String?>(null) }; var photo by remember { mutableStateOf<ByteArray?>(null) }
    val photoPicker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri -> if (uri != null) { val item = readAttachment(context, uri); if (item != null && item.mimeType.startsWith("image/")) scope.launch { runCatching { session.upload<UpdateResponse>("me/photo", item.bytes, item.mimeType) }.onSuccess { photo = item.bytes; message = "Profilfoto gespeichert." }.onFailure { message = it.message } } } }
    LaunchedEffect(Unit) { member = runCatching { session.get<MeResponse>("me").member }.getOrNull(); photo = runCatching { session.bytes("me/photo", "image/*") }.getOrNull() }
    member?.let { initial -> ProfileForm(initial, photo, onPhoto = { photoPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, onSave = { update -> scope.launch { runCatching { member = session.send<at.eeg.trabocherstrasse.member.core.MemberResponse, ProfileUpdate>("me", "PATCH", update).member; message = "Daten gespeichert." }.onFailure { message = it.message } } }, message = message) } ?: Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
}

@Composable private fun ProfileForm(member: Member, photo: ByteArray?, onPhoto: () -> Unit, onSave: (ProfileUpdate) -> Unit, message: String?) {
    var email by remember(member.id) { mutableStateOf(member.email.orEmpty()) }; var phone by remember(member.id) { mutableStateOf(member.phone.orEmpty()) }; var street by remember(member.id) { mutableStateOf(member.addressStreet.orEmpty()) }; var zip by remember(member.id) { mutableStateOf(member.addressZip.orEmpty()) }; var city by remember(member.id) { mutableStateOf(member.addressCity.orEmpty()) }; var holder by remember(member.id) { mutableStateOf(member.accountHolder.orEmpty()) }; var iban by remember(member.id) { mutableStateOf(member.iban.orEmpty()) }; var bic by remember(member.id) { mutableStateOf(member.bic.orEmpty()) }; var optOut by remember(member.id) { mutableStateOf(member.newsletterOptOut == 1) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) { val bitmap = photo?.let { BitmapFactory.decodeByteArray(it, 0, it.size) }; if (bitmap != null) Image(bitmap.asImageBitmap(), null, Modifier.size(72.dp).clip(CircleShape), contentScale = ContentScale.Crop) else Icon(Icons.Default.AccountCircle, null, Modifier.size(72.dp)); OutlinedButton(onClick = onPhoto, modifier = Modifier.padding(start = 12.dp)) { Icon(Icons.Default.AddAPhoto, null); Text(" Profilfoto") } }
        listOf("E-Mail" to email, "Telefon" to phone, "Straße" to street, "PLZ" to zip, "Ort" to city, "Kontoinhaber" to holder, "IBAN" to iban, "BIC" to bic).forEach { (label, value) -> OutlinedTextField(value, { new -> when (label) { "E-Mail" -> email = new; "Telefon" -> phone = new; "Straße" -> street = new; "PLZ" -> zip = new; "Ort" -> city = new; "Kontoinhaber" -> holder = new; "IBAN" -> iban = new; else -> bic = new } }, label = { Text(label) }, singleLine = true, modifier = Modifier.fillMaxWidth()) }
        Row(verticalAlignment = Alignment.CenterVertically) { Text("Newsletter abbestellen", modifier = Modifier.weight(1f)); Switch(optOut, { optOut = it }) }
        Button(onClick = { onSave(ProfileUpdate(email, phone, street, zip, city, holder, iban, bic, optOut)) }, modifier = Modifier.fillMaxWidth()) { Text("Daten speichern") }
        message?.let { Text(it, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable private fun SettingsSection(session: SessionManager) {
    val context = LocalContext.current; val scope = rememberCoroutineScope(); var prefs by remember { mutableStateOf(NotificationPreferences()) }; var biometric by remember { mutableStateOf(session.biometricEnabled()) }; var message by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) { prefs = runCatching { session.get<NotificationPreferencesResponse>("notification-preferences").preferences }.getOrDefault(prefs) }
    fun update(next: NotificationPreferences) { prefs = next; scope.launch { runCatching { session.send<UpdateResponse, NotificationPreferences>("notification-preferences", "PATCH", next) }.onFailure { message = it.message } } }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        SettingSwitch("Benachrichtigungen", prefs.notificationsEnabled) { update(prefs.copy(notificationsEnabled = it)) }
        SettingSwitch("Eigener EEG-Ton", prefs.soundEnabled) { update(prefs.copy(soundEnabled = it)) }
        SettingSwitch("Abrechnungen", prefs.invoiceNotifications) { update(prefs.copy(invoiceNotifications = it)) }
        SettingSwitch("Gemeinschaftsnachrichten", prefs.communityNotifications) { update(prefs.copy(communityNotifications = it)) }
        SettingSwitch("App mit Biometrie schützen", biometric) { biometric = it; session.setBiometricEnabled(it) }
        OutlinedButton(onClick = { context.startActivity(Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE, context.packageName)) }, modifier = Modifier.fillMaxWidth()) { Icon(Icons.Default.Notifications, null); Text(" Android-Benachrichtigungen") }
        OutlinedButton(onClick = {
            MediaPlayer.create(context, R.raw.eeg_notification)?.apply {
                setOnCompletionListener { it.release() }
                start()
            }
        }, modifier = Modifier.fillMaxWidth()) { Text("EEG-Ton testen") }
        Button(onClick = { scope.launch { session.logout() } }, modifier = Modifier.fillMaxWidth()) { Text("Abmelden") }
        message?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    }
}

@Composable private fun SettingSwitch(title: String, checked: Boolean, onChange: (Boolean) -> Unit) { Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) { Text(title, modifier = Modifier.weight(1f)); Switch(checked, onChange) } }

private fun createCameraUri(context: Context): Uri {
    val directory = File(context.cacheDir, "camera").apply { mkdirs() }
    val file = File(directory, "EEG-Foto-${System.currentTimeMillis()}.jpg")
    return FileProvider.getUriForFile(context, "${context.packageName}.files", file)
}

private fun readAttachment(context: Context, uri: Uri): UploadAttachment? = runCatching {
    val resolver = context.contentResolver
    val mime = resolver.getType(uri) ?: "image/jpeg"
    require(mime in setOf("image/jpeg", "image/png", "application/pdf"))
    val bytes = resolver.openInputStream(uri)!!.use { it.readBytes() }
    require(bytes.size <= 5 * 1024 * 1024)
    val filename = uri.lastPathSegment?.substringAfterLast('/')?.take(180) ?: if (mime == "application/pdf") "Dokument.pdf" else "Foto.jpg"
    UploadAttachment(filename, mime, bytes)
}.getOrNull()

private suspend fun currentLocation(context: Context): Location {
    val fine = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
    val coarse = ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED
    if (!fine && !coarse) throw SecurityException("Standortberechtigung fehlt.")
    return LocationServices.getFusedLocationProviderClient(context)
        .getCurrentLocation(if (fine) Priority.PRIORITY_HIGH_ACCURACY else Priority.PRIORITY_BALANCED_POWER_ACCURACY, null)
        .await() ?: throw IllegalStateException("Der aktuelle Standort konnte nicht ermittelt werden.")
}
