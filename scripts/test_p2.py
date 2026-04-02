"""P2 + Quick Wins Validation Test Suite"""
import sys, os, importlib.util
sys.path.insert(0, r'C:\Users\Pula Srisurya\Desktop\Autonomus engineer')
ROOT = r'C:\Users\Pula Srisurya\Desktop\Autonomus engineer'
p = f = 0

def chk(name, ok, detail=''):
    global p, f
    if ok: p += 1
    else: f += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  -- {detail}" if detail else ""))

def rd(path):
    return open(path, encoding='utf-8', errors='replace').read()

def section(t): print(f"\n=== {t} ===")

section("P2 #18 PII SCRUBBER")
try:
    from core.pii_scrubber import PIIScrubber
    s = PIIScrubber()
    chk('PIIScrubber imports', True)
    code_with_key = 'api_key = "sk-ant-abc123456789012345678901234567890"'
    safe, report = s.scrub(code_with_key)
    chk('Anthropic key detected', report.triggered, report.summary)
    chk('Key masked in output', 'sk-ant-' not in safe)
    code_with_email = 'author = "test@example.com"'
    safe2, r2 = s.scrub(code_with_email)
    chk('Email detected', r2.triggered, r2.summary)
    chk('Email masked', '@example.com' not in safe2)
    clean = 'def test_ok():\n    assert True\n'
    _, r3 = s.scrub(clean)
    chk('Clean code has no detections', not r3.triggered)
    chk('is_safe() returns True for clean code', s.is_safe(clean))
except Exception as e:
    chk('PIIScrubber module', False, str(e)[:120])

section("P2 #14 HITL MANAGER")
try:
    from core.hitl_manager import HITLManager, HITLDecision, estimate_confidence
    chk('HITLManager imports', True)
    hitl = HITLManager(threshold=0.85, timeout=1)
    d = hitl.check(0.96, 'test context', 'task_1')
    chk(f'High confidence auto-approved', d == HITLDecision.AUTO, str(d))
    d2 = hitl.check(0.88, 'test context', 'task_2')
    chk(f'Above threshold proceeds', d2 == HITLDecision.AUTO, str(d2))
    conf = estimate_confidence(0.8, 2, 5, 72.0, 1)
    chk(f'estimate_confidence returns 0-1', 0.0 <= conf <= 1.0, f'{conf:.2f}')
    chk('APPROVED/REJECTED/TIMEOUT/AUTO enum values', all(d.value for d in HITLDecision))
    pending = hitl.get_pending()
    chk('get_pending() returns list', isinstance(pending, list))
except Exception as e:
    chk('HITLManager module', False, str(e)[:120])

section("P2 #13 SLM ROUTER")
try:
    from core.slm_router import SLMRouter, TaskComplexity
    chk('SLMRouter imports', True)
    router = SLMRouter()
    c1 = router.classify('add a docstring to this function')
    chk(f'LOW for boilerplate', c1 == TaskComplexity.LOW, str(c1))
    c2 = router.classify('refactor the authentication module for security')
    chk(f'HIGH for security refactor', c2 == TaskComplexity.HIGH, str(c2))
    c3 = router.classify('generate unit tests for this class')
    chk(f'MEDIUM/LOW for test gen', c3 in (TaskComplexity.MEDIUM, TaskComplexity.LOW), str(c3))
    prov = router._select_provider(TaskComplexity.LOW)
    chk(f'Provider selected ({prov.name})', prov is not None, prov.name)
    stats = router.get_routing_stats()
    chk('get_routing_stats() returns dict', isinstance(stats, dict))
except Exception as e:
    chk('SLMRouter module', False, str(e)[:120])

section("QUICK WINS FILES")
chk('CONTRIBUTING.md exists', os.path.exists(os.path.join(ROOT,'CONTRIBUTING.md')))
try:
    contrib = rd(os.path.join(ROOT,'CONTRIBUTING.md'))
    chk('CONTRIBUTING has dev setup', 'pip install' in contrib)
    chk('CONTRIBUTING has code standards', 'ruff' in contrib)
    chk('CONTRIBUTING has PR guide', 'pull request' in contrib.lower())
except: chk('CONTRIBUTING.md readable', False)

chk('.agentconfig exists', os.path.exists(os.path.join(ROOT,'.agentconfig')))
try:
    cfg = rd(os.path.join(ROOT,'.agentconfig'))
    chk('.agentconfig seniority options', 'seniority' in cfg)
    chk('.agentconfig HITL threshold', 'hitl_confidence_threshold' in cfg)
    chk('.agentconfig pii_scrubbing', 'pii_scrubbing' in cfg)
    chk('.agentconfig slm_routing', 'slm_routing' in cfg)
except: chk('.agentconfig readable', False)

chk('benchmarks/ folder', os.path.isdir(os.path.join(ROOT,'benchmarks')))
chk('benchmarks/README.md', os.path.exists(os.path.join(ROOT,'benchmarks','README.md')))
chk('bug_report template', os.path.exists(os.path.join(ROOT,'.github','ISSUE_TEMPLATE','bug_report.md')))
chk('feature_request template', os.path.exists(os.path.join(ROOT,'.github','ISSUE_TEMPLATE','feature_request.md')))

section("P2 INTEGRATION WIRING")
try:
    pe = rd(os.path.join(ROOT,'core','patch_engine.py'))
    chk('PIIScrubber in patch_engine imports', 'PIIScrubber' in pe)
    chk('_scrubber instance in patch_engine', '_scrubber = PIIScrubber()' in pe)
except: chk('patch_engine.py readable', False)

try:
    cf = rd(os.path.join(ROOT,'core','claude_flow.py'))
    chk('SLMRouter in claude_flow', 'SLMRouter' in cf)
    chk('HITLManager in claude_flow', 'HITLManager' in cf)
    chk('PIIScrubber in claude_flow', 'PIIScrubber' in cf)
except: chk('claude_flow.py readable', False)

section("P2 UI ELEMENTS")
try:
    html = rd(os.path.join(ROOT,'ui','index.html'))
    chk('LLM provider badge', 'llm-provider-badge' in html)
    chk('Token burn bar', 'token-burn-bar' in html)
    chk('Static analysis row', 'static-analysis-row' in html)
    chk('Rollback badge', 'rollback-badge' in html)
    chk('LLM provider select', 'cfg-llm-provider' in html)
    chk('Token cost hint', '0.03' in html)
except: chk('index.html readable', False)

try:
    css = rd(os.path.join(ROOT,'ui','index.css'))
    chk('llm-badge CSS', '.llm-badge' in css)
    chk('token-burn-fill CSS', '.token-burn-fill' in css)
    chk('sa-badge.pass CSS', '.sa-badge.pass' in css)
    chk('rollback-badge CSS', '.rollback-badge' in css)
    chk('pulse-dot animation', 'pulse-dot' in css)
except: chk('index.css readable', False)

try:
    js = rd(os.path.join(ROOT,'ui','src','main.js'))
    chk('fetchAndShowLLMProvider()', 'fetchAndShowLLMProvider' in js)
    chk('Token burn JS logic', 'token-burn-fill' in js)
    chk('Static analysis badge JS', 'sa-ruff' in js)
    chk('Rollback badge JS', 'rolled_back' in js)
    chk('LLM provider saved to localStorage', 'engineer_llm_provider' in js)
except: chk('main.js readable', False)

print(f"\n{'='*50}")
print(f"  P2 RESULTS: {p} passed / {f} failed")
print('='*50)
if f > 0:
    print("\n  NOTE: Some failures may indicate integration points not yet activated")
sys.exit(0 if f == 0 else 1)
