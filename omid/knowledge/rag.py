"""omid.knowledge.rag — پایگاه دانش: ورود مستندات، قطعه‌بندی، بازیابی با ارجاع.

ویژگی‌ها:
- پشتیبانی از فایل‌های متنی (md, txt, rst, json, yaml, py)؛ فرمت‌های
  پشتیبانی‌نشده **صادقانه** با خطا ثبت می‌شوند (نه وانمود).
- نرمال‌سازی متن فارسی (ی/ک، نیم‌فاصله) برای جست‌وجوی دقیق‌تر.
- امتیازدهی TF-IDF ساده + پاداش عبارت کامل؛ هر نتیجه شامل منبع قابل
  شناسایی (path + chunk_id) و snippet است.
- نمایه روی دیسک (JSON) با امکان بازسازی و حذف کنترل‌شده.

**اصل امنیتی:** محتوای بازیابی‌شده «داده» است نه «دستور». هیچ بخش از متن
مستندات هرگز به‌عنوان فرمان اجرایی یا دستور امنیتی تلقی نمی‌شود
(دفاع در برابر prompt injection از طریق مستندات).

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES: frozenset[str] = frozenset({".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".py"})

_TOKEN = re.compile(r"[\w\u0600-\u06FF]+", re.UNICODE)


class KnowledgeError(RuntimeError):
    """خطای مدیریت دانش (فایل پشتیبانی‌نشده، ناموجود و ...)."""


def normalize(text: str) -> str:
    """نرمال‌سازی فارسی/عربی: ی/ک، نیم‌فاصله، حذف اعراب."""
    text = text.lower().replace("\u200c", " ")
    text = text.replace("ي", "ی").replace("ك", "ک").replace("ة", "ه")
    text = re.sub(r"[\u064B-\u0652]", "", text)  # اعراب
    return text


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text))


@dataclass
class SearchHit:
    doc_id: str
    source_path: str
    chunk_index: int
    score: float
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "source_path": self.source_path,
            "chunk_index": self.chunk_index,
            "score": round(self.score, 4),
            "snippet": self.snippet,
        }


class KnowledgeBase:
    """پایگاه دانش محلی با نمایهٔ واژگانی (بدون وابستگی خارجی)."""

    CHUNK_SIZE = 800
    CHUNK_OVERLAP = 120

    def __init__(self, data_dir: Path) -> None:
        self.index_path = Path(data_dir) / "knowledge_index.json"
        self._docs: dict[str, dict[str, Any]] = {}  # doc_id -> {path, title, chunks[]}
        self._inverted: dict[str, dict[str, list[int]]] = {}  # token -> doc_id -> chunk idxs
        self._lock = threading.RLock()
        self._load()

    # ---------- نمایه ----------
    def _load(self) -> None:
        if not self.index_path.exists():
            return
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
            self._docs = raw.get("docs", {})
            self._inverted = raw.get("inverted", {})
        except (OSError, json.JSONDecodeError):
            self._docs, self._inverted = {}, {}

    def _persist(self) -> None:
        try:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"docs": self._docs, "inverted": self._inverted}
            self.index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # ---------- ورود مستندات ----------
    def ingest_file(self, path: str | Path) -> dict[str, Any]:
        """ورود یک فایل متنی به پایگاه دانش با قطعه‌بندی و نمایه‌سازی."""
        path = Path(path)
        if not path.exists():
            raise KnowledgeError(f"فایل وجود ندارد: {path}")
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise KnowledgeError(
                f"فرمت «{path.suffix or '(بدون پسوند)'}» پشتیبانی نمی‌شود. "
                f"فرمت‌های مجاز: {sorted(SUPPORTED_SUFFIXES)} — (PDF/docx: زیرساخت آماده است، "
                "استخراج‌کننده هنوز پیاده نشده و صادقانه اعلام می‌شود)."
            )
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise KnowledgeError(f"خواندن فایل ناموفق بود: {exc}") from exc

        chunks = self._chunk(text)
        doc_id = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:12]
        title = path.name
        for line in text.splitlines()[:20]:
            if line.startswith("# "):
                title = line[2:].strip()
                break
        with self._lock:
            self.remove(path, _persist=False)
            self._docs[doc_id] = {"path": str(path), "title": title, "chunks": chunks}
            for ci, chunk in enumerate(chunks):
                for tok in set(tokenize(chunk)):
                    self._inverted.setdefault(tok, {}).setdefault(doc_id, []).append(ci)
            self._persist()
        return {"doc_id": doc_id, "path": str(path), "title": title, "chunks": len(chunks)}

    def ingest_directory(self, directory: str | Path, *, max_files: int = 200) -> dict[str, Any]:
        directory = Path(directory)
        if not directory.is_dir():
            raise KnowledgeError(f"مسیر یک پوشهٔ معتبر نیست: {directory}")
        ingested, failed = [], []
        for i, file in enumerate(sorted(p for p in directory.rglob("*") if p.is_file())):
            if i >= max_files:
                break
            if file.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            try:
                ingested.append(self.ingest_file(file))
            except KnowledgeError as exc:
                failed.append({"path": str(file), "error": str(exc)})
        return {"ingested": ingested, "failed": failed, "total": len(ingested)}

    def remove(self, path: str | Path, *, _persist: bool = True) -> bool:
        path_str = str(Path(path))
        with self._lock:
            doc_id = next((d for d, info in self._docs.items() if info["path"] == path_str), None)
            if doc_id is None:
                return False
            self._docs.pop(doc_id, None)
            for tok in list(self._inverted):
                self._inverted[tok].pop(doc_id, None)
                if not self._inverted[tok]:
                    del self._inverted[tok]
            if _persist:
                self._persist()
            return True

    def documents(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {"doc_id": d, "path": info["path"], "title": info["title"], "chunks": len(info["chunks"])}
                for d, info in self._docs.items()
            ]

    def count(self) -> int:
        with self._lock:
            return len(self._docs)

    # ---------- بازیابی ----------
    def search(self, query: str, k: int = 5) -> list[SearchHit]:
        """بازیابی مرتبط‌ترین قطعه‌ها با ارجاع به منبع قابل‌شناسایی."""
        query = (query or "").strip()
        if not query:
            return []
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        with self._lock:
            docs_snapshot = {d: dict(info) for d, info in self._docs.items()}
            inverted_snapshot = {t: dict(v) for t, v in self._inverted.items()}
        if not docs_snapshot:
            return []
        n_docs = len(docs_snapshot)
        scores: dict[tuple[str, int], float] = {}
        q_norm = normalize(query)
        for tok in set(q_tokens):
            postings = inverted_snapshot.get(tok)
            if not postings:
                continue
            idf = math.log(1 + n_docs / max(1, len(postings)))
            for doc_id, chunk_idxs in postings.items():
                for ci in chunk_idxs:
                    scores[(doc_id, ci)] = scores.get((doc_id, ci), 0.0) + idf
        hits: list[SearchHit] = []
        for (doc_id, ci), score in scores.items():
            info = docs_snapshot.get(doc_id)
            if info is None or ci >= len(info["chunks"]):
                continue
            chunk_text = info["chunks"][ci]
            if q_norm and q_norm in normalize(chunk_text):
                score *= 1.5  # پاداش تطابق عبارت کامل
            hits.append(
                SearchHit(
                    doc_id=doc_id,
                    source_path=info["path"],
                    chunk_index=ci,
                    score=score,
                    snippet=self._snippet(chunk_text, q_tokens),
                )
            )
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[: max(1, k)]

    # ---------- داخلی ----------
    @classmethod
    def _chunk(cls, text: str) -> list[str]:
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not text:
            return []
        chunks, start = [], 0
        while start < len(text):
            end = min(start + cls.CHUNK_SIZE, len(text))
            if end < len(text):
                # شکستن در نزدیک‌ترین مرز جمله/خط
                cut = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
                if cut > start + cls.CHUNK_SIZE // 2:
                    end = cut + 1
            chunks.append(text[start:end].strip())
            if end >= len(text):
                break
            start = max(end - cls.CHUNK_OVERLAP, start + 1)
        return [c for c in chunks if c]

    @staticmethod
    def _snippet(chunk: str, q_tokens: list[str], width: int = 220) -> str:
        norm_chunk = normalize(chunk)
        pos = -1
        for tok in q_tokens:
            pos = norm_chunk.find(tok)
            if pos != -1:
                break
        if pos == -1:
            return chunk[:width].strip() + ("…" if len(chunk) > width else "")
        ratio = pos / max(1, len(norm_chunk))
        start = int(ratio * max(0, len(chunk) - width))
        return ("…" if start > 0 else "") + chunk[start : start + width].strip() + "…"
