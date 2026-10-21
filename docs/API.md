# راهنمای API — OMID Industrial AI Agent

> **هوشمندسازی صنعت امید** — ما می‌سازیم تا شما راحت زندگی کنید
> طراح و سازندهٔ اصلی: مهندس امید براتی

Base URL: `http://127.0.0.1:8000` — مستندات زندهٔ Swagger: `/api/docs`

## احراز هویت

| سطح | هدر | منبع |
|---|---|---|
| خواندن | `Authorization: Bearer <OMID_API_TOKEN>` | توکن خواندن |
| کنترل | `X-OMID-Control-Token: <OMID_CONTROL_TOKEN>` | توکن کنترل (جداگانه) |

اگر `OMID_API_TOKEN` تنظیم نشده باشد، API فقط روی `localhost`/loopback اجازهٔ اجرا دارد و برای bind کردن به `0.0.0.0` یا IP/hostname شبکه، پیکربندی با خطا متوقف می‌شود. برای دسترسی شبکه‌ای، توکن خواندن قوی در `OMID_API_TOKEN` تنظیم کنید. اگر `OMID_CONTROL_TOKEN` تنظیم نشده باشد، **همهٔ endpointهای کنترلی رد می‌شوند** (پیش‌فرض امن).

## Endpointها

### باز (بدون احراز هویت)
| متد | مسیر | توضیح |
|---|---|---|
| GET | `/api/health` | liveness ساده |
| GET | `/api/about` | هویت رسمی پروژه از branding.json |
| GET | `/` → `/dashboard/` | داشبورد |

### خواندن (Bearer)
| متد | مسیر | توضیح |
|---|---|---|
| GET | `/api/status` | وضعیت کامل: ایمنی، AI، شمارنده‌ها |
| GET | `/api/events?limit&severity&type_prefix` | رویدادهای حسابرسی (redact‌شده) |
| POST | `/api/agent/request` `{text}` | درخواست زبان طبیعی → وظیفه با شواهد |
| GET | `/api/tasks` / `/api/tasks/{id}` | فهرست/جزئیات وظایف |
| POST | `/api/tasks/{id}/cancel` | لغو همکاری‌جویانه |
| GET | `/api/safety` | snapshot ایمنی |
| POST | `/api/safety/estop` `{reason}` | **توقف اضطراری — fail-safe** |
| GET | `/api/devices` / `/api/devices/{id}` | رجیستری تجهیزات |
| POST | `/api/devices/discover` `{scope: serial\|network}` | کشف مجاز |
| GET | `/api/drivers` / POST `/api/drivers/{name}/status` | درایورها |
| GET | `/api/twin` | snapshot twin (برچسب SIMULATION) |
| POST | `/api/twin/preview` `{x,y,z,feed}` | پیش‌نمایش حرکت روی twin |
| GET | `/api/knowledge/search?q&k` | جست‌وجوی RAG با ارجاع به منبع |
| GET | `/api/knowledge/docs` | فهرست مستندات نمایه‌شده |
| GET | `/api/memory/search?q` / `/api/memory/operations` | حافظه |
| GET | `/api/diagnostics/rules` / `findings` / POST `scan` | تشخیص عیب قواعد-محور |

### کنترل (Bearer + X-OMID-Control-Token)
| متد | مسیر | توضیح |
|---|---|---|
| POST | `/api/safety/mode` `{mode, confirm}` | تغییر حالت (control نیازمند عبارت تأیید) |
| POST | `/api/safety/estop/release` `{confirm}` | آزادسازی E-Stop |
| POST | `/api/tasks/{id}/confirm` | تأیید صریح عملیات فیزیکی |
| POST | `/api/knowledge/ingest` `{path}` / `ingest-dir` `{dir}` | ورود مستندات (دسترسی FS سرور) |
| POST/DELETE | `/api/memory/prefs` | نوشتن/حذف ترجیحات |
| POST | `/api/memory/export` | خروجی کامل حافظه |

## محدودیت نرخ

پیش‌فرض ۲۴۰ درخواست در دقیقه به ازای هر کلاینت (`OMID_RATE_LIMIT_PER_MIN`). پاسخ `429` با هدر `Retry-After`. مسیر `/api/health` معاف است.

## نمونه‌ها

```bash
# وضعیت
curl -H "Authorization: Bearer $OMID_API_TOKEN" http://127.0.0.1:8000/api/status

# درخواست به عامل
curl -X POST http://127.0.0.1:8000/api/agent/request \
  -H "Authorization: Bearer $OMID_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"text": "وضعیت سیستم را بررسی کن"}'

# توقف اضطراری
curl -X POST http://127.0.0.1:8000/api/safety/estop \
  -H "Authorization: Bearer $OMID_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"reason": "اپراتور"}'
```

## کدهای خطا

| کد | معنا |
|---|---|
| 401 | توکن خواندن نامعتبر/نیامده |
| 403 | فقدان اعتبار کنترل (یا توکن کنترل پیکربندی نشده) |
| 409 | تضاد با قواعد ایمنی (مثلاً قفل کنترل فیزیکی بسته) |
| 422 | ورودی نامعتبر یا پرسش خالی |
| 429 | عبور از محدودیت نرخ |

خطاها هیچ‌گاه توکن یا راز را بازنویسی نمی‌کنند.
