# معماری OMID Industrial AI Agent

> **هوشمندسازی صنعت امید** — ما می‌سازیم تا شما راحت زندگی کنید
> طراح و سازندهٔ اصلی: مهندس امید براتی | با همکاری: دکتر کیمیا زهرا براتی و مهندس محسن بابایی

## ۱. اصول حاکم

1. **صداقت عملیاتی:** هیچ وضعیتی بدون شاهد (کد/تست/اجرا) «موفق» اعلام نمی‌شود. هر خروجی برچسب منبع دارد: `simulation` یا `live`.
2. **تفکیک تصمیم از اجرا:** مدل زبانی فقط «پیشنهاد ابزار از فهرست مجاز» تولید می‌کند؛ اجرا همیشه از رجیستری ابزارها و دروازه‌های ایمنی می‌گذرد.
3. **پیش‌فرض امن:** حالت پیش‌فرض `simulate` است؛ کنترل فیزیکی سه قفل مستقل دارد.
4. **محلی‌محور (local-first):** همهٔ اجزا بدون اینترنت کار می‌کنند؛ داشبورد هیچ منبع خارجی (CDN) ندارد.
5. **قابلیت ممیزی:** همهٔ رویدادهای مهم در لاگ حسابرسی JSONL با redaction خودکار ثبت می‌شوند.
6. **degradation صادقانه:** نبود Ollama، نبود pyserial یا نبود سخت‌افزار با پیام روشن گزارش می‌شود، نه وانمود.

## ۲. لایه‌ها و جریان داده

```
کاربر (داشبورد/CLI/API)
        │  زبان طبیعی
        ▼
AgentRuntime.handle_request
        │ ۱) تحلیل هدف: LLM planner (در صورت سلامت Ollama) یا موتور قواعد
        │ ۲) اعتبارسنجی برنامه: فقط ابزارهای ثبت‌شده، args باید dict باشد
        ▼
TaskManager (چرخهٔ حیات وظیفه: pending→running→[waiting_confirm]→…)
        │ ۳) اجرای مرحله‌به‌مرحله با deadline و امکان لغو
        ▼
ToolRegistry.invoke
        │ ۴) PermissionPolicy.check → SafetyManager.assert_allowed
        │    (ریسک ابزار × حالت عملیاتی × E-Stop × اعتبار کنترل × kill-switch)
        │ ۵) اجرا با timeout در ThreadPool + حسابرسی قبل/بعد
        ▼
قابلیت‌ها: drivers / twin / discovery / knowledge / memory / diagnostics
        │ ۶) نتیجه با evidence (زمان، ریسک، حالت، source) بازمی‌گردد
        ▼
گزارش روشن فارسی + ثبت در حافظهٔ عملیات
```

## ۳. ماژول‌ها

| ماژول | مسئولیت | نکتهٔ طراحی |
|---|---|---|
| `omid.branding` | منبع یکتای هویت | branding.json + آزمون برند |
| `omid.config` | پیکربندی محیطی | frozen dataclass، اعتبارسنجی صریح، `public_view` بدون راز |
| `omid.events` | رویداد/حسابرسی | redaction کلیدهای حساس پیش از نوشتن روی دیسک |
| `omid.safety` | حالت‌ها، E-Stop، محافظ G-code | **بدون وابستگی به LLM**؛ E-Stop همیشه مجاز |
| `omid.core.permissions` | سطح‌بندی ریسک | read < suggest < simulate < physical + kill-switch ابزار |
| `omid.core.tools` | رجیستری و اجرای مجاز | timeout، evidence، خطاها گزارش می‌شوند نه propagate |
| `omid.core.tasks` | چرخهٔ وظیفه | `waiting_confirm` برای عملیات فیزیکی |
| `omid.core.agent` | حلقهٔ عامل | LLM→JSON سخت‌گیرانه؛ fallback قواعد-محور فارسی/EN |
| `omid.core.builtin_tools` | فهرست ابزارهای مجاز | ۱۴ ابزار داخلی با ریسک صریح |
| `omid.ai.ollama` | مدل محلی | health-check، latency، خطاهای صادقانه |
| `omid.discovery` | رجیستری/کشف تجهیزات | allowlist شبکه؛ pyserial با import محافظت‌شده |
| `omid.drivers` | رابط مشترک درایور | `CommandResult.source` = simulation/live |
| `omid.twin` | شبیه‌ساز/Digital Twin | پیش‌نمایش حرکت + dry-run سناریو |
| `omid.knowledge` | RAG محلی | TF-IDF ساده + نرمال‌سازی فارسی (ی/ک، نیم‌فاصله) |
| `omid.memory` | حافظهٔ بلندمدت | SQLite + redaction + prune + export |
| `omid.diagnostics` | تشخیص عیب | قواعد صریح با severity/confidence/suggestion |
| `omid.api` | FastAPI | auth تفکیک‌شده، rate-limit، CSP بدون unsafe-inline |
| `omid.dashboard` | رابط RTL | بدون CDN؛ برچسب SIMULATION/LIVE |

## ۴. تصمیم‌های کلیدی

- **همه‌چیز sync + ThreadPool:** سادگی و قابلیت آزمون بر async ارجحیت یافت؛ FastAPI هندلرهای sync را در threadpool اجرا می‌کند. E-Stop با `threading.RLock` محافظت می‌شود.
- **duck-typing در Policy:** `PermissionPolicy` نمونهٔ SafetyManager را می‌گیرد بدون import ماژول ایمنی → بدون وابستگی حلقوی.
- **Composition Root واحد (`AppContext`):** API، CLI و تست‌ها همه از یک ریشه ساخته می‌شوند تا رفتار یکسان بماند.
- **دو توکن مجزا (خواندن/کنترل):** فقدان توکن کنترل = غیرفعال بودن کامل عملیات کنترلی (پیش‌فرض امن).
- **CSP سخت‌گیرانه:** JS/CSS داشبورد در فایل‌های جدا هستند تا `unsafe-inline` لازم نباشد.

## ۵. نقاط توسعه

- درایور جدید: کلاس جدید از `DeviceDriver` + ثبت در `AppContext.drivers` + ابزارهای متناسب در `builtin_tools`.
- قاعدهٔ تشخیص جدید: یک `Rule` به `FaultDetector(extra_rules=...)`.
- ابزار جدید: `Tool(name, description, risk, handler)` در `register_builtin_tools`.
- ارائه‌دهندهٔ AI جدید: کلاسی با همان قرارداد `health()/chat()` (OpenAI-compatible و …).

## ۶. آزمون‌ها و CI

- ~۹۰ آزمون در `tests/` (واحد + یکپارچه + API + CLI + برند).
- CI روی هر push/PR: `ruff check` + `python -m omid selfcheck` + `pytest` با گزارش JUnit.
- دادهٔ آزمون کاملاً در `tmp_path` ایزوله است و با حافظهٔ واقعی قاطی نمی‌شود.
