# Unified Architecture Design: book-ingestion + agentic_pipeline

**Date:** 2025-01-30
**Status:** Draft
**Projects:**
- `/Users/taylorstephens/_Projects/book-ingestion-python`
- `/Users/taylorstephens/_Projects/book-mcp-server/agentic_pipeline`

---

## Executive Summary

This design unifies `book-ingestion-python` (processing engine) and `agentic_pipeline` (orchestration layer) into a cohesive system where:

1. **book-ingestion** becomes an importable Python library with clean interfaces
2. **agentic_pipeline** imports it directly (no more subprocess calls)
3. LLM capabilities flow **down** from agentic to book-ingestion
4. Rich quality signals flow **up** from book-ingestion to agentic

---

## Problem Statement

### Current State

```
agentic_pipeline ──subprocess──► book-ingestion-python
       │                                    │
       │  (throws away)                     │
       ◄────────────────────────────────────┘
              rich quality signals
```

**Issues:**
- Subprocess boundary loses all rich data (confidence, quality scores, warnings)
- Duplicate state tracking in both projects
- LLM intelligence can't help when heuristics fail
- No feedback loop between orchestration decisions and processing quality

### Goal State

```
agentic_pipeline ──direct import──► book-ingestion
       │                                    │
       │  LLMFallbackPort                   │
       ▼                                    │
   LLM capabilities                         │
       │                                    │
       ◄────────────────────────────────────┘
         PipelineResult (confidence, quality, warnings)
```

---

## Expert Recommendations Applied

### From "Clean Architecture with Python" (Packt 2025)

1. **Dependency Inversion Principle**: High-level modules depend on abstractions
2. **Adapter Pattern**: Bridge between layers without tight coupling
3. **Repository Pattern**: Abstract data access behind interfaces
4. **Composition Root**: Wire dependencies in one place

### From "Generative AI with LangChain" (2nd Edition)

1. **Lazy Loading**: Heavy dependencies loaded only when needed
2. **Modular Packages**: Split into core + optional extras
3. **Independent Release Cycles**: Stable core, experimental features separate

---

## Architecture Design

### Package Structure

```
book_ingestion/
├── __init__.py              # Public API with lazy loading
├── py.typed                 # PEP 561 marker for type hints
├── bootstrap.py             # Composition root (wiring)
│
├── ports/                   # Interfaces (Protocol classes)
│   ├── __init__.py
│   ├── llm_fallback.py      # LLMFallbackPort
│   └── repository.py        # BookRepository
│
├── domain/                  # Core entities (no dependencies)
│   ├── __init__.py
│   ├── book.py              # Book, Chapter dataclasses
│   └── result.py            # PipelineResult, QualityReport
│
├── adapters/                # Interface implementations
│   ├── __init__.py
│   ├── sqlite_repository.py # BookRepository → SQLite
│   └── file_writer.py       # Markdown output
│
├── processors/              # Business logic (existing)
│   ├── __init__.py
│   ├── enhanced_pipeline.py
│   ├── chapter_detector.py
│   ├── profiler.py
│   └── ...
│
├── converters/              # PDF/EPUB (optional dependency)
│   ├── __init__.py
│   ├── pdf_converter.py
│   └── epub_converter.py
│
└── cli.py                   # CLI entry point
```

---

## Key Components

### 1. Ports (Interfaces)

Using `typing.Protocol` for structural subtyping - implementers don't need to inherit.

```python
# book_ingestion/ports/llm_fallback.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class LLMFallbackPort(Protocol):
    """
    Protocol for LLM fallback when heuristics fail.

    Implement this in your orchestration layer to provide
    LLM capabilities to the processing pipeline.
    """

    def detect_chapters(self, text: str) -> list[dict]:
        """
        Use LLM to detect chapter boundaries.

        Called when heuristic detection has low confidence (<0.5).

        Args:
            text: Book text (may be truncated to ~40k chars)

        Returns:
            List of dicts with keys: title, start_position, confidence
        """
        ...

    def extract_metadata(self, frontmatter: str) -> dict:
        """
        Use LLM to extract metadata from messy frontmatter.

        Args:
            frontmatter: First ~2000 chars of book

        Returns:
            Dict with keys: title, author, publisher, year
        """
        ...
```

