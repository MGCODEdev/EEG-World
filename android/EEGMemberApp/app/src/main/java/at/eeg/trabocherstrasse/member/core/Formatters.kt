package at.eeg.trabocherstrasse.member.core

import java.text.NumberFormat
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.time.format.FormatStyle
import java.util.Locale

private val locale = Locale.forLanguageTag("de-AT")

fun Double.euro(): String = NumberFormat.getCurrencyInstance(locale).format(this)
fun Double.kwh(digits: Int = 1): String = NumberFormat.getNumberInstance(locale).apply {
    minimumFractionDigits = digits
    maximumFractionDigits = digits
}.format(this) + " kWh"

fun dateText(value: String): String = runCatching {
    LocalDate.parse(value.take(10)).format(DateTimeFormatter.ofLocalizedDate(FormatStyle.MEDIUM).withLocale(locale))
}.getOrDefault(value)

enum class Period(val label: String) {
    DAY("Tag"), WEEK("Woche"), MONTH("Monat"), YEAR("Jahr");

    fun range(anchor: LocalDate): Pair<LocalDate, LocalDate> = when (this) {
        DAY -> anchor to anchor
        WEEK -> anchor.minusDays((anchor.dayOfWeek.value - 1).toLong()) to anchor.plusDays((7 - anchor.dayOfWeek.value).toLong())
        MONTH -> anchor.withDayOfMonth(1) to anchor.withDayOfMonth(anchor.lengthOfMonth())
        YEAR -> anchor.withDayOfYear(1) to anchor.withDayOfYear(anchor.lengthOfYear())
    }

    fun shift(anchor: LocalDate, amount: Long): LocalDate = when (this) {
        DAY -> anchor.plusDays(amount)
        WEEK -> anchor.plusWeeks(amount)
        MONTH -> anchor.plusMonths(amount)
        YEAR -> anchor.plusYears(amount)
    }

    fun title(anchor: LocalDate): String = when (this) {
        DAY -> anchor.format(DateTimeFormatter.ofPattern("dd. MMMM yyyy", locale))
        WEEK -> {
            val (from, to) = range(anchor)
            "${from.format(DateTimeFormatter.ofPattern("dd.MM.", locale))} – ${to.format(DateTimeFormatter.ofPattern("dd.MM.yyyy", locale))}"
        }
        MONTH -> YearMonth.from(anchor).format(DateTimeFormatter.ofPattern("MMMM yyyy", locale))
        YEAR -> anchor.year.toString()
    }
}
