package at.eeg.trabocherstrasse.member.ui

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import java.io.File

@Composable fun PdfPreviewDialog(filename: String, bytes: ByteArray, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val safeName = filename.replace(Regex("[^A-Za-z0-9ÄÖÜäöüß._-]"), "-").let { if (it.endsWith(".pdf", true)) it else "$it.pdf" }
    val sharedFile = remember(bytes) {
        File(context.cacheDir, "shared").apply { mkdirs() }.resolve(safeName).apply { writeBytes(bytes) }
    }
    val preview = remember(bytes) { renderFirstPage(sharedFile) }
    val save = rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("application/pdf")) { uri ->
        if (uri != null) context.contentResolver.openOutputStream(uri)?.use { it.write(bytes) }
    }
    DisposableEffect(sharedFile) { onDispose { sharedFile.delete() } }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(filename) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                preview?.let { Image(it.asImageBitmap(), "PDF-Vorschau", Modifier.fillMaxWidth().heightIn(max = 520.dp), contentScale = ContentScale.FillWidth) }
                if (preview == null) Text("Die PDF-Vorschau konnte nicht gerendert werden.")
            }
        },
        confirmButton = {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedButton(onClick = { save.launch(safeName) }) { Icon(Icons.Default.Download, null); Text(" Speichern") }
                Button(onClick = {
                    val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", sharedFile)
                    val share = Intent(Intent.ACTION_SEND).apply {
                        type = "application/pdf"; putExtra(Intent.EXTRA_STREAM, uri); addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                    context.startActivity(Intent.createChooser(share, "PDF teilen, drucken oder senden"))
                }) { Icon(Icons.Default.Share, null); Text(" Teilen") }
            }
        },
        dismissButton = { OutlinedButton(onClick = onDismiss) { Text("Schließen") } },
    )
}

private fun renderFirstPage(file: File): Bitmap? = runCatching {
    ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY).use { descriptor ->
        PdfRenderer(descriptor).use { renderer ->
            renderer.openPage(0).use { page ->
                val width = 1080
                val height = (width.toFloat() / page.width * page.height).toInt()
                Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888).also { bitmap ->
                    bitmap.eraseColor(android.graphics.Color.WHITE)
                    page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                }
            }
        }
    }
}.getOrNull()