```python
# book_ingestion/ports/repository.py
from typing import Protocol, Optional

@runtime_checkable
class BookRepository(Protocol):
    """Protocol for book storage."""

    def save_book(self, book_id: str, metadata: dict) -> None: ...
    def save_chapters(self, book_id: str, chapters: list[dict]) -> None: ...
    def get_book(self, book_id: str) -> Optional[dict]: ...
    def find_by_hash(self, content_hash: str) -> Optional[dict]: ...
```

### 2. Bootstrap (Composition Root)

```python
# book_ingestion/bootstrap.py
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from book_ingestion.processors.enhanced_pipeline import (
    EnhancedPipeline,
    ProcessingMode,
    PipelineResult,
)
from book_ingestion.ports import LLMFallbackPort


@dataclass
class BookIngestionApp:
    """
    Application container with wired dependencies.

    Usage:
        app = BookIngestionApp.create(
            db_path="./library.db",
            llm_fallback=my_llm_adapter,
        )
        result = app.process("path/to/book.pdf")
    """

    pipeline: EnhancedPipeline
    db_path: Path
    llm_fallback: Optional[LLMFallbackPort] = None

    @classmethod
    def create(
        cls,
        db_path: Path | str = Path("./data/library.db"),
        mode: ProcessingMode = ProcessingMode.STANDARD,
        llm_fallback: Optional[LLMFallbackPort] = None,
        enable_semantic: bool = True,
    ) -> "BookIngestionApp":
        """Factory method - create configured application."""
        db_path = Path(db_path)

        pipeline = EnhancedPipeline(
            mode=mode,
            enable_semantic=enable_semantic,
        )

        return cls(
            pipeline=pipeline,
            db_path=db_path,
            llm_fallback=llm_fallback,
        )

    def process(self, book_path: str | Path) -> PipelineResult:
        """Process a book file end-to-end."""
        book_path = Path(book_path)
        text, metadata = self._convert_file(book_path)

        import hashlib
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        book_id = f"{book_path.stem}-{content_hash}"

        result = self.pipeline.process_book(
            text=text,
            book_id=book_id,
            metadata=metadata,
        )

        # Try LLM fallback if low confidence
        if result.detection_confidence < 0.5 and self.llm_fallback:
            result = self._try_llm_fallback(text, book_id, result)

        return result
```

### 3. Top-Level API with Lazy Loading

```python
# book_ingestion/__init__.py
"""
Book Ingestion Library

Process PDF/EPUB books into structured, searchable chapters.
"""

__version__ = "1.0.0"

# Core exports (always available, lightweight)
from book_ingestion.processors.enhanced_pipeline import (
    EnhancedPipeline,
    PipelineResult,
    ProcessingMode,
    ChapterDetectionResult,
    process_book_enhanced,
)

from book_ingestion.processors.profiler import (
    DataProfiler,
    BookProfile,
    QualityReport,
)

from book_ingestion.processors.chapter_validator import (
    ChapterValidator,
    ValidationResult,
)

# Lazy imports for heavy dependencies
_lazy_imports = {
    "PDFConverter": "book_ingestion.converters.pdf_converter",
    "EPUBConverter": "book_ingestion.converters.epub_converter",
    "SemanticChunker": "book_ingestion.processors.semantic_chunker",
    "BookIngestionApp": "book_ingestion.bootstrap",
}

def __getattr__(name: str):
    """Lazy load optional components."""
    if name in _lazy_imports:
        import importlib
        module = importlib.import_module(_lazy_imports[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "__version__",
    "EnhancedPipeline",
    "PipelineResult",
    "ProcessingMode",
    "ChapterDetectionResult",
    "process_book_enhanced",
    "DataProfiler",
    "BookProfile",
    "QualityReport",
    "ChapterValidator",
    "ValidationResult",
    "PDFConverter",
    "EPUBConverter",
    "SemanticChunker",
    "BookIngestionApp",
]
```

