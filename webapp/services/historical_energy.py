"""Serverseitige, mitgliedsbezogene Auswertung historischer Energiedaten."""

from datetime import date, timedelta

from services.energy_domain import (
    EnergyDomainError,
    community_feed_kwh,
    residual_grid_consumption_kwh,
    self_sufficiency_percent,
)


SERIES_CODES = {
    "consumption": "1-1:1.9.0 G.01",
    "self_coverage": "1-1:2.9.0 G.03",
    "generation": "1-1:2.9.0 G.01",
    "participation_generation": "1-1:2.9.0 G.01T",
    "public_feed": "1-1:2.9.0 P.01T",
}


def mask_metering_point(value: str) -> str:
    value = str(value or "")
    if len(value) <= 8:
        return value
    return f"{value[:4]}…{value[-4:]}"


def member_metering_points(db, member) -> list[dict]:
    rows = db.execute("""
        SELECT metering_point_id, direction, role, valid_from, valid_to
        FROM member_metering_points
        WHERE member_id=?
        ORDER BY direction, metering_point_id
    """, (member["id"],)).fetchall()
    result = [dict(row) for row in rows]
    if not result:
        if member["bezug_zp"]:
            result.append({
                "metering_point_id": member["bezug_zp"],
                "direction": "CONSUMPTION",
                "role": "consumer",
                "valid_from": member["bezug_ab"],
                "valid_to": None,
            })
        if member["einspeiser_zp"]:
            result.append({
                "metering_point_id": member["einspeiser_zp"],
                "direction": "GENERATION",
                "role": "producer",
                "valid_from": member["einspeiser_ab"],
                "valid_to": None,
            })
    for item in result:
        item["masked_id"] = mask_metering_point(item["metering_point_id"])
    return result


def select_authorized_points(db, member, selected: str | None = None) -> list[dict]:
    points = member_metering_points(db, member)
    if selected:
        points = [point for point in points if point["metering_point_id"] == selected]
        if not points:
            raise PermissionError("Der Zählpunkt ist diesem Mitglied nicht zugeordnet.")
    return points


def _bounds(period_from: date, period_to: date) -> tuple[str, str]:
    return (
        f"{period_from.isoformat()}T00:00:00",
        f"{(period_to + timedelta(days=1)).isoformat()}T00:00:00",
    )


def _totals_from_rows(rows) -> dict[str, float]:
    result = {key: 0.0 for key in SERIES_CODES}
    reverse = {value: key for key, value in SERIES_CODES.items()}
    # G.01 exists once for each direction. The point direction disambiguates it.
    for row in rows:
        code = row["code"]
        direction = row["point_direction"]
        if code == SERIES_CODES["consumption"] and direction == "CONSUMPTION":
            result["consumption"] += float(row["kwh"] or 0)
        elif code == SERIES_CODES["generation"] and direction == "GENERATION":
            result["generation"] += float(row["kwh"] or 0)
        elif code in reverse:
            result[reverse[code]] += float(row["kwh"] or 0)
    return result


def _derived(totals: dict[str, float]) -> tuple[dict, list[str]]:
    errors = []
    try:
        residual_grid = residual_grid_consumption_kwh(
            totals["consumption"], totals["self_coverage"]
        )
        self_sufficiency = self_sufficiency_percent(
            totals["self_coverage"], totals["consumption"]
        )
    except EnergyDomainError as error:
        residual_grid = None
        self_sufficiency = None
        errors.append(str(error))
    try:
        community_feed = community_feed_kwh(
            totals["participation_generation"], totals["public_feed"]
        )
    except EnergyDomainError as error:
        community_feed = None
        errors.append(str(error))
    return {
        "residual_grid_kwh": residual_grid,
        "community_feed_kwh": community_feed,
        "self_sufficiency_percent": self_sufficiency,
    }, errors


def _share_percent(part: float | None, total: float) -> float | None:
    if part is None or total <= 0:
        return None
    return round(part / total * 100.0, 6)


