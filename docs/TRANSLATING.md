# Adding a language

A language is one Python file in `econpulse/locales/` plus one line in the registry. Persian (`locales/fa.py`) is a complete example, including right-to-left layout and a non-Gregorian calendar.

## 1. Create the locale file

Copy `econpulse/locales/fa.py` to `econpulse/locales/<code>.py` (an ISO 639-1 code such as `de`, `tr`, `ar`) and edit:

```python
CODE = 'de'
NAME = 'Deutsch'  # shown in Settings, in the language itself
RTL = False  # True for right-to-left scripts (Arabic, Persian, Hebrew, ...)

STRINGS = {
    'Economic Calendar': 'Wirtschaftskalender',
    'Today': 'Heute',
    # ... every key from fa.py's STRINGS, translated
}
```

Translate the **values** only, never the keys. Keep these as they are: event titles from the data source, currency codes, and the names EconPulse, biquote, Forex Factory and FinanceCalendar.com.

## 2. Optional hooks

Any of these functions in the locale file replace the English behaviour. Delete the ones you don't need (for example, German needs none of Persian's digit and calendar hooks):

| Hook | Purpose | English default |
|---|---|---|
| `digits(value)` | Native digits inside sentences | unchanged |
| `count(n, noun)` | "12 releases", where noun is `'release'` or `'holiday'` | `12 releases` |
| `minutes(n)` | Alert lead-time captions | `15 min` |
| `alert_heading(stage)` | Notification title before a release | `High-impact release in 15 min` |
| `impact_text(impact)` | "High impact" in the details window | `High impact` |
| `weekday(d)`, `date_text(d, style)` | Dates; style is `full`, `long`, `medium` or `short` | Gregorian, English |

Clock times, countdowns and figures always keep Latin digits so the columns line up.

## 3. Register it

In `econpulse/i18n.py`:

```python
from .locales import de, fa

LANGUAGES = {'en': _English, 'fa': fa, 'de': de}
```

## 4. Check it

```sh
python -m unittest discover -s tests -p "test_translations.py"
python main.py --demo
```

The test fails until every interface string has a translation and names any that are missing. Then switch the language in Settings and look through the widget, the full calendar, a release's details, Preferences and the tray menu.

For right-to-left languages the layout mirrors automatically. If a mixed line of your script and numbers displays in the wrong order, the usual cure is to draw the label and the value as separate items. `NextUp` in `event_list.py` shows how.