---

## Package Configuration

```toml
# pyproject.toml

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "book-ingestion"
version = "1.0.0"
description = "Book processing pipeline with chapter detection and quality validation"
readme = "README.md"
requires-python = ">=3.11"

# Core dependencies only - lightweight
dependencies = [
    "click>=8.0",
    "rich>=13.0",
    "tqdm>=4.0",
]

[project.optional-dependencies]
converters = [
    "pymupdf>=1.23",
    "ebooklib>=0.18",
    "beautifulsoup4>=4.12",
    "lxml>=4.9",
    "python-magic>=0.4",
]
nlp = [
    "nltk>=3.8",
    "spacy>=3.0",
]
embeddings = [
    "torch>=2.0",
    "sentence-transformers>=2.2",
]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]
all = [
    "book-ingestion[converters,nlp,embeddings,dev]",
]

[project.scripts]
book-ingestion = "book_ingestion.cli:main"

[tool.hatch.build.targets.wheel]
packages = ["book_ingestion"]
```

---

## Integration from agentic_pipeline

### LLM Fallback Adapter

```python
# agentic_pipeline/adapters/llm_fallback_adapter.py
from pathlib import Path
from agentic_pipeline.agents.classifier import ClassifierAgent


class LLMFallbackAdapter:
    """
    Implements LLMFallbackPort protocol using ClassifierAgent.

    No inheritance needed - structural typing via Protocol.
    """

    def __init__(self, db_path: Path):
        self.classifier = ClassifierAgent(db_path)

    def detect_chapters(self, text: str) -> list[dict]:
        """Use LLM to detect chapter boundaries."""
        prompt = f"""Analyze this book text and identify chapter boundaries.

Return a JSON list of chapters with:
- title: The chapter title
- start_position: Approximate character position
- confidence: Your confidence (0.0-1.0)

Text:
{text[:40000]}
"""
        result = self.classifier.classify(prompt, content_hash="")
        return self._parse_chapter_response(result)

    def extract_metadata(self, frontmatter: str) -> dict:
        """Use LLM to extract metadata."""
        prompt = f"""Extract book metadata from this frontmatter.

Return JSON with: title, author, publisher, year

Frontmatter:
{frontmatter[:2000]}
"""
        result = self.classifier.classify(prompt, content_hash="")
        return self._parse_metadata_response(result)
```

### Updated Orchestrator

```python
# agentic_pipeline/orchestrator/orchestrator.py
from book_ingestion import BookIngestionApp, PipelineResult, ProcessingMode
from agentic_pipeline.adapters import LLMFallbackAdapter


class Orchestrator:
    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.repo = PipelineRepository(config.db_path)

        # Create LLM fallback adapter
        llm_fallback = LLMFallbackAdapter(config.db_path)

        # Create book ingestion app with LLM fallback
        self.book_app = BookIngestionApp.create(
            db_path=config.db_path,
            mode=ProcessingMode.STANDARD,
            llm_fallback=llm_fallback,
        )

    def _run_processing(self, book_path: str) -> PipelineResult:
        """Direct import instead of subprocess!"""
        return self.book_app.process(book_path)

    def _process_book(self, pipeline_id: str, book_path: str, content_hash: str) -> dict:
        """Process with access to rich data."""

        self._transition(pipeline_id, PipelineState.PROCESSING)
        result = self._run_processing(book_path)

        # NOW WE HAVE RICH DATA:
        self.repo.update_quality_score(pipeline_id, result.quality_report.quality_score)
        self.repo.update_detection_info(
            pipeline_id,
            method=result.detection_method,
            confidence=result.detection_confidence,
        )

        # Use actual validation result
        if not result.is_valid:
            self._transition(pipeline_id, PipelineState.NEEDS_RETRY)
            return {"state": "needs_retry", "reason": result.warnings}

        # Use detection confidence for approval routing
        if result.needs_review:
            self._transition(pipeline_id, PipelineState.PENDING_APPROVAL)
            return {
                "state": "pending_approval",
                "confidence": result.detection_confidence,
                "warnings": result.warnings,
                "recommendations": result.recommendations,
            }

        # Auto-approve high confidence
        self._transition(pipeline_id, PipelineState.APPROVED)
        return {
            "state": "complete",
            "quality_score": result.quality_report.quality_score,
            "detection_confidence": result.detection_confidence,
        }
```

