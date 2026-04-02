"""
Vector Memory — Long-term semantic codebase search with ChromaDB.

Indexes repository files into a persistent vector database.
Enables the agent to retrieve relevant context when editing any file.

Example: When editing auth.py, the agent retrieves:
  - models.py (has User model)
  - config.py (has JWT settings)
  - middleware.py (has auth decorator)

Falls back gracefully to keyword search when ChromaDB is unavailable.

Usage:
    from core.vector_memory import VectorMemory

    vm = VectorMemory(repo_path="/path/to/repo")
    vm.index_repository()   # Once per project

    results = vm.search("JWT authentication token validation", top_k=5)
    for r in results:
        print(r.file_path, r.relevance_score, r.snippet[:100])
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CHROMA_AVAILABLE = False
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _CHROMA_AVAILABLE = True
except ImportError:
    logger.debug("[VectorMemory] chromadb not installed — using keyword fallback")


@dataclass
class SearchResult:
    file_path: str
    snippet: str
    relevance_score: float     # 0.0–1.0 (1.0 = most relevant)
    source: str                # "vector" | "keyword"


class VectorMemory:
    """
    Semantic codebase search for long-term agent memory.

    Indexes all .py files in a repository and enables semantic retrieval
    when the agent needs context about related files.

    Falls back to keyword-based search when ChromaDB is unavailable.
    """

    # File types to index
    INDEXED_EXTENSIONS = {".py", ".js", ".ts", ".md", ".yaml", ".toml", ".json"}
    MAX_CHUNK_SIZE = 1500      # chars per chunk
    CHUNK_OVERLAP  = 200       # chars of overlap between chunks

    def __init__(
        self,
        repo_path: Optional[str] = None,
        persist_dir: Optional[str] = None,
        collection_name: str = "codebase",
    ):
        self.repo_path       = Path(repo_path or os.getcwd())
        self.persist_dir     = persist_dir or os.getenv("CHROMA_PERSIST_DIR", ".chroma")
        self.collection_name = collection_name
        self._collection     = None
        self._keyword_index: dict[str, str] = {}   # fallback
        self._is_indexed     = False

        if _CHROMA_AVAILABLE:
            self._init_chroma()

    # ─── Public API ───────────────────────────────────────────────────────────

    def index_repository(self, force: bool = False) -> int:
        """
        Index all source files in the repository.

        Args:
            force: Re-index even if already indexed

        Returns:
            Number of files indexed
        """
        if self._is_indexed and not force:
            logger.debug("[VectorMemory] Already indexed. Use force=True to re-index.")
            return 0

        files = self._discover_files()
        logger.info(f"[VectorMemory] Indexing {len(files)} files...")

        indexed = 0
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
                rel_path = str(file_path.relative_to(self.repo_path))

                if _CHROMA_AVAILABLE and self._collection is not None:
                    self._index_chroma(rel_path, content)
                else:
                    self._keyword_index[rel_path] = content

                indexed += 1
            except Exception as e:
                logger.debug(f"[VectorMemory] Skipped {file_path}: {e}")

        self._is_indexed = True
        source = "ChromaDB" if _CHROMA_AVAILABLE else "keyword index"
        logger.info(f"[VectorMemory] Indexed {indexed} files via {source}")
        return indexed

    def search(
        self,
        query: str,
        top_k: int = 5,
        file_filter: Optional[str] = None,
    ) -> list[SearchResult]:
        """
        Search the indexed codebase for relevant context.

        Args:
            query:       Natural language or code snippet to search
            top_k:       Max results to return
            file_filter: Optional substring to filter file paths

        Returns:
            List of SearchResult ordered by relevance
        """
        if not self._is_indexed:
            logger.warning("[VectorMemory] Not indexed yet. Call index_repository() first.")
            return []

        if _CHROMA_AVAILABLE and self._collection is not None:
            return self._search_chroma(query, top_k, file_filter)
        return self._search_keyword(query, top_k, file_filter)

    def get_context_for_file(self, file_path: str, top_k: int = 3) -> list[SearchResult]:
        """
        Get related files when editing a specific file.
        Uses the file's content as the search query.
        """
        try:
            full_path = self.repo_path / file_path
            content = full_path.read_text(encoding="utf-8", errors="replace")
            # Use first 500 chars as the search query
            query = content[:500]
            results = self.search(query, top_k=top_k + 1)
            # Exclude the file itself
            return [r for r in results if r.file_path != file_path][:top_k]
        except Exception as e:
            logger.debug(f"[VectorMemory] get_context_for_file failed: {e}")
            return []

    def clear(self) -> None:
        """Clear the vector index."""
        self._keyword_index.clear()
        self._is_indexed = False
        if _CHROMA_AVAILABLE and self._collection is not None:
            try:
                self._collection.delete(where={"source": {"$ne": ""}})
            except Exception:
                pass
        logger.info("[VectorMemory] Index cleared")

    # ─── ChromaDB Backend ──────────────────────────────────────────────────────

    def _init_chroma(self) -> None:
        try:
            client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.debug(f"[VectorMemory] ChromaDB initialized at {self.persist_dir}")
        except Exception as e:
            logger.warning(f"[VectorMemory] ChromaDB init failed: {e} — using keyword fallback")
            self._collection = None

    def _index_chroma(self, rel_path: str, content: str) -> None:
        chunks = self._chunk(content)
        for i, chunk in enumerate(chunks):
            doc_id = hashlib.md5(f"{rel_path}:{i}".encode()).hexdigest()
            self._collection.upsert(
                ids=[doc_id],
                documents=[chunk],
                metadatas=[{"file_path": rel_path, "chunk": i}],
            )

    def _search_chroma(self, query: str, top_k: int, file_filter: Optional[str]) -> list[SearchResult]:
        try:
            where = None
            if file_filter:
                where = {"file_path": {"$contains": file_filter}}
            res = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where,
            )
            results = []
            for doc, meta, dist in zip(
                res["documents"][0], res["metadatas"][0], res["distances"][0]
            ):
                results.append(SearchResult(
                    file_path=meta["file_path"],
                    snippet=doc[:300],
                    relevance_score=round(1.0 - float(dist), 3),
                    source="vector",
                ))
            return results
        except Exception as e:
            logger.warning(f"[VectorMemory] ChromaDB search failed: {e}")
            return self._search_keyword(query, top_k, file_filter)

    # ─── Keyword Fallback ─────────────────────────────────────────────────────

    def _search_keyword(self, query: str, top_k: int, file_filter: Optional[str]) -> list[SearchResult]:
        """Simple keyword overlap search when ChromaDB is unavailable."""
        query_words = set(query.lower().split())
        results = []
        for path, content in self._keyword_index.items():
            if file_filter and file_filter not in path:
                continue
            content_words = set(content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                score = min(overlap / max(len(query_words), 1), 1.0)
                # Find best snippet
                snippet = self._find_snippet(content, query_words)
                results.append(SearchResult(
                    file_path=path,
                    snippet=snippet,
                    relevance_score=round(score, 3),
                    source="keyword",
                ))
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:top_k]

    def _find_snippet(self, content: str, query_words: set) -> str:
        """Find the most relevant snippet in content."""
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if any(w in line.lower() for w in query_words):
                start = max(0, i - 1)
                end   = min(len(lines), i + 3)
                return "\n".join(lines[start:end])[:300]
        return content[:200]

    def _discover_files(self) -> list[Path]:
        """Discover indexable files in the repo."""
        files = []
        ignore_dirs = {".git", "__pycache__", ".venv", "venv", "node_modules",
                       ".chroma", ".mypy_cache", ".pytest_cache", "dist"}
        for path in self.repo_path.rglob("*"):
            if any(d in path.parts for d in ignore_dirs):
                continue
            if path.suffix in self.INDEXED_EXTENSIONS and path.is_file():
                if path.stat().st_size < 200_000:  # Skip files > 200KB
                    files.append(path)
        return files

    def _chunk(self, content: str) -> list[str]:
        """Split content into overlapping chunks for indexing."""
        chunks = []
        start  = 0
        while start < len(content):
            end = start + self.MAX_CHUNK_SIZE
            chunks.append(content[start:end])
            start = end - self.CHUNK_OVERLAP
        return chunks or [content]
