"""omid.__main__ — رابط خط فرمان OMID Industrial AI Agent.

دستورها:
    python -m omid selfcheck          خودآزمایی کامل با شواهد (مناسب CI)
    python -m omid serve              اجرای API و داشبورد
    python -m omid request "متن"      اجرای یک درخواست عامل و چاپ نتیجه
    python -m omid brand              چاپ هویت رسمی پروژه

© هوشمندسازی صنعت امید — ما می‌سازیم تا شما راحت زندگی کنید
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import argparse
import json
import sys

from omid import __version__, branding
from omid.context import AppContext


def cmd_selfcheck(_args: argparse.Namespace) -> int:
    ctx = AppContext()
    try:
        report = ctx.selfcheck()
    finally:
        ctx.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = report.get("overall_ok", False)
    print(f"\nSELF-CHECK: {'PASS' if ok else 'FAIL'} — {report.get('project')} v{report.get('version')}")
    return 0 if ok else 1


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn نصب نیست: pip install -r requirements.txt", file=sys.stderr)
        return 2
    host, port = args.host, args.port
    print(branding.report_header())
    print(f"\nدر حال اجرای API روی http://{host}:{port} — داشبورد: http://{host}:{port}/dashboard/")
    uvicorn.run("omid.api.app:create_app", factory=True, host=host, port=port, log_level="info")
    return 0


def cmd_request(args: argparse.Namespace) -> int:
    ctx = AppContext()
    try:
        task = ctx.agent.handle_request(args.text, requested_by="cli")
    finally:
        ctx.close()
    print(json.dumps(task.to_dict(), ensure_ascii=False, indent=2))
    if task.result_summary:
        print("\n--- خلاصه ---")
        print(task.result_summary)
    return 0 if task.status == "completed" else 1


def cmd_brand(_args: argparse.Namespace) -> int:
    print(branding.report_header())
    print(branding.footer_text())
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omid", description=f"OMID Industrial AI Agent v{__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("selfcheck", help="خودآزمایی کامل با شواهد")

    serve_p = sub.add_parser("serve", help="اجرای API و داشبورد")
    serve_p.add_argument("--host", default=None)
    serve_p.add_argument("--port", type=int, default=None)

    req_p = sub.add_parser("request", help="اجرای یک درخواست عامل")
    req_p.add_argument("text", help="متن درخواست (فارسی یا انگلیسی)")

    sub.add_parser("brand", help="چاپ هویت رسمی پروژه")

    args = parser.parse_args(argv)
    if args.command == "selfcheck":
        return cmd_selfcheck(args)
    if args.command == "serve":
        from omid.config import OMIDConfig

        config = OMIDConfig.from_env()
        args.host = args.host or config.api_host
        args.port = args.port or config.api_port
        return cmd_serve(args)
    if args.command == "request":
        return cmd_request(args)
    if args.command == "brand":
        return cmd_brand(args)
    parser.error(f"دستور ناشناخته: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
