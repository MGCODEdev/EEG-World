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
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import at.eeg.trabocherstrasse.member.core.DataStatusResponse
import at.eeg.trabocherstrasse.member.core.EnergyBalanceSplit
import at.eeg.trabocherstrasse.member.core.EnergyPricesResponse
import at.eeg.trabocherstrasse.member.core.HistoricalDataStatus
import at.eeg.trabocherstrasse.member.core.HistoricalEnergyPoint
import at.eeg.trabocherstrasse.member.core.HistoricalEnergySummary
import at.eeg.trabocherstrasse.member.core.HistoricalSeriesResponse
import at.eeg.trabocherstrasse.member.core.MeteringPoint
import at.eeg.trabocherstrasse.member.core.MeteringPointsResponse
import at.eeg.trabocherstrasse.member.core.Period
import at.eeg.trabocherstrasse.member.core.SessionManager
import at.eeg.trabocherstrasse.member.core.euro
import at.eeg.trabocherstrasse.member.core.kwh
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

private enum class BalanceMode(val label: String) { CONSUMPTION("Verbrauch"), GENERATION("Einspeisung") }

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun EnergyScreen(session: SessionManager, contentPadding: PaddingValues) {
    var status by remember { mutableStateOf<HistoricalDataStatus?>(null) }
    var summary by remember { mutableStateOf<HistoricalEnergySummary?>(null) }
    var series by remember { mutableStateOf<List<HistoricalEnergyPoint>>(emptyList()) }
    var prices by remember { mutableStateOf<EnergyPricesResponse?>(null) }
    var period by remember { mutableStateOf(Period.DAY) }
    var date by remember { mutableStateOf(LocalDate.now()) }
    var latest by remember { mutableStateOf(LocalDate.now()) }
    var mode by remember { mutableStateOf(BalanceMode.CONSUMPTION) }
    var unit by remember { mutableStateOf("kWh") }
    var error by remember { mutableStateOf<String?>(null) }
    var points by remember { mutableStateOf<List<MeteringPoint>>(emptyList()) }
    var selectedPoint by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        runCatching {
            val response: DataStatusResponse = session.get("data-status")
            status = response.dataStatus
            prices = session.get("prices")
            points = session.get<MeteringPointsResponse>("metering-points").meteringPoints
            response.dataStatus.availableUntil?.take(10)?.let {
                latest = LocalDate.parse(it).minusDays(1); date = latest
            }
        }.onFailure { error = it.message }
    }
    LaunchedEffect(period, date, latest, selectedPoint) {
        val (from, rawTo) = period.range(date)
        val to = rawTo.coerceAtMost(latest)
        if (from <= to) runCatching {
            val resolution = when (period) { Period.DAY -> "hour"; Period.WEEK, Period.MONTH -> "day"; Period.YEAR -> "month" }
            val pointQuery = if (selectedPoint.isBlank()) "" else "&metering_point=${URLEncoder.encode(selectedPoint, StandardCharsets.UTF_8)}"
            summary = session.get("energy/summary?from=$from&to=$to$pointQuery")
            val response: HistoricalSeriesResponse = session.get("energy/series?from=$from&to=$to&resolution=$resolution$pointQuery")
            series = response.series
            error = null
        }.onFailure { error = it.message; summary = null; series = emptyList() }
    }

    Column(
        Modifier.fillMaxSize().padding(contentPadding).verticalScroll(rememberScrollState()).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Text("Energie", style = MaterialTheme.typography.headlineSmall)
        status?.let { Text(dataStatusText(it), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        Card {
            Column(Modifier.padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    Period.entries.forEachIndexed { index, item ->
                        SegmentedButton(selected = period == item, onClick = { period = item }, shape = SegmentedButtonDefaults.itemShape(index, Period.entries.size)) { Text(item.label) }
                    }
                }
                PeriodNavigation(period, date, latest) { date = it }
            }
        }
        if (points.size > 1) Row(
            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(7.dp),
        ) {
            FilterChip(selected = selectedPoint.isEmpty(), onClick = { selectedPoint = "" }, label = { Text("Alle Zählpunkte") })
            points.forEach { point ->
                FilterChip(
                    selected = selectedPoint == point.id,
                    onClick = {
                        selectedPoint = point.id
                        mode = if (point.direction == "GENERATION") BalanceMode.GENERATION else BalanceMode.CONSUMPTION
                    },
                    label = { Text(point.maskedId) },
                )
            }
        }
        summary?.let { data ->
            Card(shape = RoundedCornerShape(18.dp)) {
                Column(Modifier.padding(11.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Energiebilanz", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                        Text(period.title(date), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        SingleChoiceSegmentedButtonRow(Modifier.weight(1f)) {
                            BalanceMode.entries.forEachIndexed { index, item ->
                                SegmentedButton(selected = mode == item, onClick = { mode = item }, shape = SegmentedButtonDefaults.itemShape(index, 2)) { Text(item.label) }
                            }
                        }
                        SingleChoiceSegmentedButtonRow {
                            listOf("kWh", "€").forEachIndexed { index, item ->
                                SegmentedButton(selected = unit == item, onClick = { unit = item }, shape = SegmentedButtonDefaults.itemShape(index, 2)) { Text(item) }
                            }
                        }
                    }
                    D3Chart(balancePayload(data, prices, mode, unit), Modifier.fillMaxWidth().height(270.dp))
                    BalanceValues(data, prices, mode)
                }
            }
            if (series.isNotEmpty()) Card {
                Column(Modifier.padding(11.dp)) {
                    Text(if (period == Period.DAY) "Tagesverlauf" else "Verlauf", style = MaterialTheme.typography.titleMedium)
                    D3Chart(seriesPayload(series, prices, mode, unit, period), Modifier.fillMaxWidth().height(310.dp))
                }
            }
        } ?: CircularProgressIndicator(Modifier.align(Alignment.CenterHorizontally).padding(32.dp))
        error?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
    }
}

