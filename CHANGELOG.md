# CHANGELOG — OMID Industrial AI Agent

> **هوشمندسازی صنعت امید** — ما می‌سازیم تا شما راحت زندگی کنید
> طراح و سازندهٔ اصلی: مهندس امید براتی | با همکاری: دکتر کیمیا زهرا براتی و مهندس محسن بابایی

قالب بر پایهٔ [Keep a Changelog](https://keepachangelog.com/fa-IR/1.1.0/) و نسخه‌گذاری [SemVer](https://semver.org/lang/fa/).

## [0.1.0] - 2026-10-21

### افزوده‌شده
- **هستهٔ عامل:** چرخهٔ وظیفه (ایجاد/اجرا/لغو/timeout/تأیید)، رجیستری ابزارها با ۱۴ ابزار داخلی، سطح‌بندی ریسک (read/suggest/simulate/physical)، موتور قواعد-محور فارسی/انگلیسی.
- **لایهٔ ایمنی:** حالت‌های observe/simulate/control، سه قفل ورود به کنترل فیزیکی، توقف اضطراری مستقل از LLM، محافظ G-code (whitelist فقط‌خواندنی)، اعتبارسنجی محدودهٔ حرکت.
- **AI محلی:** کلاینت Ollama با health-check، latency و fallback صادقانه؛ برنامه‌ریز JSON سخت‌گیرانه (خروجی آزاد مدل هرگز اجرا نمی‌شود).
- **تجهیزات:** رجیستری پایدار دستگاه‌ها، کشف سریال (pyserial اختیاری)، probe شبکه فقط روی allowlist، درایور GRBL با شبیه‌ساز کامل و مسیر سریال محافظت‌شده.
- **Digital Twin:** پیش‌نمایش حرکت و dry-run سناریو با برچسب صریح SIMULATION.
- **دانش و حافظه:** RAG محلی با نرمال‌سازی فارسی و ارجاع به منبع؛ حافظهٔ بلندمدت SQLite با redaction، prune و export.
- **تشخیص عیب:** ۷ قاعدهٔ داخلی با severity/confidence/suggestion و برچسب منبع داده (قواعد-محور، نه مدل پیش‌بینی تأییدشده).
- **API و داشبورد:** FastAPI با احراز هویت تفکیک‌شدهٔ خواندن/کنترل، rate-limit، CSP بدون unsafe-inline، سرصفحه‌های امنیتی؛ داشبورد RTL فارسی بدون CDN با ۱۰ نما.
- **هویت برند:** منبع یکتای `branding.json` + ماژول `omid.branding` + آزمون خودکار برند در README/داشبورد/API/مستندات.
- **کیفیت:** ~۹۰ آزمون pytest، Lint با ruff، CLI (`selfcheck`/`serve`/`request`/`brand`)، GitHub Actions CI، مستندسازی کامل (README، ARCHITECTURE، SAFETY، API، SECURITY، CONTRIBUTING).

### شناخته‌شده (صادقانه)
- بینایی ماشین پیاده نشده است.
- پروتکل‌های Modbus/OPC UA/MQTT فقط در حد کشف پورت هستند.
- اجرای فیزیکی GRBL روی سخت‌افزار واقعی آزمون میدانی نشده است.
- استخراج PDF/DOCX برای RAG پیاده نشده است.

[0.1.0]: https://github.com/omidbaratii292929-hash/ai-qwin/releases/tag/v0.1.0