---

## Migration Plan

### Phase 1: Prepare book-ingestion (Non-Breaking)

| Step | Action | Risk |
|------|--------|------|
| 1.1 | Rename `src/` → `book_ingestion/` | Low |
| 1.2 | Create `pyproject.toml` | Low |
| 1.3 | Create `__init__.py` with lazy loading | Low |
| 1.4 | Create `ports/` directory with Protocol classes | Low |
| 1.5 | Create `bootstrap.py` composition root | Low |
| 1.6 | Update relative imports | Medium |
| 1.7 | Install in development mode, verify CLI works | Low |

### Phase 2: Wire Up agentic_pipeline

| Step | Action | Risk |
|------|--------|------|
| 2.1 | Add book-ingestion as dependency | Low |
| 2.2 | Create `LLMFallbackAdapter` | Low |
| 2.3 | Update Orchestrator to use direct imports | Medium |

### Phase 3: Remove Subprocess Calls

| Step | Action | Risk |
|------|--------|------|
| 3.1 | Delete subprocess processing code | Low (after testing) |
| 3.2 | Remove `book_ingestion_path` from config | Low |

### Phase 4: Testing

| Step | Action | Risk |
|------|--------|------|
| 4.1 | Unit test adapter implements Protocol | None |
| 4.2 | Integration test direct import processing | None |
| 4.3 | End-to-end test with sample book | None |

---

## Data Flow

### Before (Subprocess)

```
Orchestrator                    book-ingestion CLI
     │                                │
     │ subprocess.run()               │
     ├───────────────────────────────►│
     │                                │ process book
     │                                │
     │ exit code only                 │
     │◄───────────────────────────────┤
     │                                │
     ▼                                │
  (no quality data)                   │
```

### After (Direct Import)

```
Orchestrator                    BookIngestionApp
     │                                │
     │ app.process(book_path)         │
     ├───────────────────────────────►│
     │                                │
     │                                │ LLMFallbackPort?
     │ llm_fallback.detect_chapters() │◄────────────────┐
     │◄───────────────────────────────┤                 │
     │                                │                 │
     │ PipelineResult                 │                 │
     │  - chapters                    │                 │
     │  - detection_confidence        │                 │
     │  - quality_report              │                 │
     │  - warnings                    │                 │
     │  - recommendations             │                 │
     │◄───────────────────────────────┤                 │
     │                                │                 │
     ▼                                                  │
  Approval routing based on                             │
  actual confidence + quality                           │
     │                                                  │
     └──────────────────────────────────────────────────┘
           (LLM capabilities flow down)
```

---

## Expert Review: Additional Recommendations

### From "Clean Architecture with Python" - Error Handling at Boundaries

**Key Principle:** Keep controllers interface-agnostic. Delegate error formatting to interface-specific presenters.

```python
# book_ingestion/result.py - Framework-agnostic operation result

from dataclasses import dataclass
from typing import Generic, TypeVar, Optional
from enum import Enum

T = TypeVar("T")

class ErrorCode(Enum):
    VALIDATION_ERROR = "validation_error"
    PROCESSING_ERROR = "processing_error"
    LLM_FALLBACK_FAILED = "llm_fallback_failed"
    FILE_NOT_FOUND = "file_not_found"

@dataclass
class OperationError:
    code: ErrorCode
    message: str
    details: Optional[dict] = None

@dataclass
class OperationResult(Generic[T]):
    """Framework-agnostic result container."""
    value: Optional[T] = None
    error: Optional[OperationError] = None

    @property
    def is_success(self) -> bool:
        return self.error is None

    @classmethod
    def succeed(cls, value: T) -> "OperationResult[T]":
        return cls(value=value)

    @classmethod
    def fail(cls, code: ErrorCode, message: str) -> "OperationResult[T]":
        return cls(error=OperationError(code=code, message=message))
```

