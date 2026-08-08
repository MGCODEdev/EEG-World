package at.eeg.trabocherstrasse.member.ui

import android.app.DatePickerDialog
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CalendarMonth
import androidx.compose.material.icons.filled.ChevronLeft
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import at.eeg.trabocherstrasse.member.core.Period
import java.time.LocalDate

@Composable fun PeriodNavigation(
    period: Period,
    date: LocalDate,
    maximumDate: LocalDate,
    onDate: (LocalDate) -> Unit,
) {
    val context = LocalContext.current
    val next = period.shift(date, 1)
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = { onDate(period.shift(date, -1)) }) { Icon(Icons.Default.ChevronLeft, "Vorheriger Zeitraum") }
        Text(
            period.title(date), style = MaterialTheme.typography.labelLarge,
            textAlign = TextAlign.Center, maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.weight(1f).padding(horizontal = 4.dp),
        )
        IconButton(onClick = { onDate(next) }, enabled = period.range(next).first <= maximumDate) { Icon(Icons.Default.ChevronRight, "Nächster Zeitraum") }
        IconButton(onClick = {
            DatePickerDialog(
                context,
                { _, year, month, day -> onDate(LocalDate.of(year, month + 1, day).coerceAtMost(maximumDate)) },
                date.year, date.monthValue - 1, date.dayOfMonth,
            ).apply { datePicker.maxDate = maximumDate.toEpochDay() * 86_400_000L }.show()
        }) { Icon(Icons.Default.CalendarMonth, "Datum auswählen", tint = MaterialTheme.colorScheme.primary) }
    }
}

fun dataStatusText(status: at.eeg.trabocherstrasse.member.core.HistoricalDataStatus): String {
    val until = status.availableUntil?.take(10)?.let { runCatching { LocalDate.parse(it).minusDays(1) }.getOrNull() }
    return if (until == null) "Noch kein Energiedatenstand verfügbar" else "Energiedaten bis zum ${at.eeg.trabocherstrasse.member.core.dateText(until.toString())}"
}
