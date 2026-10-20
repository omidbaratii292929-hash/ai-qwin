"""آزمون هویت برند — حذف/تناقض اطلاعات رسمی شرکت باید شناسایی شود.

مطابق بخش «آزمون هویت برند» در پرامپت مادر:
- مشخصات رسمی در README اصلی
- منبع مرکزی برند (branding.json) با مقادیر صحیح
- داشبورد و API از همان منبع مرکزی
- قالب گزارش‌ها (report_header) صحیح
- مستندات مختلف بدون تناقض
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omid import branding
from omid.errors import BrandingError

REPO_ROOT = Path(__file__).resolve().parent.parent

COMPANY = "هوشمندسازی صنعت امید"
TAGLINE = "ما می‌سازیم تا شما راحت زندگی کنید"
LEAD = "مهندس امید براتی"
COLLABS = ["دکتر کیمیا زهرا براتی", "مهندس محسن بابایی"]


def test_branding_json_valid_and_exact():
    raw = json.loads((REPO_ROOT / "branding.json").read_text(encoding="utf-8"))
    branding.validate(raw)
    assert raw["company_name"] == COMPANY
    assert raw["tagline"] == TAGLINE
    assert raw["lead_designer_and_creator"] == LEAD
    assert raw["collaborators"] == COLLABS
    assert raw["project_name"] == "OMID Industrial AI Agent"


def test_loader_returns_source_of_truth():
    data = branding.load_branding(refresh=True)
    assert data["company_name"] == COMPANY
    assert branding.get("tagline") == TAGLINE


def test_validate_rejects_broken_identity():
    with pytest.raises(BrandingError):
        branding.validate({})
    with pytest.raises(BrandingError):
        branding.validate({"project_name": "x", "company_name": "", "tagline": "t",
                           "lead_designer_and_creator": "l", "collaborators": ["c"]})
    with pytest.raises(BrandingError):
        branding.validate({"project_name": "x", "company_name": "c", "tagline": "t",
                           "lead_designer_and_creator": "l", "collaborators": []})


def test_report_header_contains_identity():
    header = branding.report_header()
    for expected in (COMPANY, TAGLINE, LEAD, *COLLABS):
        assert expected in header


def test_footer_contains_identity():
    footer = branding.footer_text()
    assert COMPANY in footer
    assert TAGLINE in footer


def test_readme_contains_official_identity():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for expected in (COMPANY, TAGLINE, LEAD, *COLLABS, "OMID Industrial AI Agent"):
        assert expected in readme, f"README فاقد اطلاعات رسمی است: {expected}"


@pytest.mark.parametrize(
    "doc",
    ["docs/ARCHITECTURE.md", "docs/SAFETY.md", "SECURITY.md", "CHANGELOG.md", "CONTRIBUTING.md"],
)
def test_docs_contain_company_identity(doc):
    text = (REPO_ROOT / doc).read_text(encoding="utf-8")
    assert COMPANY in text, f"{doc} باید هویت رسمی شرکت را درج کند."


def test_dashboard_static_shows_identity():
    html = (REPO_ROOT / "omid" / "dashboard" / "static" / "index.html").read_text(encoding="utf-8")
    assert COMPANY in html
    assert TAGLINE in html


def test_about_dict_consistent_with_source():
    about = branding.about_dict()
    assert about["company_name"] == COMPANY
    assert about["collaborators"] == COLLABS
    assert "version" in about and about["version"]


def test_no_conflicting_company_name_in_code():
    """هیچ فایل پایتونی نباید نام شرکت را به شکل متفاوت hard-code کند."""
    wrong_variants = ["صنعت هوشمند امید", "هوشمند سازی صنعت امید", "شرکت امید"]
    for py in (REPO_ROOT / "omid").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for wrong in wrong_variants:
            assert wrong not in text, f"نام شرکت در {py} تناقض دارد: {wrong}"