**In Orchestrator - Let each layer handle errors appropriately:**

```python
def _process_book(self, pipeline_id: str, book_path: str) -> OperationResult:
    try:
        result = self.book_app.process(book_path)
        return OperationResult.succeed(result)
    except FileNotFoundError as e:
        return OperationResult.fail(ErrorCode.FILE_NOT_FOUND, str(e))
    except ValidationError as e:
        return OperationResult.fail(ErrorCode.VALIDATION_ERROR, str(e))
    # Let interface layer format these for CLI/API appropriately
```

---

### From "Clean Architecture with Python" - Observability Strategy

**Key Principle:** Clean Architecture's layers create natural observation points. Don't let framework logging leak into core layers.

```python
# book_ingestion/ports/logger.py

from typing import Protocol

class PipelineLogger(Protocol):
    """Protocol for logging across layers."""

    def processing_started(self, book_id: str, path: str) -> None: ...
    def chapter_detected(self, book_id: str, method: str, confidence: float) -> None: ...
    def llm_fallback_triggered(self, book_id: str, reason: str) -> None: ...
    def processing_complete(self, book_id: str, quality_score: float) -> None: ...
    def error(self, book_id: str, error_type: str, message: str) -> None: ...
```

**Structured Logging Implementation:**

```python
# agentic_pipeline/adapters/structured_logger.py

import logging
import json
from uuid import uuid4
from contextvars import ContextVar

# Thread-safe trace ID
trace_id: ContextVar[str] = ContextVar("trace_id", default="")

class StructuredLogger:
    """Structured logging that maintains Clean Architecture boundaries."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _log(self, level: str, event: str, **kwargs):
        """Emit structured log entry with trace ID."""
        entry = {
            "event": event,
            "trace_id": trace_id.get(),
            **kwargs
        }
        getattr(self.logger, level)(json.dumps(entry))

    def processing_started(self, book_id: str, path: str) -> None:
        self._log("info", "processing_started", book_id=book_id, path=path)

    def chapter_detected(self, book_id: str, method: str, confidence: float) -> None:
        self._log("info", "chapter_detected",
                  book_id=book_id, method=method, confidence=confidence)

    def llm_fallback_triggered(self, book_id: str, reason: str) -> None:
        self._log("info", "llm_fallback_triggered", book_id=book_id, reason=reason)
```

**Trace ID Middleware:**

```python
# Assign trace ID at system boundary
def with_trace_id():
    trace_id.set(str(uuid4())[:8])
```

---

### From "Generative AI with LangChain" - LLM Observability Metrics

**Key Metrics for LLM-Enhanced Processing:**

| Metric | Purpose | Layer |
|--------|---------|-------|
| Time to First Token (TTFT) | LLM responsiveness | agentic_pipeline |
| Token usage per request | Cost tracking | agentic_pipeline |
| LLM fallback trigger rate | Heuristic effectiveness | book_ingestion |
| Detection confidence distribution | Model quality | book_ingestion |
| Hallucination detection rate | Output quality | agentic_pipeline |

**Implement Token Tracking:**

```python
# agentic_pipeline/adapters/llm_fallback_adapter.py

class LLMFallbackAdapter:
    def __init__(self, db_path: Path, logger: PipelineLogger):
        self.classifier = ClassifierAgent(db_path)
        self.logger = logger
        self.token_counter = TokenCounter()  # Track usage

    def detect_chapters(self, text: str) -> list[dict]:
        start_time = time.monotonic()

        result = self.classifier.classify(...)

        # Track LLM-specific metrics
        self.token_counter.add(
            input_tokens=self._count_tokens(text[:40000]),
            output_tokens=self._count_tokens(str(result)),
        )

        self.logger.llm_call_complete(
            latency_ms=(time.monotonic() - start_time) * 1000,
            tokens_used=self.token_counter.total,
        )

        return self._parse_chapter_response(result)
```

---

### Architectural Fitness Functions

**Key Principle:** Automate verification that architectural boundaries remain intact.

