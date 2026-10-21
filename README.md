# OMID Industrial AI Agent — عامل هوشمند صنعتی امید

> **هوشمندسازی صنعت امید**
> **«ما می‌سازیم تا شما راحت زندگی کنید»**
> طراح و سازندهٔ اصلی: **مهندس امید براتی**
> با همکاری: **دکتر کیمیا زهرا براتی** و **مهندس محسن بابایی**

> **وضعیت CI:** گردش کار GitHub Actions فعال است و با push به شاخهٔ `main` و هر Pull Request اجرا می‌شود. نتیجهٔ آخرین اجرای شاخهٔ اصلی پس از ادغام PR شمارهٔ ۹ موفق بوده است. [مشاهدهٔ اجراها](https://github.com/omidbaratii292929-hash/ai-qwin/actions/workflows/ci.yml).

سامانهٔ **OMID** یک عامل هوشمند صنعتیِ ماژولار، محلی‌محور (local-first) و قابل‌ممیزی است که می‌تواند وضعیت سیستم و تجهیزات را بررسی کند، اطلاعات فنی و مستندات را تحلیل کند (RAG)، عیب‌ها را با قواعد فنی تشخیص دهد، عملیات را در محیط شبیه‌سازی آزمایش کند و در محدودهٔ مجوزهای صریح، عملیات فیزیکی را از طریق درایورهای کنترل‌شده اجرا نماید.

**اصل بنیادین این پروژه صداقت عملیاتی است:** هیچ قابلیتی بدون شاهد قابل‌بررسی (کد، آزمون، اجرای واقعی) «انجام‌شده» اعلام نمی‌شود و دادهٔ شبیه‌سازی‌شده هرگز به‌جای دادهٔ زنده جا نمی‌زند.

---

## جدول وضعیت قابلیت‌ها (صادقانه)

| قابلیت | وضعیت | شاهد |
|---|---|---|
| هستهٔ عامل (وظایف، ابزارها، مجوزها، رویدادها) | ✅ پیاده‌سازی + تست‌شده | `tests/test_agent.py`, `tests/test_tools.py` |
| لایهٔ ایمنی (حالت‌ها، E-Stop، قفل‌ها) | ✅ پیاده‌سازی + تست‌شده | `tests/test_safety.py` |
| موتور قواعد-محور فارسی/انگلیسی | ✅ پیاده‌سازی + تست‌شده | `tests/test_agent.py` |
| اتصال Ollama (برنامه‌ریز LLM) | ✅ کد کامل؛ **نیازمند Ollama روی ماشین شما** | `tests/test_ollama.py` (mock) |
| درایور GRBL — حالت شبیه‌سازی | ✅ پیاده‌سازی + تست‌شده | `tests/test_grbl.py` |
| درایور GRBL — سخت‌افزار واقعی | ⚠️ کد آماده؛ روی سخت‌افزار واقعی آزمون نشده | نیازمند pyserial + دستگاه |
| کشف پورت‌های سریال | ✅ زیرساخت کامل؛ نیازمند pyserial | `tests/test_discovery.py` |
| کشف شبکه (Modbus/OPC UA/MQTT) | ⚠️ فقط probe مجازِ allowlist؛ پروتکل‌کاوی عمیق در توسعه | `tests/test_discovery.py` |
| Digital Twin و شبیه‌ساز سناریو | ✅ پیاده‌سازی + تست‌شده | `tests/test_twin.py` |
| RAG و پایگاه دانش (متن/مارک‌داون) | ✅ پیاده‌سازی + تست‌شده | `tests/test_rag.py` |
| استخراج PDF/DOCX برای RAG | ❌ هنوز پیاده نشده (صادقانه) | — |
| حافظهٔ بلندمدت (SQLite) | ✅ پیاده‌سازی + تست‌شده | `tests/test_memory.py` |
| تشخیص عیب قواعد-محور | ✅ پیاده‌سازی + تست‌شده (مدل پیش‌بینی تأییدشده **نیست**) | `tests/test_diagnostics.py` |
| بینایی ماشین (Vision) | ❌ در نقشهٔ راه — بدون داده/دوربین واقعی ادعایی نداریم | — |
| API محافظت‌شده + داشبورد RTL | ✅ پیاده‌سازی + تست‌شده | `tests/test_api.py` |
| هویت برند یکپارچه + آزمون برند | ✅ پیاده‌سازی + تست‌شده | `tests/test_branding.py` |
| CI (GitHub Actions) | ✅ فعال؛ lint، self-check و pytest در CI | `.github/workflows/ci.yml` |

> نشان‌های ساختگی مثل «۱۰۰٪ دقیق» یا «آمادهٔ تولید صنعتی» عمداً استفاده نشده‌اند.

---

## معماری در یک نگاه

```
┌────────────────────────────────────────────────────────────────┐
│  داشبورد RTL (بدون CDN)  +  REST API (FastAPI)                 │
│  احراز هویت تفکیک‌شده: خواندن / کنترل  +  rate-limit  +  CSP    │
├────────────────────────────────────────────────────────────────┤
│  هستهٔ عامل: تحلیل هدف → برنامه‌ریزی → اجرای مجاز → شاهد       │
│  (LLM فقط «پیشنهاد ابزار از فهرست مجاز» می‌دهد؛ اجرا هرگز      │
│   مستقیم از متن مدل انجام نمی‌شود)                              │
├──────────────┬──────────────┬───────────────┬──────────────────┤
│ ایمنی        │ تجهیزات       │ هوشمندی       │ دانش/حافظه       │
│ حالت‌ها       │ کشف (سریال/   │ Ollama (اختیاری)│ RAG محلی        │
│ E-Stop مستقل │ شبکهٔ مجاز)   │ قواعد فارسی/EN │ SQLite           │
│ محافظ G-code │ درایور GRBL   │ تشخیص عیب      │ حسابرسی JSONL     │
│              │ Digital Twin  │               │                  │
└──────────────┴──────────────┴───────────────┴──────────────────┘
```

جزئیات کامل: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — قواعد ایمنی: [`docs/SAFETY.md`](docs/SAFETY.md)

### ساختار پوشه‌ها

```
omid/
├── branding.py          # منبع یکتای هویت برند
├── config.py            # پیکربندی محیطی اعتبارسنجی‌شده
├── events.py            # گذرگاه رویداد + لاگ حسابرسی (redaction خودکار)
├── context.py           # ریشهٔ ترکیب (Composition Root) + selfcheck
├── safety/              # حالت‌ها، E-Stop، اعتبارسنج حرکت، محافظ G-code
├── core/                # مجوزها، ابزارها، وظایف، حلقهٔ عامل، ابزارهای داخلی
├── ai/                  # کلاینت Ollama با health-check
├── discovery/           # رجیستری دستگاه‌ها + کشف سریال/شبکهٔ مجاز
├── drivers/             # رابط درایور + GRBL (شبیه‌ساز/سریال)
├── twin/                # Digital Twin با برچسب SIMULATION/LIVE
├── knowledge/           # RAG محلی (فارسی/انگلیسی) با ارجاع به منبع
├── memory/              # حافظهٔ بلندمدت SQLite
├── diagnostics/         # تشخیص عیب قواعد-محور
├── api/                 # FastAPI: auth، middleware، روترها
└── dashboard/static/    # داشبورد RTL بدون هیچ منبع خارجی
tests/                   # آزمون‌های واحد/یکپارچه
docs/                    # معماری، ایمنی، API، گزارش‌های مرحله‌ای
branding.json            # منبع یکتای اطلاعات هویت
```

---

## نیازمندی‌ها و نصب

- Python 3.10 یا جدیدتر
- (اختیاری) [Ollama](https://ollama.com) برای برنامه‌ریز LLM محلی
- (اختیاری) `pyserial` فقط روی ماشینی که سخت‌افزار سریال واقعی دارد

```bash
git clone https://github.com/omidbaratii292929-hash/ai-qwin.git
cd ai-qwin
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt          # اجرایی
pip install -r requirements-dev.txt      # توسعه/تست (pytest + ruff)
# اختیاری برای سخت‌افزار واقعی: pip install pyserial
```

## پیکربندی

```bash
cp .env.example .env      # ویرایش مقادیر
```

متغیرهای کلیدی (توضیح کامل در [`.env.example`](.env.example)):

| متغیر | پیش‌فرض | نقش |
|---|---|---|
| `OMID_MODE` | `simulate` | حالت عملیاتی: `observe`/`simulate`/`control` |
| `OMID_ALLOW_PHYSICAL_CONTROL` | `0` | قفل سخت‌افزاری کنترل فیزیکی |
| `OMID_API_TOKEN` | — | توکن دسترسی خواندن API |
| `OMID_CONTROL_TOKEN` | — | توکن جداگانهٔ عملیات کنترلی |
| `OMID_OLLAMA_URL` / `OMID_OLLAMA_MODEL` | local / خالی | اتصال مدل محلی |
| `OMID_NETWORK_ALLOWLIST` | خالی | تنها میزبان‌های مجاز برای probe شبکه |
| `OMID_GRBL_BACKEND` | `simulated` | انتخاب صریح `simulated` یا درایور سریال `serial` |
| `OMID_GRBL_SERIAL_PORT` | — | در حالت سریال الزامی است؛ مثلاً `COM11` |
| `OMID_GRBL_BAUDRATE` | `115200` | سرعت ارتباط سریال GRBL |

> **هشدار:** توکن‌ها را هرگز در مخزن commit نکنید. `.env` در `.gitignore` است.

## اجرا

```bash
python -m omid selfcheck            # خودآزمایی کامل با شواهد (JSON)
python -m omid serve                # API: http://127.0.0.1:8000 — داشبورد: /dashboard/
python -m omid request "وضعیت سیستم را بررسی کن"   # درخواست یک‌شات از CLI
python -m omid brand                # چاپ هویت رسمی پروژه
```

نمونه درخواست‌های قابل‌فهم توسط موتور قواعد-محور (فارسی/انگلیسی):

```
وضعیت سیستم را بررسی کن          → system_status
تجهیزات را کشف کن               → discover_devices (سریال)
حرکت به x=100 y=50 را شبیه‌سازی کن → simulate_motion (فقط twin)
درباره پروژه                     → get_branding
کمک                              → describe_capabilities
توقف اضطراری                     → trigger_estop (همیشه مجاز)
```

## اتصال به Ollama

1. Ollama را نصب و اجرا کنید: `ollama serve`
2. یک مدل بگیرید: `ollama pull qwen2.5:7b`
3. در `.env`: `OMID_OLLAMA_MODEL=qwen2.5:7b`
4. سامانه ابتدا سلامت سرویس و وجود مدل را بررسی می‌کند؛ در صورت نبود،
   **بدون خطا** به موتور قواعد-محور بازمی‌گردد (degradation صادقانه).

نقش LLM فقط تولید «برنامهٔ JSON» از فهرست ابزارهای مجاز است. ابزار
ساختگی، JSON نامعتبر یا متن آزاد (مثل G-code خام) هرگز اجرا نمی‌شود و در
لاگ حسابرسی ثبت می‌گردد.

## حالت شبیه‌سازی و قواعد ایمنی

- پیش‌فرض امن: `simulate` — هیچ فرمان فیزیکی صادر نمی‌شود.
- شروع برنامه هرگز فقط با مقدار محیطی، حالت `control` را فعال نمی‌کند؛ حتی اگر `OMID_MODE=control` باشد، سامانه روی `simulate` می‌ماند.
  برای ورود runtime به کنترل، `OMID_ALLOW_PHYSICAL_CONTROL=1`، عبارت `ENABLE-PHYSICAL-CONTROL` و خاموش بودن E-Stop لازم است.
- عملیات فیزیکی حتی با همهٔ قفل‌ها، نیازمند **تأیید صریح انسانی** برای هر
  وظیفه است (`waiting_confirm` → `POST /api/tasks/{id}/confirm`).
- توقف اضطراری مسیری مستقل از مدل زبانی دارد، همیشه مجاز است و سامانه را
  به `observe` بازمی‌گرداند.
- G-code خام (مخصوصاً از خروجی مدل) هرگز ارسال نمی‌شود؛ فقط فرمان
  ساختاریافتهٔ `MotionCommand` پس از اعتبارسنجی محدوده.
- جزئیات: [`docs/SAFETY.md`](docs/SAFETY.md)

## داشبورد و API

- داشبورد RTL فارسی روی `/dashboard/` — بدون CDN، قابل استفاده در LAN
  ایزوله. برچسب‌های **SIMULATION/LIVE** در همهٔ نماهای داده.
- مستندات زندهٔ API: `/api/docs` (Swagger) و فهرست endpointها در
  [`docs/API.md`](docs/API.md).
- احراز هویت: `Authorization: Bearer <OMID_API_TOKEN>` برای خواندن؛
  `X-OMID-Control-Token: <OMID_CONTROL_TOKEN>` برای کنترل.
- دسترسی از شبکهٔ محلی به معنی دسترسی عمومی اینترنت نیست؛ پیش‌فرض روی
  `127.0.0.1` bind می‌شود.

## اجرای آزمون‌ها و عیب‌یابی

```bash
ruff check .          # lint
pytest -q             # همهٔ آزمون‌های واحد/یکپارچه
python -m omid selfcheck   # خودآزمایی محیط واقعی
```

| مشکل | علت/راه‌حل |
|---|---|
| `Ollama در دسترس نیست` | طبیعی اگر Ollama نصب نیست — سامانه قواعد-محور کار می‌کند |
| کشف سریال خالی است | `pip install pyserial` (فقط روی ماشین دارای سخت‌افزار) |
| 401 روی API | توکن خواندن را در نوار بالای داشبورد وارد کنید |
| 403 روی عملیات کنترلی | `OMID_CONTROL_TOKEN` تنظیم نشده — کنترل عمداً غیرفعال است |
| 429 | محدودیت نرخ؛ پیش‌فرض ۲۴۰ درخواست بر دقیقه (`OMID_RATE_LIMIT_PER_MIN`) |

## محدودیت‌های شناخته‌شده (اعلام صریح)

1. بینایی ماشین هنوز پیاده نشده است — بدون دوربین و دادهٔ معتبر، ادعایی وجود ندارد.
2. درایورهای Modbus/OPC UA/MQTT در حد «کشف پروتکل از پورت» هستند؛ پیاده‌سازی کامل پروتکل در نقشهٔ راه است.
3. اجرای فیزیکی GRBL روی سخت‌افزار واقعی آزمون میدانی نشده (شبیه‌ساز کامل تست شده است).
4. تشخیص عیب «قواعد-محور» است، نه مدل پیش‌بینی تأییدشده.
5. استخراج متن PDF/DOCX برای RAG پیاده نشده؛ ورودی‌های متنی/مارک‌داون پشتیبانی می‌شوند.
6. rate-limit و حافظهٔ نشست in-memory و مناسب استقرار تک‌گره روی LAN است.

## مشارکت در توسعه

[`CONTRIBUTING.md`](CONTRIBUTING.md) را ببینید. امنیت: [`SECURITY.md`](SECURITY.md). تغییرات: [`CHANGELOG.md`](CHANGELOG.md).

---

## English Summary

**OMID Industrial AI Agent** is a modular, local-first, auditable industrial AI
agent by **Hooshmandsazi Sanat Omid** («هوشمندسازی صنعت امید»), designed and
built by **Eng. Omid Barati** in collaboration with **Dr. Kimia Zahra Barati**
and **Eng. Mohsen Babaee**. It features a tool-permissioned agent core, strict
safety layer (observe/simulate/control modes, independent E-Stop, G-code
guard), GRBL driver with a fully tested simulator, allowlisted network
discovery, digital twin, Persian/English local RAG, SQLite long-term memory,
rule-based fault diagnostics, a hardened FastAPI backend and an RTL dashboard
with zero external assets. The LLM (Ollama) is optional and may only propose
JSON plans over an allowlist of registered tools — raw model output is never
executed. All simulated data is explicitly labeled and never presented as
live measurements.

---

<div dir="rtl">

**© هوشمندسازی صنعت امید — ما می‌سازیم تا شما راحت زندگی کنید**
طراح و سازندهٔ اصلی: مهندس امید براتی | با همکاری: دکتر کیمیا زهرا براتی و مهندس محسن بابایی

</div>
