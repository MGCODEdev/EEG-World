"""Fachlogik für periodische EEG-Abrechnungen."""


def calculate_billing(db, period_from, period_to, price_cons, price_gen, carryover_provider):
    """Berechnet Bezug und Einspeisung aller aktiven Mitglieder."""
    ts_from = period_from + 'T00:00:00' if 'T' not in period_from else period_from
    ts_to = period_to + 'T23:45:00' if 'T' not in period_to else period_to
    items = []
    total_income = total_expense = total_kwh = 0
    members = db.execute(
        'SELECT id, name, bezug_zp, einspeiser_zp FROM members WHERE active=1'
    ).fetchall()

    for member in members:
        cons_kwh = gen_kwh = 0
        if member['bezug_zp']:
            row = db.execute("""
                SELECT ROUND(SUM(m.value_kwh), 3) as kwh
                FROM measurements m
                JOIN meter_codes mc ON mc.id = m.meter_code_id
                WHERE mc.code = '1-1:2.9.0 G.03'
                  AND m.metering_point_id = ?
                  AND m.timestamp_start >= ? AND m.timestamp_start <= ?
            """, (member['bezug_zp'], ts_from, ts_to)).fetchone()
            cons_kwh = row['kwh'] or 0
        if member['einspeiser_zp']:
            row = db.execute("""
                SELECT
                    ROUND(SUM(CASE WHEN mc.code='1-1:2.9.0 G.01T' THEN m.value_kwh ELSE 0 END), 3) as g01t,
                    ROUND(SUM(CASE WHEN mc.code='1-1:2.9.0 P.01T' THEN m.value_kwh ELSE 0 END), 3) as p01t
                FROM measurements m
                JOIN meter_codes mc ON mc.id = m.meter_code_id
                WHERE mc.code IN ('1-1:2.9.0 G.01T', '1-1:2.9.0 P.01T')
                  AND m.metering_point_id = ?
                  AND m.timestamp_start >= ? AND m.timestamp_start <= ?
            """, (member['einspeiser_zp'], ts_from, ts_to)).fetchone()
            gen_kwh = max(0, (row['g01t'] or 0) - (row['p01t'] or 0))

        if cons_kwh <= 0 and gen_kwh <= 0:
            continue
        if cons_kwh > 0:
            amount = round(cons_kwh * price_cons / 100.0, 2)
            items.append({'member_id': member['id'], 'type': 'consumption',
                          'kwh': round(cons_kwh, 3), 'price': price_cons, 'amount': amount})
            total_income += amount
            total_kwh += cons_kwh
        if gen_kwh > 0:
            amount = round(gen_kwh * price_gen / 100.0, 2)
            items.append({'member_id': member['id'], 'type': 'generation',
                          'kwh': round(gen_kwh, 3), 'price': price_gen, 'amount': amount})
            total_expense += amount

    return {
        'items': items,
        'carryovers': carryover_provider(db, period_from),
        'total_kwh': total_kwh,
        'total_income': round(total_income, 2),
        'total_expense': round(total_expense, 2),
        'total_margin': round(total_income - total_expense, 2),
    }