def _balance_payload(totals: dict[str, float], derived: dict) -> dict:
    """Expose the two EDA-supported balances without inventing household PV flows."""
    consumption_total = totals["consumption"]
    generation_total = totals["participation_generation"]
    return {
        "consumption": {
            "total_kwh": round(consumption_total, 6),
            "eeg_kwh": round(totals["self_coverage"], 6),
            "grid_kwh": (
                round(derived["residual_grid_kwh"], 6)
                if derived["residual_grid_kwh"] is not None else None
            ),
            "eeg_percent": derived["self_sufficiency_percent"],
        },
        "generation": {
            "total_kwh": round(generation_total, 6),
            "eeg_kwh": (
                round(derived["community_feed_kwh"], 6)
                if derived["community_feed_kwh"] is not None else None
            ),
            "grid_kwh": round(totals["public_feed"], 6),
            "eeg_percent": _share_percent(
                derived["community_feed_kwh"], generation_total
            ),
        },
    }


def historical_summary(db, member, period_from: date, period_to: date,
                       selected_point: str | None = None) -> dict:
    points = select_authorized_points(db, member, selected_point)
    if not points:
        totals = {key: 0.0 for key in SERIES_CODES}
        derived, _ = _derived(totals)
        return {
            "totals": {f"{key}_kwh": value for key, value in totals.items()},
            "derived": derived,
            "balance": _balance_payload(totals, derived),
            "quality": {},
            "data_quality_errors": ["Keine Zählpunkte zugeordnet."],
        }
    ts_from, ts_to = _bounds(period_from, period_to)
    point_directions = {point["metering_point_id"]: point["direction"] for point in points}
    placeholders = ",".join("?" for _ in points)
    rows = db.execute(f"""
        SELECT m.metering_point_id, mc.code, SUM(m.value_kwh) AS kwh
        FROM measurements m
        JOIN meter_codes mc ON mc.id=m.meter_code_id
        WHERE m.metering_point_id IN ({placeholders})
          AND m.timestamp_start>=? AND m.timestamp_start<?
          AND mc.code IN (?, ?, ?, ?, ?)
        GROUP BY m.metering_point_id, mc.code
    """, (
        *point_directions, ts_from, ts_to,
        SERIES_CODES["consumption"], SERIES_CODES["self_coverage"],
        SERIES_CODES["generation"], SERIES_CODES["participation_generation"],
        SERIES_CODES["public_feed"],
    )).fetchall()
    directional_rows = [
        {**dict(row), "point_direction": point_directions[row["metering_point_id"]]}
        for row in rows
    ]
    totals = _totals_from_rows(directional_rows)
    derived, errors = _derived(totals)
    quality_rows = db.execute(f"""
        SELECT COALESCE(NULLIF(TRIM(quality), ''), 'UNKNOWN') quality, COUNT(*) count
        FROM measurements
        WHERE metering_point_id IN ({placeholders})
          AND timestamp_start>=? AND timestamp_start<?
        GROUP BY quality ORDER BY count DESC
    """, (*point_directions, ts_from, ts_to)).fetchall()
    return {
        "totals": {f"{key}_kwh": round(value, 6) for key, value in totals.items()},
        "derived": derived,
        "balance": _balance_payload(totals, derived),
        "quality": {row["quality"]: row["count"] for row in quality_rows},
        "data_quality_errors": errors,
    }