```python
# tests/test_architecture.py

import ast
from pathlib import Path

class ArchitectureConfig:
    """Define expected layer structure."""
    LAYER_HIERARCHY = ["domain", "ports", "processors", "adapters", "cli"]

    # Inner layers should not import from outer layers
    FORBIDDEN_IMPORTS = {
        "domain": ["adapters", "cli", "processors"],
        "ports": ["adapters", "cli"],
        "processors": ["adapters", "cli"],
    }

def test_dependency_rule():
    """Verify dependencies only flow inward."""
    for module_path in Path("book_ingestion").rglob("*.py"):
        layer = _get_layer(module_path)
        imports = _extract_imports(module_path)

        forbidden = ArchitectureConfig.FORBIDDEN_IMPORTS.get(layer, [])
        for imp in imports:
            imp_layer = _get_layer_from_import(imp)
            assert imp_layer not in forbidden, (
                f"{module_path} in layer '{layer}' imports from '{imp_layer}'"
            )

def test_ports_are_protocols():
    """Verify all ports are Protocol classes."""
    for port_file in Path("book_ingestion/ports").glob("*.py"):
        tree = ast.parse(port_file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                assert "Protocol" in bases, f"{node.name} must be a Protocol"
```

---

### Monitoring Cadence Strategy

| Frequency | Metrics | Action |
|-----------|---------|--------|
| **Real-time** | Latency, error rate, LLM failures | Alert on threshold breach |
| **Daily** | Token usage, cost per book, fallback rate | Optimize prompts |
| **Weekly** | Detection confidence trends, quality scores | Retrain/adjust thresholds |

---

## Success Criteria

1. **Functional:**
   - [ ] `from book_ingestion import EnhancedPipeline` works
   - [ ] CLI still works: `book-ingestion process book.pdf`
   - [ ] agentic_pipeline uses direct imports (no subprocess)
   - [ ] LLM fallback is called when confidence < 0.5

2. **Data Flow:**
   - [ ] Orchestrator receives `PipelineResult` with all fields
   - [ ] Quality scores stored in pipeline database
   - [ ] Approval routing uses detection confidence
   - [ ] Recommendations influence retry strategy

3. **Non-Functional:**
   - [ ] No breaking changes to existing CLI
   - [ ] Heavy dependencies (torch) only loaded when needed
   - [ ] Tests pass for both projects

4. **Observability (NEW):**
   - [ ] Structured logging with trace IDs across layers
   - [ ] LLM token usage tracking
   - [ ] Architectural fitness tests in CI
   - [ ] Error handling follows OperationResult pattern

---

## References

### Books Consulted

- **Clean Architecture with Python** (Packt 2025)
  - Ch 9: Interface Adapters & Error Handling at Boundaries
  - Ch 10: Implementing Observability - Structured Logging & Tracing
  - Ch 10: Architectural Fitness Functions
  - Dependency Inversion, Adapter Pattern, OperationResult pattern

- **Generative AI with LangChain** (2nd Edition)
  - Ch 9: Production-Ready LLM Deployment and Observability
  - LLM-specific metrics: TTFT, token economy, tool usage analytics
  - Monitoring cadence: real-time vs daily vs weekly
  - LiteLLM for provider fallbacks and reliability

### Other References

- **python-dependency-injector** - Composition root patterns
- **PEP 561** - py.typed marker for type hints
- **typing.Protocol** (PEP 544) - Structural subtyping for duck typing

---

## Next Steps

1. Review and approve this design
2. Create feature branch: `git checkout -b feature/unified-architecture`
3. Implement Phase 1 (prepare book-ingestion)
   - Include `ports/logger.py` Protocol
   - Add `OperationResult` pattern for error handling
4. Implement Phase 2 (wire agentic_pipeline)
   - Add `StructuredLogger` adapter
   - Implement trace ID middleware
5. Implement Phase 3 (observability)
   - Add LLM token tracking
   - Create monitoring dashboard metrics
6. Implement Phase 4 (testing)
   - Add architectural fitness tests to CI
   - Test dependency rule violations
7. Test end-to-end with sample books
8. Remove subprocess calls
9. Merge and deploy
