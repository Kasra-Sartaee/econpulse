"""Clearly labelled sample data for --demo (screenshots and testing)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .core import parse_feed


def demo_events():
    """Artificial records, only for --demo screenshot and testing."""
    now = datetime.now(UTC)
    records = [
        (-180, 'USD', 'High', 'Non-Farm Employment Change', '165K', '142K', '188K', 'better'),
        (-65, 'EUR', 'Medium', 'Industrial Production m/m', '0.1%', '0.3%', '0.2%', 'worse'),
        (-22, 'USD', 'High', 'Core CPI m/m', '0.3%', '0.3%', '0.2%', ''),
        (12, 'USD', 'High', 'CPI y/y', '', '2.8%', '2.9%', ''),
        (12, 'USD', 'High', 'Core CPI y/y', '', '3.1%', '3.2%', ''),
        (57, 'GBP', 'Medium', 'Manufacturing Production m/m', '', '0.2%', '0.1%', ''),
        (88, 'EUR', 'High', 'ECB President Lagarde Speaks', '', '', '', ''),
        (160, 'CAD', 'Low', 'Housing Starts', '', '245K', '251K', ''),
        (280, 'USD', 'Medium', 'Crude Oil Inventories', '', '-1.2M', '0.9M', ''),
        (890, 'JPY', 'High', 'BOJ Monetary Policy Statement', '', '', '', ''),
        (1520, 'AUD', 'High', 'RBA Rate Decision', '', '3.75%', '3.75%', ''),
        (2100, 'NZD', 'Medium', 'Business PMI', '', '49.8', '49.2', ''),
        (2550, 'CHF', 'Low', 'Producer Price Index m/m', '', '0.1%', '-0.2%', ''),
        (3000, 'CNY', 'Medium', 'Industrial Production y/y', '', '5.6%', '5.4%', ''),
    ]
    out = [
        dict(
            date=(now + timedelta(minutes=m)).isoformat(),
            country=c,
            title=t,
            impact=impact,
            actual=actual,
            forecast=forecast,
            previous=previous,
            actual_tone=tone,
            source='DEMO',
        )
        for m, c, impact, t, actual, forecast, previous, tone in records
    ]
    for d, c in ((0, 'EUR'), (0, 'CAD'), (0, 'USD'), (1, 'JPY')):
        noon = (now + timedelta(days=d)).replace(hour=12, minute=0, second=0, microsecond=0)
        out.append(dict(date=noon.isoformat(), country=c, title='Bank Holiday', impact='Holiday', source='DEMO'))
    return parse_feed(out)
