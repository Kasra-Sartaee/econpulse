# Showing the next release in OBS, Stream Deck or a script

EconPulse can keep a small status file, `next.json`, up to date with the next high-impact release. Anything that can read a file can use it: a streaming overlay, a Stream Deck button, a trading script.

## Turn it on

**Settings → Data source → Write live status file (next.json)**. It is off by default.

The file is in your data folder (**Settings → About → Open data folder**):

| System | Path |
|---|---|
| Windows | `%APPDATA%\EconPulse\next.json` |
| macOS | `~/Library/Application Support/EconPulse/next.json` |
| Linux | `~/.config/EconPulse/next.json` |

It is rewritten once a minute, also while EconPulse is hidden in the tray, and always atomically, so a reader never sees a half-written file.

## What's in it

```json
{
  "updated_at": "2026-11-20T13:25:00+00:00",
  "state": "live",
  "source": "biquote",
  "last_sync": "2026-11-20T13:15:02+00:00",
  "event_count": 412,
  "next_high_impact": {
    "uid": "bq:mql5:326749",
    "currency": "USD",
    "title": "Non-Farm Employment Change",
    "impact": "High",
    "instant_utc": "2026-11-20T13:30:00+00:00",
    "local_time": "2026-11-20T08:30:00-05:00",
    "countdown": "00:05:00",
    "seconds_remaining": 300,
    "forecast": "142K",
    "previous": "188K",
    "revised_from": ""
  }
}
```

- `state` is `live`, `cached` (the last good data, because the source is unreachable), `offline` (nothing loaded yet and no network), `loading` or `demo`.
- `next_high_impact` is `null` when nothing high-impact is ahead in your watched currencies.
- `countdown` and `seconds_remaining` are correct when the file is written (once a minute). For a ticking countdown, compute it from `instant_utc`.

## OBS

OBS's *Text (GDI+)* source can show a text file, but not pick fields out of JSON. This small script turns `next.json` into a one-line `next.txt` every second. Save it as `next_to_text.py` and keep it running while you stream:

```python
"""Write next.txt (for an OBS text source) from EconPulse's next.json, every second."""

from datetime import datetime, timezone
import json, os, pathlib, time

# Windows and Linux; on macOS use pathlib.Path.home() / 'Library/Application Support/EconPulse'
folder = pathlib.Path(os.environ.get('APPDATA', pathlib.Path.home() / '.config')) / 'EconPulse'
while True:
    try:
        nxt = json.loads((folder / 'next.json').read_text(encoding='utf-8'))['next_high_impact']
        if nxt:
            left = datetime.fromisoformat(nxt['instant_utc']) - datetime.now(timezone.utc)
            secs = max(0, int(left.total_seconds()))
            line = f'{nxt["currency"]} {nxt["title"]}  {secs // 3600:02}:{secs % 3600 // 60:02}:{secs % 60:02}'
        else:
            line = 'No high-impact releases ahead'
        (folder / 'next.txt').write_text(line, encoding='utf-8')
    except (OSError, ValueError, KeyError):
        pass  # EconPulse not running yet, or the setting is off
    time.sleep(1)
```

In OBS: **Sources → + → Text (GDI+) → Read from file**, and choose `next.txt` in the same folder.

## Stream Deck and scripts

Any plugin that can show the output of a command or the contents of a file works the same way: point it at `next.txt` from the script above, or read `next.json` directly. In a script, `next.json` is the stable interface: fields may be added in later versions, but these won't be renamed or removed without a note in the changelog.
