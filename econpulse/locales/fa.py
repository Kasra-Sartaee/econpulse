"""Persian (fa): strings, Persian digits and Solar Hijri (Jalali) dates.

To add a language, copy this file's shape (see docs/TRANSLATING.md): STRINGS
is required; the functions below are optional hooks used instead of the
English defaults in :mod:`econpulse.i18n`.
"""

from __future__ import annotations

from datetime import date

CODE = 'fa'
NAME = 'فارسی'
RTL = True

STRINGS = {
    'Economic Calendar': 'تقویم اقتصادی',
    'Calendar': 'تقویم',
    'Today': 'امروز',
    'Tomorrow': 'فردا',
    'Yesterday': 'دیروز',
    'Upcoming': 'آینده',
    'Released': 'منتشرشده',
    'Week': 'هفته',
    'Bank holidays': 'تعطیلات بانکی',
    'Views': 'نماها',
    'Tools': 'ابزارها',
    'Trading notes': 'یادداشت\u200cهای معاملاتی',
    'Open widget': 'ویجت',
    'Search events or currency': 'جستجوی رویداد یا ارز',
    'Refresh': 'بروزرسانی',
    'Export': 'خروجی',
    'Settings': 'تنظیمات',
    'Open calendar': 'تقویم کامل',
    'Close': 'بستن',
    'Now': 'اکنون',
    'Jump to the next release': 'رفتن به رویداد بعدی',
    'Hide summary': 'پنهان\u200cکردن خلاصه',
    'Show summary': 'نمایش خلاصه',
    'Next high impact': 'خبر مهم بعدی',
    'Results published': 'نتایج منتشرشده',
    'Holidays': 'تعطیلات',
    'Awaiting data': 'در انتظار داده',
    'Actual values received': 'مقدار واقعی دریافت\u200cشده',
    'Bank and market closures': 'تعطیلی بانک\u200cها و بازارها',
    'No upcoming high-impact release': 'خبر مهمی در پیش نیست',
    'No high-impact releases ahead': 'خبر مهمی در پیش نیست',
    'All': 'همه',
    'High': 'زیاد',
    'Medium': 'متوسط',
    'Low': 'کم',
    'Holiday': 'تعطیل',
    'Time': 'زمان',
    'Cur.': 'ارز',
    'Event': 'رویداد',
    'Actual': 'واقعی',
    'Forecast': 'پیش\u200cبینی',
    'Previous': 'قبلی',
    'Countdown': 'شمارش معکوس',
    'Not posted': 'اعلام نشده',
    'Pending': 'در انتظار',
    'All day': 'تمام روز',
    'All Day': 'تمام روز',
    'Tentative': 'نامشخص',
    'Bank holiday  ·  markets may close early': 'تعطیلی بانکی  ·  بازار ممکن است زودتر بسته شود',
    'Nothing to show': 'موردی برای نمایش نیست',
    'No releases match these filters.': 'هیچ رویدادی با این فیلترها پیدا نشد.',
    'Live': 'زنده',
    'Cached': 'ذخیره\u200cشده',
    'Offline': 'آفلاین',
    'Connecting': 'در حال اتصال',
    'Demo': 'نمایشی',
    'Schedule only': 'فقط زمان\u200cبندی',
    'Sample data, not live': 'داده نمونه، غیرزنده',
    'Fetching calendar…': 'در حال دریافت تقویم…',
    'No calendar data yet': 'هنوز داده\u200cای دریافت نشده',
    'Syncing…': 'در حال همگام\u200cسازی…',
    'Bank holiday today': 'تعطیلی بانکی امروز',
    'Loading calendar data…': 'در حال بارگذاری تقویم…',
    'Refresh available again in 2 minutes': 'بروزرسانی دوباره تا ۲ دقیقه دیگر ممکن است',
    'Preferences': 'تنظیمات',
    'Appearance, alerts and data sources': 'ظاهر، هشدارها و منابع داده',
    'Appearance': 'ظاهر',
    'Theme': 'قالب رنگ',
    'Dark': 'تیره',
    'Light': 'روشن',
    'Language': 'زبان',
    'Time zone': 'منطقه زمانی',
    'Open on launch': 'حالت آغاز',
    'Widget': 'ویجت',
    'Currencies': 'ارزها',
    'Show all': 'همه ارزها',
    'Alerts': 'هشدارها',
    'Always on top of other windows': 'همیشه روی سایر پنجره\u200cها',
    'Show bank and market holidays': 'نمایش تعطیلات بانکی و بازار',
    'Desktop notifications for high-impact releases': 'اعلان دسکتاپ برای اخبار مهم',
    'Play a sound': 'پخش صدای هشدار',
    'Alert me': 'زمان هشدار',
    'At release': 'هنگام انتشار',
    'Forex Factory weekly export': 'خروجی هفتگی Forex Factory',
    'Save': 'ذخیره',
    'Cancel': 'انصراف',
    'Done': 'بستن',
    'System local': 'ساعت سیستم',
    'Tehran (UTC+03:30)': 'تهران (UTC+03:30)',
    'Berlin (DST-aware)': 'برلین (با ساعت تابستانی)',
    'New York (DST-aware)': 'نیویورک (با ساعت تابستانی)',
    'London (DST-aware)': 'لندن (با ساعت تابستانی)',
    'UTC': 'UTC',
    'Dubai (UTC+04:00)': 'دبی (UTC+04:00)',
    'Tokyo (UTC+09:00)': 'توکیو (UTC+09:00)',
    'Tehran': 'تهران',
    'Berlin': 'برلین',
    'New York': 'نیویورک',
    'London': 'لندن',
    'Dubai': 'دبی',
    'Tokyo': 'توکیو',
    'Version': 'نسخه',
    'data may be stale': 'ممکن است داده قدیمی باشد',
    'Demo mode  ·  illustrative values, not live market data': 'حالت نمایشی  ·  مقادیر نمونه، نه داده واقعی بازار',
    'released': 'منتشر شد',
    'Source': 'منبع',
    'Reference period': 'دوره مرجع',
    'n/a': 'ندارد',
    'Bank / market holiday': 'تعطیلی بانک / بازار',
    'All-day market or bank holiday; trading hours may vary.': 'تعطیلی تمام\u200cروز بانک یا بازار؛ ساعات معاملات ممکن است تغییر کند.',
    'Actual came in better than forecast.': 'مقدار واقعی بهتر از پیش\u200cبینی بود.',
    'Actual came in worse than forecast.': 'مقدار واقعی بدتر از پیش\u200cبینی بود.',
    'Stored on this computer only.': 'فقط روی همین رایانه ذخیره می\u200cشود.',
    'Ctrl+S to save': 'ذخیره با Ctrl+S',
    'Releasing now': 'زمان انتشار خبر مهم',
    'now': 'اکنون',
    'Open last view (double-click)': 'آخرین نما (دوبار کلیک)',
    'Show widget': 'نمایش ویجت',
    'Open full calendar': 'تقویم کامل',
    'Widget: Today': 'ویجت: امروز',
    'Widget: Week': 'ویجت: هفته',
    'Toggle Always on Top': 'همیشه رو / عادی',
    'Refresh calendar': 'بروزرسانی تقویم',
    'Exit EconPulse': 'خروج از EconPulse',
    'No events in this view.': 'رویدادی در این نما نیست.',
    'Export visible releases': 'خروجی رویدادهای نمایش\u200cداده\u200cشده',
    'About': 'درباره',
    'Also show other currencies (ZAR, TRY, MXN…)': 'نمایش ارزهای دیگر (ZAR، TRY، MXN…)',
    'Calendar data from': 'منبع داده تقویم',
    'Copied': 'کپی شد',
    'Data source': 'منبع داده',
    'Data: FinanceCalendar.com': 'منبع: FinanceCalendar.com',
    'Demo data': 'داده نمایشی',
    'FinanceCalendar.com API key': 'کلید API برای FinanceCalendar.com',
    'Get an API key': 'دریافت کلید API',
    'Get the new version': 'دریافت نسخه جدید',
    'Market data by biquote': 'داده\u200cهای بازار از biquote',
    'New version available': 'نسخه جدید موجود است',
    'Next try': 'تلاش بعدی',
    'Open source page': 'مشاهده منبع',
    'Schedule: Forex Factory weekly export': 'زمان\u200cبندی: خروجی هفتگی Forex Factory',
    'Show only the selected currencies. With none selected, all major currencies are shown.': 'فقط ارزهای انتخاب\u200cشده نمایش داده می\u200cشوند؛ اگر هیچ\u200cکدام انتخاب نشود، همه ارزهای اصلی نمایش داده می\u200cشوند.',
    'Start at login': 'اجرا هنگام ورود به سیستم',
    'Start automatically at login': 'اجرای خودکار هنگام ورود به سیستم',
    'Tell me when a new version is out (checks GitHub once a day)': 'اطلاع از انتشار نسخه جدید (روزی یک بار از GitHub بررسی می\u200cشود)',
    'The data source asked us to wait before the next refresh': 'منبع داده خواسته است پیش از بروزرسانی بعدی کمی صبر کنیم',
    'Toggle start at login': 'اجرا هنگام ورود / خاموش',
    'Updates': 'بروزرسانی\u200cها',
    'biquote: free, no key; Actual, Forecast and Previous values.': 'biquote: رایگان و بدون کلید؛ مقادیر واقعی، پیش\u200cبینی و قبلی.',
    'Forex Factory weekly export: official schedule feed, no Actual values. Also used automatically if the chosen source is unavailable.': 'خروجی هفتگی Forex Factory: زمان\u200cبندی رسمی، بدون مقدار واقعی. اگر منبع انتخاب\u200cشده در دسترس نباشد، خودکار از آن استفاده می\u200cشود.',
    'FinanceCalendar.com: official-agency data; needs your own API key (the free plan has no figures).': 'FinanceCalendar.com: داده نهادهای رسمی آمار؛ به کلید API شخصی نیاز دارد (طرح رایگان ارقام ندارد).',
    'Free and open source (MIT licence). By Aref Hosseini, Kasra Sartaee and contributors.': 'رایگان و متن\u200cباز (مجوز MIT). ساخته Aref Hosseini و Kasra Sartaee و مشارکت\u200cکنندگان.',
    'Not affiliated with any data provider. Not financial advice.': 'وابسته به هیچ منبع داده\u200cای نیست و توصیه مالی محسوب نمی\u200cشود.',
    'Project page': 'صفحه پروژه',
    'Report an issue': 'گزارش مشکل',
    'Open data folder': 'پوشه داده\u200cها',
    'Copy diagnostics': 'کپی اطلاعات عیب\u200cیابی',
    'Notes': 'یادداشت\u200cها',
    'Could not save notes:': 'ذخیره یادداشت\u200cها انجام نشد:',
    'Export failed': 'خروجی با خطا روبه\u200cرو شد',
    'API key rejected': 'کلید API پذیرفته نشد',
    'asked to slow down': 'درخواست کاهش سرعت ارسال شد',
    'unreadable response': 'پاسخ غیرقابل خواندن',
    'Schedule only: this source has no Actual values.': 'فقط زمان\u200cبندی: این منبع مقادیر واقعی ندارد.',
    'Showing saved data.': 'نمایش داده\u200cهای ذخیره\u200cشده.',
    'Showing the Forex Factory schedule (no Actual values).': 'نمایش زمان\u200cبندی Forex Factory (بدون مقدار واقعی).',
    'Notify when Actual is published': 'اعلان هنگام انتشار مقدار واقعی',
    'Fast check after high-impact releases': 'بررسی سریع پس از انتشار اخبار مهم',
    'Result published': 'نتیجه منتشر شد',
    'Star': 'نشان\u200cگذاری',
    'Starred': 'نشان\u200cگذاری\u200cشده',
    'Release note': 'یادداشت این رویداد',
    'Private note for this indicator (saved locally)': 'یادداشت شخصی برای این شاخص (ذخیره محلی)',
}


