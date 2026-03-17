---
status: archived
tags: [project/book-ingestion-python, format/plan]
type: note
created: '2026-01-30'
modified: '2026-01-30'
---

# Unified Book Processing Architecture

**A Strategic Overview for Stakeholders**

*Date: January 30, 2025*
*Author: Taylor Stephens*
*Status: Proposed*

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [The Problem We're Solving](#the-problem-were-solving)
3. [Our Solution](#our-solution)
4. [How It Works](#how-it-works)
5. [Why This Approach](#why-this-approach)
6. [Alternatives We Considered](#alternatives-we-considered)
7. [Benefits & Outcomes](#benefits--outcomes)
8. [Risks & Mitigations](#risks--mitigations)
9. [Implementation Roadmap](#implementation-roadmap)
10. [Frequently Asked Questions](#frequently-asked-questions)

---

## Executive Summary

We have two systems that process books for our library:

1. **Book Ingestion** — Converts PDF/EPUB files into clean, structured chapters
2. **Agentic Pipeline** — An AI-powered orchestrator that classifies books and manages the processing workflow

**The Problem:** These systems currently communicate through a wall. The orchestrator launches book ingestion as a separate process, waits for it to finish, and only learns "it worked" or "it failed." All the rich intelligence that book ingestion produces—quality scores, confidence levels, warnings, recommendations—gets thrown away.

**The Solution:** We're removing the wall. Instead of launching a separate process, the orchestrator will directly integrate with book ingestion as a library. This enables two-way communication: the orchestrator can lend its AI capabilities to help with difficult books, and book ingestion can return detailed quality information that drives smarter decisions.

**The Outcome:** Better books in the library, fewer manual reviews, lower costs, and a foundation for future AI-assisted features.

---

## The Problem We're Solving

### What Happens Today

When a new book arrives, here's the current flow:

```
User drops book.pdf into the system
           ↓
   Agentic Pipeline sees it
           ↓
   Launches book-ingestion as a subprocess
           ↓
   Waits... waits... waits...
           ↓
   Gets back: "Exit code 0" (success) or "Exit code 1" (failure)
           ↓
   That's it. No other information.
```

### Why This Is a Problem

**1. We're throwing away valuable intelligence**

Book ingestion actually produces rich information:
- "I'm 92% confident these are the correct chapter boundaries"
- "Quality score: 78/100 — some OCR artifacts detected"
- "Warning: Chapter 7 seems unusually short, might be misdetected"
- "Recommendation: Consider manual review of pages 145-160"

But because we communicate through a subprocess wall, all of this gets lost. The orchestrator only sees pass/fail.

**2. The AI can't help when things get hard**

Sometimes book ingestion encounters a difficult book—maybe the chapter titles are unusual, or the formatting is inconsistent. It has heuristics (rules) to handle common cases, but when those fail, it's stuck.

Meanwhile, the Agentic Pipeline has access to powerful AI models that could help. But there's no way for book ingestion to ask for help—the wall prevents it.

**3. Decisions are made with incomplete information**

The orchestrator decides:
- Should this book be auto-approved or need human review?
- Should we retry processing with different settings?
- Is this book good enough for the library?

Today, these decisions are based on guesswork because we don't have the quality signals. We either over-review (wasting human time) or under-review (letting poor quality slip through).

**4. Duplicate work and inconsistency**

Both systems track state, handle errors, and log events—but they do it differently because they can't share approaches. This creates maintenance burden and inconsistent behavior.

---

## Our Solution

### The Core Idea

**Turn book-ingestion into a library that agentic-pipeline imports directly.**

Instead of:
```
Orchestrator  ──[subprocess wall]──►  Book Ingestion (separate process)
```

We get:
```
Orchestrator  ──[direct import]──►  Book Ingestion (same process)
     ↑                                      │
     │    AI capabilities flow DOWN         │
     │◄─────────────────────────────────────│
     │                                      │
     │    Rich quality data flows UP        │
     │◄─────────────────────────────────────┘
```

### What Changes

| Aspect | Before | After |
|--------|--------|-------|
| **Communication** | Exit codes only | Full data objects with 15+ fields |
| **AI Assistance** | None possible | AI helps with difficult chapter detection |
| **Quality Signals** | Lost | Drive approval routing decisions |
| **Error Details** | "It failed" | Specific error type, context, recovery suggestions |
| **Processing Decisions** | Guesswork | Data-driven based on confidence scores |

---

## How It Works

### For Non-Technical Readers

Think of it like this:

**Before:** You're managing a team, but you can only communicate with one member through a locked door. You slide a document under the door, wait, and they slide back a note that says either "Done" or "Failed." You have no idea what happened inside.

**After:** The door is open. You can have a conversation. They can ask you questions when they're stuck. They can explain exactly what they did, what they're confident about, and what concerns them. You can make better decisions because you have complete information.

### The Key Components

**1. Ports (Defined Interfaces)**

We define clear "contracts" for how the systems talk to each other:

- **LLM Fallback Port**: "When you're stuck detecting chapters, here's how to ask the AI for help"
- **Book Repository Port**: "Here's how to save and retrieve book data"
- **Logger Port**: "Here's how to report what's happening"

These contracts are technology-agnostic. They describe *what* can be done, not *how* it's implemented.

**2. Adapters (Implementations)**

For each contract, we build an adapter that fulfills it:

- The orchestrator provides an "LLM Fallback Adapter" that connects to our AI models
- We provide a "SQLite Adapter" for storing books in the database
- We provide a "Structured Logger" that creates traceable logs

**3. Pipeline Results (Rich Data)**

Instead of just "success/failure," book ingestion returns a comprehensive result:

```
PipelineResult:
├── chapters: List of detected chapters with content
├── detection_method: "regex" or "semantic" or "llm_assisted"
├── detection_confidence: 0.87 (87% confident)
├── quality_score: 82/100
├── is_valid: true
├── needs_review: false (confidence high enough)
├── warnings: ["Chapter 12 title unclear"]
├── recommendations: ["Consider adding table of contents"]
└── processing_stats: timing, token counts, etc.
```

**4. Smart Routing**

With this rich data, the orchestrator makes informed decisions:

```
If confidence >= 90% AND quality_score >= 80:
    → Auto-approve, no human review needed

If confidence >= 70% AND quality_score >= 60:
    → Auto-approve with monitoring

If confidence < 70% OR has warnings:
    → Route to human review with specific guidance

If quality_score < 50:
    → Reject and explain why
```

---

## Why This Approach

### Guiding Principles

We followed established software architecture principles, validated against expert recommendations from industry-standard texts:

**1. Dependency Inversion (from Clean Architecture)**

High-level policy (orchestration decisions) shouldn't depend on low-level details (how chapters are detected). Both depend on abstractions (the Ports).

*Why it matters:* We can change how chapter detection works without changing how orchestration works. We can swap AI providers without touching the processing logic.

**2. Composition Over Configuration**

We wire together components at startup, rather than scattering configuration everywhere.

*Why it matters:* All the "what connects to what" decisions are in one place. Easier to understand, test, and change.

**3. Lazy Loading (from LangChain patterns)**

Heavy dependencies (AI models, PDF libraries) only load when actually needed.

*Why it matters:* Fast startup. Lower memory usage for simple operations. Pay for what you use.

**4. Protocol-Based Interfaces (Python typing)**

Contracts are defined using Python's Protocol system—essentially "if it walks like a duck and quacks like a duck, it's a duck."

*Why it matters:* Implementing systems don't need to inherit from our base classes. Easier to integrate with existing code. Better for testing with mocks.

---

## Alternatives We Considered

### Alternative A: Keep Subprocess, Add API

**Idea:** Keep book ingestion as a separate process, but have it expose a REST API that returns rich data.

**Why we didn't choose it:**

| Factor | API Approach | Direct Import (Chosen) |
|--------|--------------|------------------------|
| **Latency** | Network overhead on every call | Zero overhead |
| **Complexity** | HTTP server, serialization, error handling | Simple function calls |
| **AI Integration** | Would need callback URLs, webhooks | Direct method calls |
| **Deployment** | Two processes to manage | One process |
| **Debugging** | Distributed tracing needed | Stack traces just work |

**When API would be better:** If we needed to scale book processing independently, or if teams were in different organizations. Neither applies here.

---

### Alternative B: Message Queue (Kafka/RabbitMQ)

**Idea:** Orchestrator publishes "process this book" messages. Book ingestion consumes them and publishes results back.

**Why we didn't choose it:**

| Factor | Message Queue | Direct Import (Chosen) |
|--------|---------------|------------------------|
| **Complexity** | Queue infrastructure, dead letters, retries | None |
| **Latency** | Message serialization + queue delays | Zero |
| **AI Fallback** | Difficult—needs request/reply pattern | Natural |
| **Debugging** | Messages disappear into queues | Synchronous, traceable |
| **Team Size** | Built for large distributed teams | Right-sized for us |

**When queues would be better:** If we processed thousands of books per hour and needed to buffer bursts. We process dozens per day.

---

### Alternative C: Microservices

**Idea:** Each capability (PDF conversion, chapter detection, quality validation) becomes its own service with its own API.

**Why we didn't choose it:**

| Factor | Microservices | Direct Import (Chosen) |
|--------|---------------|------------------------|
| **Operational Cost** | 5+ services to deploy, monitor, scale | One application |
| **Network Calls** | Every step is a network hop | In-process |
| **Data Consistency** | Distributed transactions | Local transactions |
| **Development Speed** | Contract negotiation between services | Refactor freely |
| **Team Structure** | Designed for 50+ engineers | We're a small team |

**When microservices would be better:** If different teams owned different capabilities, or if capabilities scaled independently. Book processing is one cohesive workflow.

---

### Alternative D: Monolith (Merge Everything)

**Idea:** Combine both projects into a single codebase with no boundaries.

**Why we didn't choose it:**

| Factor | Full Merge | Library Import (Chosen) |
|--------|-----------|------------------------|
| **Reusability** | Book ingestion can't be used elsewhere | Can be used by any Python app |
| **Testing** | Everything coupled, hard to test in isolation | Clean boundaries, easy mocking |
| **Cognitive Load** | One giant codebase | Clear separation of concerns |
| **CLI Preservation** | Would need to maintain separately | CLI keeps working |

**When full merge would be better:** If we were certain no one else would ever use book ingestion. But the MCP server already uses the output, and future tools might want to process books too.

---

### Why Direct Import Wins

For our situation—a small team, moderate volume, cohesive workflow, need for AI integration—direct import with clean interfaces gives us:

1. **Simplicity** without sacrificing flexibility
2. **Performance** without premature optimization
3. **Maintainability** without over-engineering
4. **Extensibility** without speculation about future needs

---

## Benefits & Outcomes

### Immediate Benefits

| Benefit | Impact | Measurement |
|---------|--------|-------------|
| **Better approval routing** | Fewer unnecessary human reviews | Track auto-approve rate |
| **AI-assisted detection** | Handle difficult books that previously failed | Track LLM fallback success rate |
| **Quality visibility** | See quality scores in dashboard | Quality score distribution |
| **Faster debugging** | Trace issues across entire flow | Mean time to diagnose |

### Medium-Term Benefits

| Benefit | Impact | Measurement |
|---------|--------|-------------|
| **Reduced processing costs** | Use cheaper models for easy books, powerful models only when needed | Cost per book processed |
| **Higher library quality** | Consistent quality standards enforced automatically | Average quality score trend |
| **Developer productivity** | One codebase to understand, not two | Time to implement new features |

### Long-Term Benefits

| Benefit | Impact |
|---------|--------|
| **Foundation for AI features** | Can add AI-powered metadata extraction, summarization, etc. |
| **Reusable library** | Other tools can import book-ingestion |
| **Architectural template** | Pattern can apply to other integration needs |

---

## Risks & Mitigations

### Risk 1: Breaking Existing CLI

**Risk:** Book ingestion has an existing command-line interface. Restructuring might break it.

**Mitigation:**
- CLI is preserved as a thin wrapper around the library
- All existing commands continue to work
- We add tests to verify CLI compatibility before merging

**Likelihood:** Low (we're adding, not removing)

---

### Risk 2: Increased Memory Usage

**Risk:** Running in the same process means book ingestion's dependencies load into the orchestrator's memory.

**Mitigation:**
- Lazy loading ensures heavy dependencies (AI models, PDF libraries) only load when used
- Optional dependency groups—install only what you need
- Memory profiling during testing

**Likelihood:** Low (lazy loading addresses this)

---

### Risk 3: Coupling Increases Over Time

**Risk:** Without discipline, the clean boundaries between systems could erode.

**Mitigation:**
- Architectural fitness tests run in CI
- Tests automatically verify dependencies only flow in allowed directions
- Protocol interfaces enforce contracts at compile time

**Likelihood:** Medium (requires ongoing discipline)

---

### Risk 4: Migration Complexity

**Risk:** Changing directory structure and imports could introduce bugs.

**Mitigation:**
- Phased migration plan with validation at each step
- Comprehensive test suite runs at every phase
- Rollback plan if issues discovered

**Likelihood:** Low (well-understood refactoring)

---

## Implementation Roadmap

### Phase 1: Prepare Book Ingestion (Week 1-2)

**Goal:** Make book-ingestion importable without breaking existing CLI

- Restructure as proper Python package
- Add Protocol interfaces (Ports)
- Implement lazy loading for heavy dependencies
- Create composition root (wiring)
- Verify CLI still works

**Exit Criteria:** `from book_ingestion import EnhancedPipeline` works

---

### Phase 2: Build Integration (Week 2-3)

**Goal:** Connect orchestrator to book ingestion

- Add book-ingestion as dependency
- Create LLM Fallback Adapter
- Update orchestrator to use direct imports
- Implement structured logging with trace IDs

**Exit Criteria:** Orchestrator processes books via direct import

---

### Phase 3: Enable Rich Routing (Week 3-4)

**Goal:** Use quality signals for smart decisions

- Update approval routing to use confidence scores
- Store quality metrics in pipeline database
- Create monitoring dashboards
- Implement LLM fallback for low-confidence detection

**Exit Criteria:** Approval decisions based on actual quality data

---

### Phase 4: Cleanup & Validation (Week 4)

**Goal:** Remove old approach, validate system

- Remove subprocess processing code
- Add architectural fitness tests to CI
- End-to-end testing with diverse book samples
- Performance benchmarking
- Documentation updates

**Exit Criteria:** All tests pass, old code removed, documentation complete

---

## Frequently Asked Questions

### "Why not just improve the existing subprocess approach?"

We could add more data to stdout/stderr, but:
- Parsing text output is fragile
- Still can't enable AI fallback (would need two-way communication)
- Increases complexity without solving the core problem

The subprocess wall is the problem. We need to remove it.

---

### "What if we need to scale book processing independently later?"

The library design doesn't prevent this. If we later need massive scale:
1. The library can be wrapped in an API
2. The Ports/Adapters pattern means the orchestrator wouldn't need to change
3. We'd add this complexity when we actually need it, not speculatively

---

### "How does this affect the MCP server (book library)?"

The MCP server reads from the same database that book ingestion writes to. This doesn't change—the data format stays the same. The MCP server will automatically benefit from higher quality data in the database.

---

### "What happens to books that are currently processing?"

During migration:
1. We deploy the new system in parallel
2. New books use the new path
3. In-progress books complete via the old path
4. Once queue is clear, we remove old path

No books are lost or interrupted.

---

### "How do we know it's working?"

Metrics we'll track:
- **Auto-approve rate**: Should increase (fewer false negatives)
- **Human review overrides**: Should decrease (better initial decisions)
- **LLM fallback rate**: Shows how often AI helps
- **Quality score distribution**: Should shift higher over time
- **Processing errors**: Should decrease with better error handling

---

### "What if the AI makes wrong decisions?"

The AI is a fallback, not the primary path. The flow is:
1. Try heuristic detection (fast, free, proven)
2. If confidence is low, ask AI for help
3. If AI result is also low confidence, flag for human review

Humans remain in the loop for uncertain cases. The AI helps—it doesn't replace human judgment.

---

### "Can we revert if something goes wrong?"

Yes. The migration is phased:
- Phase 1 is purely additive (no breaking changes)
- Phase 2 can run parallel with old code
- Old code is only removed in Phase 4 after validation

At any point before Phase 4, we can stop and revert with no impact.

---

## Summary

We're connecting two systems that currently can't talk to each other properly. By making book ingestion a library that the orchestrator imports directly, we enable:

- **Richer data flow** — Quality signals drive better decisions
- **AI assistance** — When heuristics fail, AI can help
- **Simpler architecture** — One process instead of two
- **Future flexibility** — Clean interfaces enable evolution

The approach is grounded in proven architectural patterns, right-sized for our team, and designed with clear rollback paths.

---

*Document version: 1.0*
*Last updated: January 30, 2025*