@Composable private fun BalanceValues(summary: HistoricalEnergySummary, prices: EnergyPricesResponse?, mode: BalanceMode) {
    val balance = if (mode == BalanceMode.CONSUMPTION) summary.balance.consumption else summary.balance.generation
    val eegRate = if (mode == BalanceMode.CONSUMPTION) prices?.current?.eegConsumptionCt else prices?.current?.eegGenerationCt
    val gridRate = if (mode == BalanceMode.CONSUMPTION) prices?.reference?.gridConsumptionCt else prices?.reference?.publicFeedCt
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        EnergyValueTile(
            if (mode == BalanceMode.CONSUMPTION) "Aus der EEG" else "An die EEG",
            balance.eegKwh, balance.eegKwh?.let { kwh -> eegRate?.let { kwh * it / 100 } },
            if (mode == BalanceMode.CONSUMPTION) EEGCommunity else EEGGenerationCommunity,
            Modifier.weight(1f),
        )
        EnergyValueTile(
            if (mode == BalanceMode.CONSUMPTION) "Aus dem Netz" else "Ins Netz",
            balance.gridKwh, balance.gridKwh?.let { kwh -> gridRate?.let { kwh * it / 100 } },
            if (mode == BalanceMode.CONSUMPTION) EEGConsumptionGrid else EEGGenerationGrid,
            Modifier.weight(1f),
        )
    }
}

@Composable private fun EnergyValueTile(title: String, energy: Double?, money: Double?, color: Color, modifier: Modifier) {
    Column(modifier = modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(title, style = MaterialTheme.typography.labelMedium, color = color, fontWeight = FontWeight.SemiBold)
        Text(energy?.kwh() ?: "–", style = MaterialTheme.typography.titleMedium)
        Text(money?.euro() ?: "–", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

private fun estimated(balance: EnergyBalanceSplit, prices: EnergyPricesResponse?, mode: BalanceMode): Pair<Double?, Double?> {
    val eegRate = if (mode == BalanceMode.CONSUMPTION) prices?.current?.eegConsumptionCt else prices?.current?.eegGenerationCt
    val gridRate = if (mode == BalanceMode.CONSUMPTION) prices?.reference?.gridConsumptionCt else prices?.reference?.publicFeedCt
    return balance.eegKwh?.let { kwh -> eegRate?.let { kwh * it / 100 } } to balance.gridKwh?.let { kwh -> gridRate?.let { kwh * it / 100 } }
}

private fun values(balance: EnergyBalanceSplit, prices: EnergyPricesResponse?, mode: BalanceMode, unit: String): Pair<Double?, Double?> =
    if (unit == "kWh") balance.eegKwh to balance.gridKwh else estimated(balance, prices, mode)

private fun balancePayload(summary: HistoricalEnergySummary, prices: EnergyPricesResponse?, mode: BalanceMode, unit: String): ChartPayload {
    val balance = if (mode == BalanceMode.CONSUMPTION) summary.balance.consumption else summary.balance.generation
    val (eeg, grid) = values(balance, prices, mode, unit)
    return ChartPayload(
        "donuts", unit,
        listOf(ChartCategory(if (mode == BalanceMode.CONSUMPTION) "Mein Verbrauch" else "Meine Einspeisung", "Aufteilung der Energiebilanz")),
        listOf(
            ChartSeries(if (mode == BalanceMode.CONSUMPTION) "Aus der EEG" else "An die EEG", if (mode == BalanceMode.CONSUMPTION) "#2EA65C" else "#E2A416", "Bilanz", listOf(eeg)),
            ChartSeries(if (mode == BalanceMode.CONSUMPTION) "Aus dem Netz" else "Ins Netz", if (mode == BalanceMode.CONSUMPTION) "#F06B29" else "#7759C6", "Bilanz", listOf(grid)),
        ),
    )
}

private fun seriesPayload(points: List<HistoricalEnergyPoint>, prices: EnergyPricesResponse?, mode: BalanceMode, unit: String, period: Period): ChartPayload {
    val formatter = when (period) {
        Period.DAY -> DateTimeFormatter.ofPattern("HH:mm")
        Period.YEAR -> DateTimeFormatter.ofPattern("MMM", Locale.forLanguageTag("de-AT"))
        else -> DateTimeFormatter.ofPattern("dd.MM.")
    }
    val categories = points.map { point ->
        val raw = point.bucket
        val label = runCatching {
            when {
                raw.length == 7 -> java.time.YearMonth.parse(raw).atDay(1).format(formatter)
                raw.length == 10 -> LocalDate.parse(raw).format(formatter)
                else -> java.time.LocalDateTime.parse(raw.take(19)).format(formatter)
            }
        }.getOrDefault(raw)
        ChartCategory(label, raw, point.containsEstimatedValues)
    }
    val balances = points.map { if (mode == BalanceMode.CONSUMPTION) it.balance.consumption else it.balance.generation }
    return ChartPayload(
        "bars", unit, categories,
        listOf(
            ChartSeries(if (mode == BalanceMode.CONSUMPTION) "EEG-Bezug" else "An die EEG", if (mode == BalanceMode.CONSUMPTION) "#2EA65C" else "#E2A416", "Bilanz", balances.map { values(it, prices, mode, unit).first }),
            ChartSeries(if (mode == BalanceMode.CONSUMPTION) "Restnetzbezug" else "Ins öffentliche Netz", if (mode == BalanceMode.CONSUMPTION) "#F06B29" else "#7759C6", "Bilanz", balances.map { values(it, prices, mode, unit).second }),
        ),
    )
}
