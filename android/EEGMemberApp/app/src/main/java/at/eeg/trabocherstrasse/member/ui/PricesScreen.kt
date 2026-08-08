package at.eeg.trabocherstrasse.member.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import at.eeg.trabocherstrasse.member.core.EnergyPrice
import at.eeg.trabocherstrasse.member.core.EnergyPricesResponse
import at.eeg.trabocherstrasse.member.core.SessionManager
import at.eeg.trabocherstrasse.member.core.dateText
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun PricesScreen(session: SessionManager, contentPadding: PaddingValues) {
    var prices by remember { mutableStateOf<EnergyPricesResponse?>(null) }
    var range by remember { mutableIntStateOf(12) }
    var error by remember { mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        runCatching { prices = session.get<EnergyPricesResponse>("prices") }.onFailure { error = it.message }
    }
    Column(
        Modifier.fillMaxSize().padding(contentPadding).verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Energiepreise", style = MaterialTheme.typography.headlineSmall)
        prices?.let { response ->
            response.current?.let { current ->
                Card(shape = RoundedCornerShape(18.dp)) {
                    Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text("Aktueller EEG-Tarif", style = MaterialTheme.typography.titleMedium)
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            PriceTile("Bezug aus der EEG", current.eegConsumptionCt, Modifier.weight(1f))
                            PriceTile("Einspeisung an die EEG", current.eegGenerationCt, Modifier.weight(1f))
                        }
                        Text("Gültig ${dateText(current.validFrom)} – ${dateText(current.validTo)}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        current.description?.takeIf { it.isNotBlank() }?.let { Text(it, style = MaterialTheme.typography.bodyMedium) }
                    }
                }
            }
            Card {
                Column(Modifier.padding(11.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Preisentwicklung", style = MaterialTheme.typography.titleMedium)
                    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                        listOf(3 to "3 M", 6 to "6 M", 12 to "12 M", 0 to "Max").forEachIndexed { index, item ->
                            SegmentedButton(selected = range == item.first, onClick = { range = item.first }, shape = SegmentedButtonDefaults.itemShape(index, 4)) { Text(item.second) }
                        }
                    }
                    D3Chart(pricePayload(response.history, range), Modifier.fillMaxWidth().height(285.dp))
                }
            }
            Text("Frühere EEG-Tarife", style = MaterialTheme.typography.titleMedium)
            response.history.sortedByDescending { it.validFrom }.forEach { item ->
                Card {
                    Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("${dateText(item.validFrom)} – ${dateText(item.validTo)}", fontWeight = FontWeight.SemiBold)
                            item.description?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                        }
                        Column(horizontalAlignment = Alignment.End) {
                            Text("${formatCt(item.eegConsumptionCt)} Bezug")
                            Text("${formatCt(item.eegGenerationCt)} Einspeisung", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }
        } ?: CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally).padding(36.dp))
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    }
}

@Composable private fun PriceTile(title: String, cents: Double, modifier: Modifier) {
    Column(modifier) {
        Text(title, style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(formatCt(cents), style = MaterialTheme.typography.headlineSmall, color = MaterialTheme.colorScheme.primary)
    }
}

private fun formatCt(value: Double) = String.format(java.util.Locale.forLanguageTag("de-AT"), "%.2f ct/kWh", value)

private fun pricePayload(all: List<EnergyPrice>, months: Int): ChartPayload {
    val cutoff = if (months == 0) LocalDate.MIN else LocalDate.now().minusMonths(months.toLong())
    val filtered = all.filter { runCatching { LocalDate.parse(it.validTo) >= cutoff }.getOrDefault(true) }.sortedBy { it.validFrom }
    return ChartPayload(
        "lines", "ct/kWh",
        filtered.map { ChartCategory(it.validFrom.take(7), "${dateText(it.validFrom)} – ${dateText(it.validTo)}") },
        listOf(
            ChartSeries("EEG-Bezug", "#2E8F89", "Preis", filtered.map { it.eegConsumptionCt }),
            ChartSeries("EEG-Einspeisung", "#E2A416", "Preis", filtered.map { it.eegGenerationCt }),
        ),
    )
}
