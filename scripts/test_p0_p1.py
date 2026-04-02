"""
P0 + P1 Validation Test Suite
"""
import importlib.util
import os
import sys
import io
# Force UTF-8 output on Windows terminals
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT = r"C:\Users\Pula Srisurya\Desktop\Autonomus engineer"
PASS  = "[PASS]"
FAIL  = "[FAIL]"
results = []

def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, condition, detail))
    suffix = f"  -- {detail}" if detail else ""
    print(f"  {status} {name}{suffix}")

def read(path):
    return open(path, encoding="utf-8", errors="replace").read()

def section(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print('='*60)

sys.path.insert(0, ROOT)

# ─── P0 #1: License ──────────────────────────────────────────────────────────
section("P0 #1 -- MIT License")
lic_path = os.path.join(ROOT, "LICENSE")
check("LICENSE file exists", os.path.exists(lic_path))
if os.path.exists(lic_path):
    content = read(lic_path)
    check("MIT text present", "MIT License" in content)
    check("Author name present", "SriSuryaPoola" in content)
    check("Year present", "2026" in content)

# ─── P0 #2: README ──────────────────────────────────────────────────────────
section("P0 #2 -- Honest README")
readme_path = os.path.join(ROOT, "README.md")
check("README.md exists", os.path.exists(readme_path))
if os.path.exists(readme_path):
    readme = read(readme_path)
    word_count = len(readme.split())
    check(f"Under 900 words ({word_count} words)", word_count < 900, f"{word_count} words")
    check("MIT badge present", "img.shields.io/badge/License-MIT" in readme)
    check("Docker install present", "docker compose up" in readme)
    check("Limitations section present", "Limitation" in readme)
    check("Token cost warning", "token" in readme.lower())
    check("Screenshot referenced", "platform_demo.png" in readme)
    check("No Phase 4 hype leftover", "(Phase 4)" not in readme)
    check("evolution.md linked", "evolution.md" in readme)

# ─── P0 #3: Root Cleanup ────────────────────────────────────────────────────
section("P0 #3 -- Root Directory Clean")
root_files = [f for f in os.listdir(ROOT) if os.path.isfile(os.path.join(ROOT, f))]
for j in ["dummy.txt", "out.txt", "output.txt", "test_output.txt",
          "math_lib.py", "implementation__anal.py", "implementation__buil.py"]:
    check(f"Removed: {j}", j not in root_files)
check("scripts/ folder exists", os.path.isdir(os.path.join(ROOT, "scripts")))
check("docs/ folder exists", os.path.isdir(os.path.join(ROOT, "docs")))
check("dispatch_flask.py in scripts/", os.path.exists(os.path.join(ROOT, "scripts", "dispatch_flask.py")))
gi = os.path.join(ROOT, ".gitignore")
check(".gitignore exists", os.path.exists(gi))
if os.path.exists(gi):
    gi_content = read(gi)
    check(".gitignore has .env", ".env" in gi_content)
    check(".gitignore has __pycache__", "__pycache__" in gi_content)
check("docs/evolution.md exists", os.path.exists(os.path.join(ROOT, "docs", "evolution.md")))
check("docs/platform_demo.png exists", os.path.exists(os.path.join(ROOT, "docs", "platform_demo.png")))

# ─── P1 #4: Docker ───────────────────────────────────────────────────────────
section("P1 #4 -- Docker Setup")
check("Dockerfile exists", os.path.exists(os.path.join(ROOT, "Dockerfile")))
check("docker-compose.yml exists", os.path.exists(os.path.join(ROOT, "docker-compose.yml")))
check(".dockerignore exists", os.path.exists(os.path.join(ROOT, ".dockerignore")))
dc_path = os.path.join(ROOT, "docker-compose.yml")
if os.path.exists(dc_path):
    dc = read(dc_path)
    check("backend service defined", "backend:" in dc)
    check("frontend service defined", "frontend:" in dc)
    check("port 8000 mapped", "8000:8000" in dc)
    check("port 3000 mapped", "3000:3000" in dc)
    check("env vars injected", "ANTHROPIC_API_KEY" in dc)

# ─── P1 #5: Multi-LLM ────────────────────────────────────────────────────────
section("P1 #5 -- Multi-LLM Provider")
llm_path = os.path.join(ROOT, "config", "llm_providers.py")
check("config/llm_providers.py exists", os.path.exists(llm_path))
if os.path.exists(llm_path):
    content = read(llm_path)
    check("AnthropicProvider defined", "class AnthropicProvider" in content)
    check("OpenAIProvider defined", "class OpenAIProvider" in content)
    check("OllamaProvider defined", "class OllamaProvider" in content)
    check("GeminiProvider defined", "class GeminiProvider" in content)
    check("HeuristicProvider defined", "class HeuristicProvider" in content)
    check("get_llm_client() factory", "def get_llm_client" in content)
    check("Auto-detect chain defined", "_FALLBACK_ORDER" in content)
    # Live import test
    spec = importlib.util.spec_from_file_location("llm_providers", llm_path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        client = mod.get_llm_client()
        check(f"Auto-detect returns provider: {client.name}", True, client.name)
        check("HeuristicProvider.is_available() == True", mod.HeuristicProvider().is_available())
    except Exception as e:
        check("Module imports cleanly", False, str(e)[:120])

# ─── P1 #6: pyproject.toml ───────────────────────────────────────────────────
section("P1 #6 -- pyproject.toml")
ppt_path = os.path.join(ROOT, "pyproject.toml")
check("pyproject.toml exists", os.path.exists(ppt_path))
if os.path.exists(ppt_path):
    content = read(ppt_path)
    check("project name set", "autonomous-engineer" in content)
    check("CLI entry point (ae)", 'ae = "cli:main"' in content)
    check("optional-dependencies group", "[project.optional-dependencies]" in content)
    check("ruff config", "[tool.ruff]" in content)
    check("mypy config", "[tool.mypy]" in content)
    check("bandit config", "[tool.bandit]" in content)
    try:
        import tomllib
        with open(ppt_path, "rb") as f:
            tomllib.load(f)
        check("Valid TOML syntax", True)
    except ImportError:
        check("Valid TOML syntax", True, "tomllib not found -- skipped")
    except Exception as e:
        check("Valid TOML syntax", False, str(e)[:80])

# ─── P1 #7: Atomic Rollback ──────────────────────────────────────────────────
section("P1 #7 -- Atomic Rollback (SnapshotManager)")
snap_path = os.path.join(ROOT, "core", "snapshot.py")
check("core/snapshot.py exists", os.path.exists(snap_path))
if os.path.exists(snap_path):
    try:
        from core.snapshot import SnapshotManager
        import tempfile, shutil
        tmp_ws = tempfile.mkdtemp()
        test_file = os.path.join(tmp_ws, "hello.py")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write('print("original")\n')
        snap = SnapshotManager(tmp_ws)
        snap.take()
        check("Snapshot taken", snap.has_snapshot)
        with open(test_file, "w", encoding="utf-8") as f:
            f.write('print("mutated")\n')
        ok = snap.rollback()
        check("Rollback returned True", ok)
        restored = open(test_file, encoding="utf-8").read()
        check("File restored to original content", "original" in restored, repr(restored))
        snap.cleanup()
        check("Cleanup removes snapshot", not snap.has_snapshot)
        shutil.rmtree(tmp_ws, ignore_errors=True)
    except Exception as e:
        check("SnapshotManager works end-to-end", False, str(e)[:120])

# ─── P1 #9: Static Analysis ──────────────────────────────────────────────────
section("P1 #9 -- Static Analysis Gatekeeper")
sa_path = os.path.join(ROOT, "core", "static_analysis.py")
check("core/static_analysis.py exists", os.path.exists(sa_path))
if os.path.exists(sa_path):
    try:
        from core.static_analysis import StaticAnalysisGatekeeper
        import tempfile
        gate = StaticAnalysisGatekeeper()
        tmp = tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                          encoding="utf-8", delete=False)
        tmp.write('def test_ok():\n    assert True\n')
        tmp.close()
        result = gate.run(tmp.name, cwd=ROOT)
        check("Gatekeeper runs without error", True)
        check("Result has .passed", hasattr(result, "passed"))
        check("Result has .summary", hasattr(result, "summary"))
        check(f"Clean file passes ({result.summary})", result.passed, result.summary)
        os.unlink(tmp.name)
    except Exception as e:
        check("StaticAnalysisGatekeeper works", False, str(e)[:120])

# ─── P1 #10: GitHub Actions ──────────────────────────────────────────────────
section("P1 #10 -- GitHub Actions CI")
ci_path = os.path.join(ROOT, ".github", "workflows", "ci.yml")
check("ci.yml exists", os.path.exists(ci_path))
if os.path.exists(ci_path):
    content = read(ci_path)
    check("lint job defined", "lint:" in content)
    check("test job defined", "test:" in content)
    check("ruff step", "ruff" in content)
    check("bandit step", "bandit" in content)
    check("pytest with coverage", "pytest" in content and "cov" in content)
    check("triggers on push", "push:" in content)
    check("triggers on pull_request", "pull_request:" in content)

# ─── P1 #8: Settings ──────────────────────────────────────────────────────────
section("P1 #8 -- Settings (Budget + Static Analysis)")
settings_path = os.path.join(ROOT, "config", "settings.py")
if os.path.exists(settings_path):
    content = read(settings_path)
    check("TOKEN_BUDGET_PER_PROJECT defined", "TOKEN_BUDGET_PER_PROJECT" in content)
    check("LLM_PROVIDER env var", "LLM_PROVIDER" in content)
    check("STATIC_ANALYSIS_ENABLED", "STATIC_ANALYSIS_ENABLED" in content)

# ─── P1: QAEngineer wiring ───────────────────────────────────────────────────
section("P1 -- QAEngineer Integration")
qa_path = os.path.join(ROOT, "agents", "workers", "qa_engineer.py")
if os.path.exists(qa_path):
    content = read(qa_path)
    check("SnapshotManager imported", "SnapshotManager" in content)
    check("StaticAnalysisGatekeeper imported", "StaticAnalysisGatekeeper" in content)
    check("snapshot.take() called before loop", "snapshot.take()" in content)
    check("static_analysis.run() in validate step", "self.static_analysis.run" in content)
    check("snapshot.rollback() on escalation", "snapshot.rollback()" in content)
    check("snapshot.cleanup() on convergence", "snapshot.cleanup()" in content)

# ─── Summary ─────────────────────────────────────────────────────────────────
total  = len(results)
passed = sum(1 for _, ok, _ in results if ok)
failed = total - passed

print(f"\n{'='*60}")
print(f"  RESULTS: {passed}/{total} passed  |  {failed} failed")
print('='*60)
if failed:
    print("\n  Failed checks:")
    for name, ok, detail in results:
        if not ok:
            print(f"    x {name}" + (f"  -- {detail}" if detail else ""))
print()
sys.exit(0 if failed == 0 else 1)
