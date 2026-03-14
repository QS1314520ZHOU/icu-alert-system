"""RAG retrieval service for ICU guideline snippets."""
from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("icu-alert")


@dataclass
class GuidelineChunk:
    package_id: str
    package_name: str
    package_version: str
    doc_id: str
    chunk_id: str
    title: str
    section_title: str
    source: str
    source_url: str
    recommendation: str
    recommendation_grade: str
    category: str
    scope: str
    topic: str
    active: bool
    priority: int
    owner: str
    updated_at: str
    local_ref: str
    tags: list[str]
    text: str


class RagService:
    def __init__(self, config: Any, knowledge_dir: str | None = None) -> None:
        self.config = config
        rag_cfg = (config.yaml_cfg or {}).get("ai_service", {}).get("rag", {})
        engine_rag_cfg = (config.yaml_cfg or {}).get("alert_engine", {}).get("rag", {})
        configured_dir = rag_cfg.get("knowledge_dir") if isinstance(rag_cfg, dict) else None
        base = Path(__file__).resolve().parents[2]
        self.knowledge_dir = Path(knowledge_dir or configured_dir or (base / "knowledge_base"))
        if not self.knowledge_dir.is_absolute():
            self.knowledge_dir = base / self.knowledge_dir

        # backend selection: "embedding" or "tfidf" (default)
        self._backend = str(rag_cfg.get("backend", "tfidf")).strip().lower() if isinstance(rag_cfg, dict) else "tfidf"
        self._embedding_model_name = str(rag_cfg.get("embedding_model", "BAAI/bge-small-zh-v1.5")).strip() if isinstance(rag_cfg, dict) else "BAAI/bge-small-zh-v1.5"

        self._loaded = False
        self._chunks: list[GuidelineChunk] = []
        self._idf: dict[str, float] = {}
        self._vectors: list[dict[str, float]] = []
        self._chunk_map: dict[str, GuidelineChunk] = {}
        self._source_map: dict[str, list[GuidelineChunk]] = {}
        self._documents: dict[str, dict[str, Any]] = {}
        self._package_meta: dict[str, Any] = {}
        self._synonym_map = self._build_synonym_map(engine_rag_cfg if isinstance(engine_rag_cfg, dict) else {})

        # Embedding backend state (lazy-loaded)
        self._embed_model: Any = None
        self._embed_matrix: np.ndarray | None = None  # (N, dim) float32
        self._embed_norms: np.ndarray | None = None    # (N,) precomputed L2 norms

    def reload(self) -> dict[str, Any]:
        self._loaded = False
        self._chunks = []
        self._idf = {}
        self._vectors = []
        self._chunk_map = {}
        self._source_map = {}
        self._documents = {}
        self._package_meta = {}
        self._embed_matrix = None
        self._embed_norms = None
        self._ensure_loaded()
        return self.status()

    def status(self) -> dict[str, Any]:
        self._ensure_loaded()
        active_docs = [d for d in self._documents.values() if d.get("active", True)]
        institutional_docs = [d for d in active_docs if str(d.get("scope") or "") == "institutional"]
        return {
            "package_id": str(self._package_meta.get("package_id") or ""),
            "package_name": str(self._package_meta.get("name") or ""),
            "package_version": str(self._package_meta.get("version") or ""),
            "updated_at": str(self._package_meta.get("updated_at") or ""),
            "owner": str(self._package_meta.get("owner") or ""),
            "document_count": len(active_docs),
            "institutional_document_count": len(institutional_docs),
            "chunk_count": len(self._chunks),
            "knowledge_dir": str(self.knowledge_dir),
        }

    def is_enabled(self) -> bool:
        rag_cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("rag", {})
        if isinstance(rag_cfg, dict):
            return bool(rag_cfg.get("enabled", True))
        return True

    def search(self, query: str, *, top_k: int = 5, tags: list[str] | None = None) -> list[dict[str, Any]]:
        if not self.is_enabled():
            return []
        if not query or not str(query).strip():
            return []
        self._ensure_loaded()
        if not self._chunks:
            return []

        use_embedding = (self._backend == "embedding" and self._embed_matrix is not None)

        # Build query representation
        if use_embedding:
            q_emb = self._encode_query(query)
            if q_emb is None:
                return []
        else:
            q_vec = self._build_query_vec(query)
            if not q_vec:
                return []

        tag_set = {str(t).lower() for t in (tags or []) if t}

        best_by_topic: dict[str, tuple[float, GuidelineChunk]] = {}
        scored: list[tuple[float, GuidelineChunk]] = []
        for idx, chunk in enumerate(self._chunks):
            if not chunk.active:
                continue
            if tag_set:
                chunk_tags = {t.lower() for t in chunk.tags}
                if not (chunk_tags & tag_set):
                    continue

            if use_embedding:
                score = self._cosine_embedding(q_emb, idx)
            else:
                score = self._cosine(q_vec, self._vectors[idx])

            if score <= 0:
                continue
            scope_boost = 0.08 if chunk.scope == "institutional" else 0.0
            boosted_score = score * (1.0 + max(0, chunk.priority) / 1000.0 + scope_boost)
            topic_key = str(chunk.topic or chunk.doc_id or chunk.chunk_id).strip().lower()
            if topic_key:
                existing = best_by_topic.get(topic_key)
                if existing is None or boosted_score > existing[0]:
                    best_by_topic[topic_key] = (boosted_score, chunk)
                continue
            scored.append((boosted_score, chunk))

        scored.extend(best_by_topic.values())

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[: max(1, top_k)]

        return [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "title": c.title,
                "section_title": c.section_title,
                "source": c.source,
                "source_url": c.source_url,
                "recommendation": c.recommendation,
                "recommendation_grade": c.recommendation_grade,
                "category": c.category,
                "scope": c.scope,
                "topic": c.topic,
                "active": c.active,
                "priority": c.priority,
                "owner": c.owner,
                "updated_at": c.updated_at,
                "local_ref": c.local_ref,
                "package_id": c.package_id,
                "package_name": c.package_name,
                "package_version": c.package_version,
                "tags": c.tags,
                "content": c.text,
                "score": round(float(s), 4),
            }
            for s, c in top
        ]

    def get_chunk_bundle(self, chunk_id: str, *, sibling_limit: int = 5) -> dict[str, Any] | None:
        self._ensure_loaded()
        target = self._chunk_map.get(str(chunk_id or "").strip())
        if target is None:
            return None

        siblings = self._source_map.get(self._source_key(target), [])
        related_chunks: list[dict[str, Any]] = []
        for chunk in siblings[: max(1, sibling_limit)]:
            related_chunks.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "doc_id": chunk.doc_id,
                    "title": chunk.title,
                    "section_title": chunk.section_title,
                    "source": chunk.source,
                    "source_url": chunk.source_url,
                    "recommendation": chunk.recommendation,
                    "recommendation_grade": chunk.recommendation_grade,
                    "category": chunk.category,
                    "scope": chunk.scope,
                    "topic": chunk.topic,
                    "active": chunk.active,
                    "priority": chunk.priority,
                    "owner": chunk.owner,
                    "updated_at": chunk.updated_at,
                    "local_ref": chunk.local_ref,
                    "package_id": chunk.package_id,
                    "package_name": chunk.package_name,
                    "package_version": chunk.package_version,
                    "tags": chunk.tags,
                    "content": chunk.text,
                }
            )

        document = self._documents.get(target.doc_id, {})
        return {
            "package_id": target.package_id,
            "package_name": target.package_name,
            "package_version": target.package_version,
            "doc_id": target.doc_id,
            "chunk_id": target.chunk_id,
            "title": target.title,
            "section_title": target.section_title,
            "source": target.source,
            "source_url": target.source_url,
            "recommendation": target.recommendation,
            "recommendation_grade": target.recommendation_grade,
            "category": target.category,
            "scope": target.scope,
            "topic": target.topic,
            "active": target.active,
            "priority": target.priority,
            "owner": target.owner,
            "updated_at": target.updated_at,
            "local_ref": target.local_ref,
            "tags": target.tags,
            "content": target.text,
            "document": document,
            "related_chunks": related_chunks,
        }

    def list_documents(self) -> list[dict[str, Any]]:
        self._ensure_loaded()
        docs = list(self._documents.values())
        docs.sort(key=lambda x: (-int(x.get("priority", 0) or 0), str(x.get("title") or "")))
        return docs

    def get_document(self, doc_id: str, *, include_chunks: bool = True) -> dict[str, Any] | None:
        self._ensure_loaded()
        doc = self._documents.get(str(doc_id or "").strip())
        if doc is None:
            return None
        if not include_chunks:
            return dict(doc)
        chunks = [
            {
                "chunk_id": c.chunk_id,
                "section_title": c.section_title,
                "recommendation": c.recommendation,
                "recommendation_grade": c.recommendation_grade,
                "scope": c.scope,
                "topic": c.topic,
                "tags": c.tags,
                "content": c.text,
                "local_ref": c.local_ref,
            }
            for c in self._chunks
            if c.doc_id == doc["doc_id"]
        ]
        result = dict(doc)
        result["chunks"] = chunks
        return result

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        self._chunks = self._load_chunks()
        if not self._chunks:
            self._idf = {}
            self._vectors = []
            self._chunk_map = {}
            self._source_map = {}
            self._documents = {}
            return

        self._chunk_map = {c.chunk_id: c for c in self._chunks}
        source_map: dict[str, list[GuidelineChunk]] = {}
        for chunk in self._chunks:
            source_map.setdefault(self._source_key(chunk), []).append(chunk)
        self._source_map = source_map
        documents: dict[str, dict[str, Any]] = {}
        for chunk in self._chunks:
            if chunk.doc_id in documents:
                continue
            documents[chunk.doc_id] = {
                "package_id": chunk.package_id,
                "package_name": chunk.package_name,
                "package_version": chunk.package_version,
                "doc_id": chunk.doc_id,
                "title": chunk.title,
                "source": chunk.source,
                "category": chunk.category,
                "scope": chunk.scope,
                "topic": chunk.topic,
                "active": chunk.active,
                "priority": chunk.priority,
                "owner": chunk.owner,
                "updated_at": chunk.updated_at,
                "tags": chunk.tags,
                "local_ref": chunk.local_ref.rsplit("#", 1)[0] if "#" in chunk.local_ref else chunk.local_ref,
            }
        dominant_by_topic: dict[str, dict[str, Any]] = {}
        for doc in documents.values():
            topic_key = str(doc.get("topic") or doc.get("doc_id") or "").strip().lower()
            if not topic_key:
                continue
            current = dominant_by_topic.get(topic_key)
            doc_score = int(doc.get("priority", 0) or 0) + (1000 if str(doc.get("scope") or "") == "institutional" else 0)
            if current is None:
                dominant_by_topic[topic_key] = {"doc_id": doc["doc_id"], "score": doc_score}
                continue
            if doc_score > int(current.get("score", 0) or 0):
                dominant_by_topic[topic_key] = {"doc_id": doc["doc_id"], "score": doc_score}
        for doc in documents.values():
            topic_key = str(doc.get("topic") or doc.get("doc_id") or "").strip().lower()
            dominant = dominant_by_topic.get(topic_key)
            dominant_doc_id = str((dominant or {}).get("doc_id") or "")
            doc["overridden"] = bool(dominant_doc_id and dominant_doc_id != doc["doc_id"])
            doc["overridden_by"] = dominant_doc_id if doc["overridden"] else ""
        self._documents = documents

        doc_count = len(self._chunks)
        df: dict[str, int] = {}
        doc_tokens: list[list[str]] = []
        for chunk in self._chunks:
            tokens = self._tokenize(f"{chunk.title} {chunk.tags} {chunk.text}")
            doc_tokens.append(tokens)
            for t in set(tokens):
                df[t] = df.get(t, 0) + 1

        self._idf = {t: math.log((1 + doc_count) / (1 + n)) + 1.0 for t, n in df.items()}
        self._vectors = [self._tfidf(tokens) for tokens in doc_tokens]

        # Build embedding matrix if backend is 'embedding'
        if self._backend == "embedding":
            self._build_embedding_index()

    def _load_chunks(self) -> list[GuidelineChunk]:
        if not self.knowledge_dir.exists():
            return []

        manifest_path = self.knowledge_dir / "manifest.json"
        if manifest_path.exists():
            chunks = self._load_manifest_package(manifest_path)
            if chunks:
                return chunks

        chunks: list[GuidelineChunk] = []
        for fp in sorted(self.knowledge_dir.glob("**/*")):
            if not fp.is_file():
                continue
            suffix = fp.suffix.lower()
            if suffix == ".json":
                chunks.extend(self._load_json_chunks(fp))
            elif suffix in {".md", ".txt"}:
                chunks.extend(self._load_text_chunks(fp))
        return chunks

    def _load_manifest_package(self, manifest_path: Path) -> list[GuidelineChunk]:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(manifest, dict):
            return []
        self._package_meta = manifest
        docs = manifest.get("documents")
        if not isinstance(docs, list):
            return []

        chunks: list[GuidelineChunk] = []
        for idx, doc in enumerate(docs, start=1):
            if not isinstance(doc, dict):
                continue
            if not bool(doc.get("active", True)):
                continue
            filename = str(doc.get("filename") or "").strip()
            if not filename:
                continue
            fp = (manifest_path.parent / filename).resolve()
            if not fp.exists() or not fp.is_file():
                continue
            suffix = fp.suffix.lower()
            if suffix == ".json":
                chunks.extend(self._load_document_json(fp, manifest, doc, fallback_idx=idx))
            elif suffix in {".md", ".txt"}:
                chunks.extend(self._load_document_text(fp, manifest, doc, fallback_idx=idx))
        return chunks

    def _load_document_json(
        self,
        fp: Path,
        manifest: dict[str, Any],
        doc_meta: dict[str, Any],
        *,
        fallback_idx: int,
    ) -> list[GuidelineChunk]:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, dict):
            return []

        doc_id = str(doc_meta.get("doc_id") or data.get("doc_id") or fp.stem or f"doc_{fallback_idx}")
        title = str(doc_meta.get("title") or data.get("title") or fp.stem)
        source = str(doc_meta.get("source") or data.get("source") or title)
        source_url = str(doc_meta.get("source_url") or data.get("source_url") or data.get("url") or "")
        category = str(doc_meta.get("category") or data.get("category") or "guideline")
        scope = str(doc_meta.get("scope") or data.get("scope") or "external").lower()
        topic = str(doc_meta.get("topic") or data.get("topic") or doc_id)
        active = bool(doc_meta.get("active", data.get("active", True)))
        priority = int(doc_meta.get("priority", data.get("priority", 50)) or 50)
        owner = str(doc_meta.get("owner") or data.get("owner") or manifest.get("owner") or "ICU CDS")
        updated_at = str(doc_meta.get("updated_at") or data.get("updated_at") or manifest.get("updated_at") or "")
        package_id = str(manifest.get("package_id") or "offline_kb")
        package_name = str(manifest.get("name") or "离线知识包")
        package_version = str(manifest.get("version") or "")
        base_tags = [str(x).strip() for x in (doc_meta.get("tags") or data.get("tags") or []) if str(x).strip()]
        local_doc_ref = str(doc_meta.get("local_ref") or data.get("local_ref") or fp.relative_to(self.knowledge_dir).as_posix())

        sections = data.get("sections")
        if not isinstance(sections, list):
            sections = []
        chunks: list[GuidelineChunk] = []
        for section_idx, item in enumerate(sections, start=1):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("content") or "").strip()
            if not text:
                continue
            section_id = str(item.get("id") or f"{doc_id}:{section_idx}")
            section_title = str(item.get("section_title") or item.get("title") or item.get("recommendation") or section_id)
            rec = str(item.get("recommendation") or section_title)
            rec_grade = str(item.get("recommendation_grade") or item.get("grade") or "")
            tags = list(dict.fromkeys(base_tags + [str(t).strip() for t in (item.get("tags") or []) if str(t).strip()]))
            local_ref = str(item.get("local_ref") or f"{local_doc_ref}#{section_id}")
            chunks.append(
                GuidelineChunk(
                    package_id=package_id,
                    package_name=package_name,
                    package_version=package_version,
                    doc_id=doc_id,
                    chunk_id=section_id,
                    title=title,
                    section_title=section_title,
                    source=source,
                    source_url=source_url,
                    recommendation=rec,
                    recommendation_grade=rec_grade,
                    category=category,
                    scope=scope,
                    topic=topic,
                    active=active,
                    priority=priority,
                    owner=owner,
                    updated_at=updated_at,
                    local_ref=local_ref,
                    tags=tags,
                    text=text,
                )
            )
        return chunks

    def _load_document_text(
        self,
        fp: Path,
        manifest: dict[str, Any],
        doc_meta: dict[str, Any],
        *,
        fallback_idx: int,
    ) -> list[GuidelineChunk]:
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            return []
        text = text.strip()
        if not text:
            return []

        package_id = str(manifest.get("package_id") or "offline_kb")
        package_name = str(manifest.get("name") or "离线知识包")
        package_version = str(manifest.get("version") or "")
        doc_id = str(doc_meta.get("doc_id") or fp.stem or f"doc_{fallback_idx}")
        title = str(doc_meta.get("title") or fp.stem)
        source = str(doc_meta.get("source") or title)
        source_url = str(doc_meta.get("source_url") or "")
        category = str(doc_meta.get("category") or "guideline")
        scope = str(doc_meta.get("scope") or "external").lower()
        topic = str(doc_meta.get("topic") or doc_id)
        active = bool(doc_meta.get("active", True))
        priority = int(doc_meta.get("priority", 50) or 50)
        owner = str(doc_meta.get("owner") or manifest.get("owner") or "ICU CDS")
        updated_at = str(doc_meta.get("updated_at") or manifest.get("updated_at") or "")
        tags = [str(x).strip() for x in (doc_meta.get("tags") or []) if str(x).strip()]
        local_doc_ref = str(doc_meta.get("local_ref") or fp.relative_to(self.knowledge_dir).as_posix())

        parts = re.split(r"\n\s*\n", text)
        chunks: list[GuidelineChunk] = []
        for idx, part in enumerate(parts, start=1):
            block = part.strip()
            if len(block) < 30:
                continue
            chunk_id = f"{doc_id}:{idx}"
            chunks.append(
                GuidelineChunk(
                    package_id=package_id,
                    package_name=package_name,
                    package_version=package_version,
                    doc_id=doc_id,
                    chunk_id=chunk_id,
                    title=title,
                    section_title=f"Section {idx}",
                    source=source,
                    source_url=source_url,
                    recommendation=f"Section {idx}",
                    recommendation_grade="",
                    category=category,
                    scope=scope,
                    topic=topic,
                    active=active,
                    priority=priority,
                    owner=owner,
                    updated_at=updated_at,
                    local_ref=f"{local_doc_ref}#{chunk_id}",
                    tags=tags,
                    text=block,
                )
            )
        return chunks

    def _load_json_chunks(self, fp: Path) -> list[GuidelineChunk]:
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return []

        items: list[dict[str, Any]] = []
        if isinstance(data, list):
            items = [x for x in data if isinstance(x, dict)]
        elif isinstance(data, dict):
            raw = data.get("documents")
            if isinstance(raw, list):
                items = [x for x in raw if isinstance(x, dict)]

        chunks: list[GuidelineChunk] = []
        for idx, item in enumerate(items, start=1):
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            title = str(item.get("title") or fp.stem)
            chunk_id = str(item.get("id") or f"{fp.stem}:{idx}")
            source = str(item.get("source") or "")
            source_url = str(item.get("source_url") or item.get("url") or "")
            recommendation = str(item.get("recommendation") or "")
            recommendation_grade = str(item.get("recommendation_grade") or item.get("grade") or "")
            raw_tags = item.get("tags")
            tags = [str(t).strip() for t in raw_tags] if isinstance(raw_tags, list) else []
            chunks.append(
                GuidelineChunk(
                    package_id="legacy",
                    package_name="Legacy Offline Knowledge",
                    package_version="1.0",
                    doc_id=fp.stem,
                    chunk_id=chunk_id,
                    title=title,
                    section_title=recommendation or title,
                    source=source,
                    source_url=source_url,
                    recommendation=recommendation,
                    recommendation_grade=recommendation_grade,
                    category="guideline",
                    scope="external",
                    topic=fp.stem,
                    active=True,
                    priority=50,
                    owner="ICU CDS",
                    updated_at="",
                    local_ref=f"{fp.relative_to(self.knowledge_dir).as_posix()}#{chunk_id}",
                    tags=[t for t in tags if t],
                    text=text,
                )
            )
        return chunks

    def _load_text_chunks(self, fp: Path) -> list[GuidelineChunk]:
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            return []

        text = text.strip()
        if not text:
            return []

        parts = re.split(r"\n\s*\n", text)
        chunks: list[GuidelineChunk] = []
        for idx, part in enumerate(parts, start=1):
            block = part.strip()
            if len(block) < 30:
                continue
            chunks.append(
                GuidelineChunk(
                    package_id="legacy",
                    package_name="Legacy Offline Knowledge",
                    package_version="1.0",
                    doc_id=fp.stem,
                    chunk_id=f"{fp.stem}:{idx}",
                    title=fp.stem,
                    section_title=f"Section {idx}",
                    source=fp.name,
                    source_url="",
                    recommendation="",
                    recommendation_grade="",
                    category="guideline",
                    scope="external",
                    topic=fp.stem,
                    active=True,
                    priority=50,
                    owner="ICU CDS",
                    updated_at="",
                    local_ref=f"{fp.relative_to(self.knowledge_dir).as_posix()}#{fp.stem}:{idx}",
                    tags=[],
                    text=block,
                )
            )
        return chunks

    def _tokenize(self, text: str) -> list[str]:
        if not text:
            return []
        lowered = str(text).lower()
        raw = re.findall(r"[a-z0-9_\-]+|[\u4e00-\u9fff]{1,4}", lowered)
        tokens: list[str] = []
        for tk in raw:
            t = tk.strip()
            if not t:
                continue
            tokens.append(t)
            if re.fullmatch(r"[\u4e00-\u9fff]{2,4}", t):
                for i in range(len(t) - 1):
                    tokens.append(t[i : i + 2])
        return self._expand_synonyms(tokens)

    def _build_synonym_map(self, rag_cfg: dict[str, Any]) -> dict[str, list[str]]:
        raw = rag_cfg.get("synonyms", {}) if isinstance(rag_cfg, dict) else {}
        if not isinstance(raw, dict):
            return {}
        out: dict[str, list[str]] = {}
        for key, values in raw.items():
            base = str(key or "").strip().lower()
            if not base:
                continue
            syns = [str(v).strip().lower() for v in (values or []) if str(v).strip()]
            if syns:
                out[base] = syns
        return out

    def _expand_synonyms(self, tokens: list[str]) -> list[str]:
        if not tokens or not self._synonym_map:
            return tokens
        expanded = list(tokens)
        token_set = set(tokens)
        for token in list(token_set):
            synonyms = self._synonym_map.get(token, [])
            for synonym in synonyms:
                if synonym not in token_set:
                    expanded.append(synonym)
                    token_set.add(synonym)
                if re.fullmatch(r"[\u4e00-\u9fff]{2,6}", synonym):
                    for i in range(len(synonym) - 1):
                        bg = synonym[i : i + 2]
                        if bg not in token_set:
                            expanded.append(bg)
                            token_set.add(bg)
        return expanded

    def _tfidf(self, tokens: list[str]) -> dict[str, float]:
        if not tokens:
            return {}
        tf: dict[str, int] = {}
        for t in tokens:
            tf[t] = tf.get(t, 0) + 1
        total = float(len(tokens))
        vec: dict[str, float] = {}
        for t, n in tf.items():
            idf = self._idf.get(t)
            if idf is None:
                continue
            vec[t] = (n / total) * idf
        return vec

    def _build_query_vec(self, query: str) -> dict[str, float]:
        tokens = self._tokenize(query)
        return self._tfidf(tokens)

    def _source_key(self, chunk: GuidelineChunk) -> str:
        return f"{chunk.source}::{chunk.title}".strip().lower()

    def _cosine(self, a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        common = set(a.keys()) & set(b.keys())
        if not common:
            return 0.0
        dot = sum(a[k] * b[k] for k in common)
        na = math.sqrt(sum(v * v for v in a.values()))
        nb = math.sqrt(sum(v * v for v in b.values()))
        if na <= 1e-12 or nb <= 1e-12:
            return 0.0
        return dot / (na * nb)

    # ------------------------------------------------------------------
    # Embedding backend helpers
    # ------------------------------------------------------------------
    def _get_embed_model(self):
        """Lazy-load the sentence-transformers model."""
        if self._embed_model is not None:
            return self._embed_model
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading embedding model: {self._embedding_model_name}")
            self._embed_model = SentenceTransformer(self._embedding_model_name)
            logger.info("Embedding model loaded successfully")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed; falling back to tfidf. "
                "Install with: pip install sentence-transformers"
            )
            self._backend = "tfidf"
            self._embed_model = None
        except Exception as e:
            logger.warning(f"Failed to load embedding model: {e}; falling back to tfidf")
            self._backend = "tfidf"
            self._embed_model = None
        return self._embed_model

    def _build_embedding_index(self) -> None:
        """Encode all chunks into a dense numpy matrix."""
        model = self._get_embed_model()
        if model is None:
            return
        texts = [f"{c.title} {c.section_title} {c.text}" for c in self._chunks]
        if not texts:
            return
        try:
            embeddings = model.encode(texts, show_progress_bar=False, normalize_embeddings=True)
            self._embed_matrix = np.asarray(embeddings, dtype=np.float32)
            self._embed_norms = np.linalg.norm(self._embed_matrix, axis=1)
            logger.info(f"Built embedding index: {self._embed_matrix.shape}")
        except Exception as e:
            logger.warning(f"Embedding encode failed: {e}; falling back to tfidf")
            self._backend = "tfidf"
            self._embed_matrix = None
            self._embed_norms = None

    def _encode_query(self, query: str) -> np.ndarray | None:
        """Encode a single query string into an embedding vector."""
        model = self._get_embed_model()
        if model is None:
            return None
        try:
            vec = model.encode([query], show_progress_bar=False, normalize_embeddings=True)
            return np.asarray(vec[0], dtype=np.float32)
        except Exception:
            return None

    def _cosine_embedding(self, q_vec: np.ndarray, idx: int) -> float:
        """Compute cosine similarity between query vector and chunk at idx."""
        if self._embed_matrix is None:
            return 0.0
        chunk_vec = self._embed_matrix[idx]
        dot = float(np.dot(q_vec, chunk_vec))
        q_norm = float(np.linalg.norm(q_vec))
        c_norm = float(self._embed_norms[idx]) if self._embed_norms is not None else float(np.linalg.norm(chunk_vec))
        if q_norm <= 1e-12 or c_norm <= 1e-12:
            return 0.0
        return dot / (q_norm * c_norm)
