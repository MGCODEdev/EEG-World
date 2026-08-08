package at.eeg.trabocherstrasse.member.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
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
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.AssistChip
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import at.eeg.trabocherstrasse.member.core.DashboardResponse
import at.eeg.trabocherstrasse.member.core.DataStatusResponse
import at.eeg.trabocherstrasse.member.core.EnergyPricesResponse
import at.eeg.trabocherstrasse.member.core.HistoricalDataStatus
import at.eeg.trabocherstrasse.member.core.HistoricalEnergySummary
import at.eeg.trabocherstrasse.member.core.Period
import at.eeg.trabocherstrasse.member.core.SessionManager
import java.time.LocalDate

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun OverviewScreen(session: SessionManager, memberName: String, contentPadding: PaddingValues) {
    var dashboard by remember { mutableStateOf<DashboardResponse?>(null) }
    var status by remember { mutableStateOf<HistoricalDataStatus?>(null) }
    var summary by remember { mutableStateOf<HistoricalEnergySummary?>(null) }
    var prices by remember { mutableStateOf<EnergyPricesResponse?>(null) }
    var period by remember { mutableStateOf(Period.MONTH) }
    var date by remember { mutableStateOf(LocalDate.now()) }
    var latest by remember { mutableStateOf(LocalDate.now()) }
    var unit by remember { mutableStateOf("kWh") }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var reload by remember { mutableStateOf(0) }
    var showingCache by remember { mutableStateOf(false) }

    LaunchedEffect(reload) {
        if (dashboard == null) {
            dashboard = session.cachedDashboard()
            showingCache = dashboard != null
        }
        loading = dashboard == null
        runCatching {
            dashboard = session.get("dashboard")
            dashboard?.let(session::cacheDashboard)
            showingCache = false
            val dataStatus: DataStatusResponse = session.get("data-status")
            status = dataStatus.dataStatus
            prices = session.get("prices")
            dataStatus.dataStatus.availableUntil?.take(10)?.let {
                latest = LocalDate.parse(it).minusDays(1)
                date = latest
            }
        }.onFailure { error = it.message }
        loading = false
    }
    LaunchedEffect(period, date, reload, latest) {
        val (start, rawEnd) = period.range(date)
        val end = rawEnd.coerceAtMost(latest)
        if (start <= end) runCatching {
            summary = session.get("energy/summary?from=$start&to=$end")
            error = null
        }.onFailure { error = it.message }
    }

    Column(
        Modifier.fillMaxSize().padding(contentPadding).verticalScroll(rememberScrollState())
            .padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Übersicht", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.weight(1f))
            IconButton(onClick = { reload++ }) { Icon(Icons.Default.Refresh, "Aktualisieren") }
        }
        Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface)) {
            Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Default.Bolt, null, tint = MaterialTheme.colorScheme.primary,
                    modifier = Modifier.size(46.dp).clip(CircleShape).background(MaterialTheme.colorScheme.primary.copy(alpha = .1f)).padding(10.dp),
                )
                Column(Modifier.padding(start = 13.dp).weight(1f)) {
                    Text("EEG Trabocherstraße", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Hallo, $memberName", style = MaterialTheme.typography.headlineSmall, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (dashboard?.member?.active == false) Text("Mitgliedschaft inaktiv", color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.labelMedium)
                }
            }
        }
        Card {
            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SingleChoiceSegmentedButtonRow(Modifier.weight(1f)) {
                        listOf(Period.DAY, Period.MONTH, Period.YEAR).forEachIndexed { index, item ->
                            SegmentedButton(
                                selected = period == item, onClick = { period = item },
                                shape = SegmentedButtonDefaults.itemShape(index, 3),
                            ) { Text(item.label) }
                        }
                    }
                    SingleChoiceSegmentedButtonRow {
                        listOf("kWh", "€").forEachIndexed { index, item ->
                            SegmentedButton(selected = unit == item, onClick = { unit = item }, shape = SegmentedButtonDefaults.itemShape(index, 2)) { Text(item) }
                        }
                    }
                }
                PeriodNavigation(period, date, latest) { date = it }
            }
        }
        if (showingCache) Text("Zuletzt sicher gespeicherte Daten", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        if (loading) CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally).padding(32.dp))
        summary?.let { current ->
            Card(shape = RoundedCornerShape(18.dp)) {
                D3Chart(overviewPayload(current, prices, unit), Modifier.fillMaxWidth().height(274.dp))
            }
            if (unit == "€") Text("Kosten und Erlöse sind Tarifschätzungen.", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        status?.let {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Icon(Icons.Default.Schedule, null, modifier = Modifier.size(15.dp))
                Text(dataStatusText(it), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        error?.let {
            AssistChip(onClick = { reload++ }, label = { Text(it) }, leadingIcon = { Icon(Icons.Default.CloudOff, null) })
        }
        Spacer(Modifier.height(4.dp))
    }
}

private fun overviewPayload(summary: HistoricalEnergySummary, prices: EnergyPricesResponse?, unit: String): ChartPayload {
    val consumption = summary.balance.consumption
    val generation = summary.balance.generation
    fun amount(kwh: Double?, cents: Double?): Double? = if (unit == "kWh") kwh else if (kwh != null && cents != null) kwh * cents / 100 else null
    val categories = mutableListOf<ChartCategory>()
    val eeg = mutableListOf<Double?>(); val grid = mutableListOf<Double?>()
    val eegColors = mutableListOf<String?>(); val gridColors = mutableListOf<String?>()
    if (consumption.totalKwh > 0 || generation.totalKwh <= 0) {
        categories += ChartCategory("Mein Verbrauch", "Aufteilung des gemessenen Verbrauchs")
        eeg += amount(consumption.eegKwh, prices?.current?.eegConsumptionCt)
        grid += amount(consumption.gridKwh, prices?.reference?.gridConsumptionCt)
        eegColors += "#2EA65C"; gridColors += "#F06B29"
    }
    if (generation.totalKwh > 0) {
        categories += ChartCategory("Meine Einspeisung", "Aufteilung der berücksichtigten Erzeugung")
        eeg += amount(generation.eegKwh, prices?.current?.eegGenerationCt)
        grid += amount(generation.gridKwh, prices?.reference?.publicFeedCt)
        eegColors += "#E2A416"; gridColors += "#7759C6"
    }
    return ChartPayload(
        "donuts", unit, categories,
        listOf(
            ChartSeries("EEG", "#2EA65C", "Bilanz", eeg, eegColors),
            ChartSeries("Öffentliches Netz", "#F06B29", "Bilanz", grid, gridColors),
        ),
    )
}