def historical_series(db, member, period_from: date, period_to: date,
                      resolution: str, selected_point: str | None = None) -> list[dict]:
    bucket_expressions = {
        "quarter_hour": "m.timestamp_start",
        "hour": "substr(m.timestamp_start, 1, 13) || ':00:00'",
        "day": "substr(m.timestamp_start, 1, 10)",
        "month": "substr(m.timestamp_start, 1, 7)",
    }
    if resolution not in bucket_expressions:
        raise ValueError("Nicht unterstützte Auflösung.")
    points = select_authorized_points(db, member, selected_point)
    if not points:
        return []
    ts_from, ts_to = _bounds(period_from, period_to)
    point_directions = {point["metering_point_id"]: point["direction"] for point in points}
    placeholders = ",".join("?" for _ in points)
    rows = db.execute(f"""
        SELECT {bucket_expressions[resolution]} bucket,
               m.metering_point_id, mc.code,
               SUM(m.value_kwh) kwh,
               MAX(COALESCE(m.is_estimated, 0)) has_estimated
        FROM measurements m
        JOIN meter_codes mc ON mc.id=m.meter_code_id
        WHERE m.metering_point_id IN ({placeholders})
          AND m.timestamp_start>=? AND m.timestamp_start<?
          AND mc.code IN (?, ?, ?, ?, ?)
        GROUP BY bucket, m.metering_point_id, mc.code
        ORDER BY bucket
    """, (
        *point_directions, ts_from, ts_to,
        SERIES_CODES["consumption"], SERIES_CODES["self_coverage"],
        SERIES_CODES["generation"], SERIES_CODES["participation_generation"],
        SERIES_CODES["public_feed"],
    )).fetchall()
    buckets: dict[str, list[dict]] = {}
    estimated: dict[str, bool] = {}
    for row in rows:
        bucket = row["bucket"]
        buckets.setdefault(bucket, []).append({
            **dict(row),
            "point_direction": point_directions[row["metering_point_id"]],
        })
        estimated[bucket] = estimated.get(bucket, False) or bool(row["has_estimated"])
    result = []
    for bucket, bucket_rows in buckets.items():
        totals = _totals_from_rows(bucket_rows)
        derived, errors = _derived(totals)
        result.append({
            "bucket": bucket,
            **{f"{key}_kwh": round(value, 6) for key, value in totals.items()},
            **derived,
            "balance": _balance_payload(totals, derived),
            "contains_estimated_values": estimated[bucket],
            "data_quality_errors": errors,
        })
    return result


def historical_data_status(db, member) -> dict:
    points = member_metering_points(db, member)
    point_ids = [point["metering_point_id"] for point in points]
    if point_ids:
        placeholders = ",".join("?" for _ in point_ids)
        available = db.execute(f"""
            SELECT MIN(timestamp_start) available_from, MAX(timestamp_end) available_until,
                   COUNT(*) measurement_count,
                   SUM(CASE WHEN is_estimated=1 THEN 1 ELSE 0 END) estimated_count
            FROM measurements WHERE metering_point_id IN ({placeholders})
        """, point_ids).fetchone()
    else:
        available = {
            "available_from": None, "available_until": None,
            "measurement_count": 0, "estimated_count": 0,
        }
    latest = db.execute("""
        SELECT imported_at, data_status, import_status
        FROM import_batches
        WHERE replaced_at IS NULL
        ORDER BY imported_at DESC, id DESC LIMIT 1
    """).fetchone()
    imported_points = db.execute(
        "SELECT COUNT(*) FROM metering_points"
    ).fetchone()[0]
    warnings = db.execute("""
        SELECT COUNT(*) FROM import_warnings w
        JOIN import_batches b ON b.id=w.import_batch_id
        WHERE b.replaced_at IS NULL
    """).fetchone()[0]
    return {
        "is_live": False,
        "label": "Historische Energiedaten",
        "available_from": available["available_from"],
        "available_until": available["available_until"],
        "last_imported_at": latest["imported_at"] if latest else None,
        "import_data_status": latest["data_status"] if latest else None,
        "import_status": latest["import_status"] if latest else None,
        "member_metering_point_count": len(points),
        "imported_metering_point_count": imported_points,
        "measurement_count": available["measurement_count"] or 0,
        "estimated_measurement_count": available["estimated_count"] or 0,
        "active_import_warning_count": warnings,
        "notice": "Keine Live-Daten. Auswertung anhand des letzten Datenimports.",
    }
