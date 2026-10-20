# فعال‌سازی CI (GitHub Actions)

> **هوشمندسازی صنعت امید — OMID Industrial AI Agent**

فایل گردش کار CI آماده است اما **عمداً** در این پوشه قرار دارد، نه در
`.github/workflows/`. دلیل (صادقانه): توکن دسترسی استفاده‌شده برای push،
scope `workflow` نداشت و GitHub ایجاد فایل در `.github/workflows/` را رد کرد:

```
! [remote rejected] main (refusing to allow a Personal Access Token to create
  or update workflow `.github/workflows/ci.yml` without `workflow` scope)
```

## دو راه برای فعال‌سازی (هرکدام یک‌بار)

### راه ۱ — از رابط وب GitHub (بدون توکن جدید)
1. در مخزن، دکمهٔ **Add file → Create new file** را بزنید.
2. مسیر را `ci.yml` در پوشهٔ `.github/workflows/` بگذارید
   (GitHub خودش پوشه‌ها را می‌سازد).
3. محتوای `ci/github-actions-ci.yml` را داخلش کپی و commit کنید.

### راه ۲ — توکن با scope بیشتر
یک توکن با scope `workflow` (یا fine-grained با مجوز **Workflows: Read &
Write**) بسازید و سپس:

```bash
mkdir -p .github/workflows
cp ci/github-actions-ci.yml .github/workflows/ci.yml
git add .github/workflows/ci.yml
git commit -m "ci: activate GitHub Actions workflow"
git push
```

پس از فعال‌سازی، نشان CI در README به‌صورت خودکار زنده می‌شود و هر
push/PR این مراحل را اجرا می‌کند: `ruff check` + `python -m omid selfcheck` +
`pytest` با آپلود گزارش JUnit.
