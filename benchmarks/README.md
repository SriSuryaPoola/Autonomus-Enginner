# Benchmarks

This folder documents the platform's verified performance against real open-source repositories.

---

## Test Matrix

| Repository | Type | Files | Platform Result | Coverage Achieved | Iterations |
|---|---|---|---|---|---|
| `psf/requests` | HTTP Library | ~80 modules | ✅ CONVERGED | 74.5% | 4 |
| `pallets/flask` | Web Framework | ~200 modules | ✅ CONVERGED | 71.2% | 4 |
| `tiangolo/fastapi` | Async API Framework | ~300 modules | ✅ CONVERGED | 73.1% | 3 |
| `django/django` | Full-Stack Monolith | 7,000+ files | ✅ E2E Chain Verified | N/A (chain test) | 2 |

---

## Platform Performance

| Metric | Value |
|---|---|
| Convergence Rate (tested repos) | 100% (4/4) |
| Average iterations to converge | 3.25 |
| Average self-heals per task | 1.8 |
| Token cost per convergence cycle | ~10k–50k tokens (~$0.03–$0.15) |
| Static analysis gate pass rate | 94% |

---

## SWE-bench Status

> Formal SWE-bench evaluation is **planned** for a future release.
> Current benchmarks are E2E system tests, not isolated task-level evaluations.

---

## Methodology

All tests were run using the full platform stack:
- FastAPI backend on `localhost:8000`
- Real GitHub repositories cloned locally
- Full convergence loop: generate → sandbox → patch → coverage gate → static analysis
- No mocking — real pytest execution in isolated subprocesses

### Test Reports

Detailed per-repo reports are in [`../Report/`](../Report/):
- [PSF Requests Report](../Report/psf_requests_report.md)
- [Flask Report](../Report/flask_stress_test_report.md)
- [FastAPI Report](../Report/fastapi_stress_test_report.md)
- [Django E2E Report](../Report/django_e2e_report.md)
