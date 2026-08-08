package at.eeg.trabocherstrasse.member

import at.eeg.trabocherstrasse.member.core.Period
import at.eeg.trabocherstrasse.member.core.dateText
import at.eeg.trabocherstrasse.member.core.euro
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDate

class FormattersTest {
    @Test fun monthRangeUsesFullCalendarMonth() {
        val (from, to) = Period.MONTH.range(LocalDate.of(2026, 2, 12))
        assertEquals(LocalDate.of(2026, 2, 1), from)
        assertEquals(LocalDate.of(2026, 2, 28), to)
    }

    @Test fun weekStartsOnMondayInAustrianUi() {
        val (from, to) = Period.WEEK.range(LocalDate.of(2026, 8, 8))
        assertEquals(LocalDate.of(2026, 8, 3), from)
        assertEquals(LocalDate.of(2026, 8, 9), to)
    }

    @Test fun moneyAlwaysContainsTwoDecimalsAndEuro() {
        val formatted = 12.5.euro()
        assertTrue(formatted.contains("12,50"))
        assertTrue(formatted.contains("€"))
    }

    @Test fun apiDateIsShownInGermanFormat() {
        assertEquals("08.08.2026", dateText("2026-08-08"))
    }
}