JALALI_MONTHS = ('فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور', 'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند')
FA_WEEKDAYS = ('دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنجشنبه', 'جمعه', 'شنبه', 'یکشنبه')  # Monday first


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Arithmetic Gregorian -> Solar Hijri conversion (valid for 1600–2400 CE)."""
    days_before_month = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + days_before_month[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


_DIGITS = str.maketrans('0123456789', '۰۱۲۳۴۵۶۷۸۹')


def digits(value) -> str:
    return str(value).translate(_DIGITS)


_NOUNS = {'release': 'رویداد', 'holiday': 'تعطیلی'}


def count(n: int, noun: str) -> str:
    # Persian nouns stay singular after a number.
    return f'{digits(n)} {_NOUNS[noun]}'


def minutes(n: int) -> str:
    return f'{digits(n)} دقیقه'


def alert_heading(stage: int) -> str:
    return f'خبر مهم تا {digits(stage)} دقیقه دیگر'


def impact_text(impact: str) -> str:
    return 'اهمیت ' + STRINGS.get(impact, impact)


def sync_detail(stamp: str, age_minutes: int) -> str:
    return f'همگام\u200cسازی {stamp}' + (f'  ·  {digits(age_minutes)} دقیقه پیش' if age_minutes >= 1 else '')


def sync_status(source: str, stamp: str, age_minutes: int) -> str:
    return f'{STRINGS.get(source, source)}  ·  آخرین همگام\u200cسازی {stamp}  ·  {digits(age_minutes)} دقیقه پیش'


def countdown_in(text: str) -> str:
    return f'{text} مانده'


def revised_from(previous: str) -> str:
    return f'مقدار قبلی از {previous} اصلاح شده است.'


def weekday(d: date) -> str:
    return FA_WEEKDAYS[d.weekday()]


def date_text(d: date, style: str) -> str:
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    day_month = f'{digits(jd)} {JALALI_MONTHS[jm - 1]}'
    if style == 'full':
        return f'{weekday(d)} {day_month} {digits(jy)}'
    if style in ('long', 'medium'):
        return f'{weekday(d)} {day_month}'
    return day_month
