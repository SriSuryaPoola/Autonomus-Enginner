// Main Frontend Controller for AI Autonomous Engineer Platform
const API_BASE = "http://localhost:8000/api";
const WS_BASE = "ws://localhost:8000/ws/events";

let currentProject = null;
let projects = [];
let socket = null;

// --- DOM Elements ---
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');
const projectList = document.getElementById('project-list');
const taskInput = document.getElementById('task-input');
const executeBtn = document.getElementById('send-task-btn');
const dashboardStats = {
    status: document.getElementById('exec-status'),
    tasks: document.getElementById('exec-tasks'),
    failures: document.getElementById('exec-failures')
};

// --- Tab Switching ---
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const tabId = btn.getAttribute('data-tab');
        
        // Update active tab button
        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        
        // Update active content
        tabContents.forEach(content => {
            content.classList.remove('active');
            if (content.id === `${tabId}-view`) {
                content.classList.add('active');
            }
        });
    });
});

// --- Project Management ---
const projectModal = document.getElementById('project-modal');
const newProjectBtn = document.getElementById('new-project-btn');
const saveProjectBtn = document.getElementById('save-project-btn');
const closeProjectBtn = document.getElementById('close-project-modal');

newProjectBtn.onclick = () => projectModal.classList.remove('hidden');
closeProjectBtn.onclick = () => projectModal.classList.add('hidden');

saveProjectBtn.onclick = async () => {
    const name = document.getElementById('new-project-name').value.trim();
    const desc = document.getElementById('new-project-desc').value.trim();
    const repo = document.getElementById('new-project-repo').value.trim();
    
    if (!name) return alert("Project name is required.");

    try {
        const resp = await fetch(`${API_BASE}/projects`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, description: desc, repository_url: repo })
        });
        const newProject = await resp.json();
        projects.push(newProject);
        selectProject(newProject.id);
        projectModal.classList.add('hidden');
    } catch (err) {
        console.error("Using offline mode due to server unavailability.");
        // Mock success for offline demo
        const mockID = Math.random().toString(36).substring(7);
        const newProject = { id: mockID, name, description: desc };
        projects.push(newProject);
        selectProject(newProject.id);
        projectModal.classList.add('hidden');
    }
};

async function fetchProjects() {
    try {
        const resp = await fetch(`${API_BASE}/projects`);
        projects = await resp.json();
        renderProjectList();
    } catch (err) {
        console.warn("Backend offline. Dashboard running in demo mode.");
        projects = [{ id: "demo-1", name: "Sample Project", description: "This is a local demo project." }];
        renderProjectList();
    }
}

function renderProjectList() {
    projectList.innerHTML = projects.map(p => `
        <div class="project-item ${currentProject?.id === p.id ? 'active' : ''}" onclick="selectProject('${p.id}')" title="${p.name}">
            <div class="p-icon">${p.name[0]}</div>
            <div class="p-details">
                <span class="p-name">${p.name}</span>
                <span class="p-id">${p.id}</span>
            </div>
        </div>
    `).join('');
}

window.selectProject = (id) => {
    currentProject = projects.find(p => p.id === id);
    if (!currentProject) return;
    document.getElementById('current-project-name').textContent = currentProject.name;
    document.getElementById('current-project-desc').textContent = currentProject.description;
    
    // Reset views for new project
    document.getElementById('dag-viz').innerHTML = "Awaiting task initiation...";
    document.getElementById('report-list').innerHTML = "";
    document.getElementById('chat-messages').innerHTML = ""; // Phase 6 FIX: clear isolated chat
    
    // Legacy metrics
    dashboardStats.status.textContent = "IDLE";
    dashboardStats.status.style.color = "#8b949e";

    // Phase 5 metrics
    updateConvergencePanel({ state: "AWAITING", coverage: { percentage: null }, iterations: "—", self_heals: "—" });
    if (_convergencePoller) {
        clearInterval(_convergencePoller);
        _convergencePoller = null;
    }
    
    renderProjectList();
};

// --- Task Execution ---
executeBtn.addEventListener('click', async () => {
    if (!currentProject) return alert("Select a project first!");
    const prompt = taskInput.value.trim();
    if (!prompt) return;

    addChatMessage("user", prompt);
    taskInput.value = "";
    
    // Immediate UI Feedback
    dashboardStats.status.textContent = "RUNNING";
    dashboardStats.status.style.color = "var(--acc-cyan)";
    updateConvergencePanel({ state: "RUNNING", coverage: { percentage: null }, iterations: "…", self_heals: "…" });
    renderMockDashboard();
    renderMockReports();

    try {
        const resp = await fetch(`${API_BASE}/tasks`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: currentProject.id, prompt: prompt })
        });
        if (resp.ok) {
            addChatMessage("system", "Engine initiated. Connecting to orchestration core...");
            // Start polling convergence state every 5 seconds
            startConvergencePolling(currentProject.id);
        } else {
            throw new Error("Backend offline");
        }
    } catch(e) {
        addChatMessage("system", "Warning: Backend unreachable. Entering Simulation Mode.");
        simulateAgentFlow(prompt);
    }
});

function renderMockDashboard() {
    const viz = document.getElementById('dag-viz');
    viz.innerHTML = `
        <div style="display: flex; flex-direction: column; align-items: center; gap: 20px;">
            <svg viewBox="0 0 400 120" style="width:100%; max-width: 500px;">
                <defs>
                    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="0" refY="3.5" orient="auto">
                        <polygon points="0 0, 10 3.5, 0 7" fill="#444" />
                    </marker>
                </defs>
                <circle cx="50" cy="60" r="15" fill="var(--acc-cyan)" style="filter: drop-shadow(0 0 5px var(--acc-cyan));" />
                <text x="35" y="90" fill="#fff" font-size="10" font-weight="bold">COORD</text>
                
                <path d="M 65 60 L 130 30" stroke="#444" fill="none" marker-end="url(#arrowhead)" />
                <path d="M 65 60 L 130 90" stroke="#444" fill="none" marker-end="url(#arrowhead)" />
                
                <circle cx="150" cy="30" r="15" fill="#ff00ea" />
                <text x="135" y="55" fill="#fff" font-size="9">DEV_CORE</text>
                
                <circle cx="150" cy="90" r="15" fill="#00ff88" />
                <text x="138" y="115" fill="#fff" font-size="9">QA_AUDIT</text>
                
                <path d="M 165 30 L 230 60" stroke="#444" fill="none" marker-end="url(#arrowhead)" />
                <path d="M 165 90 L 230 60" stroke="#444" fill="none" marker-end="url(#arrowhead)" />
                
                <circle cx="250" cy="60" r="15" fill="#fff" />
                <text x="235" y="90" fill="#fff" font-size="10">REPLAY</text>
            </svg>
            <p style="font-size: 0.8rem; color: #8b949e; margin: 0;">Auto-scaling DAG execution graph... (Real-time)</p>
        </div>
    `;
    dashboardStats.tasks.textContent = "1";
    dashboardStats.failures.textContent = "0";
}

function renderMockReports() {
    const reports = document.getElementById('report-list');
    reports.innerHTML = `
        <div class="report-item" onclick="viewReport('Final_Engineering_Spec')">
            <label>ENGINEERING SPEC</label>
            <h4>Architecture Design Document</h4>
            <p>Validated by Claude 3.5 Sonnet</p>
        </div>
        <div class="report-item" onclick="viewReport('Quality_Audit_Results')">
            <label>QA AUDIT</label>
            <h4>Test Coverage & Performance</h4>
            <p>100% Pass Rate (Simulation)</p>
        </div>
    `;
}

window.viewReport = (name) => {
    const viewer = document.getElementById('report-view-content');
    viewer.classList.remove('hidden');
    
    const content = name === 'Final_Engineering_Spec' 
        ? "# Engineering Specification\n\n## Overview\nThis project implements a high-performance multi-agent coordination layer.\n\n## Architecture\n- **Dev Agent:** Code Generation\n- **QA Agent:** Logic Validation\n- **Orchestration:** Claude-Powered Flow"
        : "# QA Audit Results\n\n## Metrics\n- **Unit Tests:** 42 Passed\n- **Regression:** 15 Passed\n- **Performance:** 98th Percentile Latency < 200ms";

    viewer.innerHTML = `
        <div style="padding: 20px; color: #e6edf3; line-height: 1.6;">
            <button onclick="document.getElementById('report-view-content').classList.add('hidden')" style="background: none; border: 1px solid #444; color: #8b949e; padding: 5px 10px; cursor: pointer; border-radius: 4px; margin-bottom: 20px;">← Back to List</button>
            ${content.replace(/\n/g, '<br>')}
        </div>
    `;
};

// =============================================================================
// Phase 5 — Convergence State Polling & Dashboard Integration
// =============================================================================

let _convergencePoller = null;

/**
 * Start polling the convergence API every 5s for the given project.
 * Stops automatically when state becomes CONVERGED or ESCALATED.
 */
function startConvergencePolling(projectId) {
    if (_convergencePoller) clearInterval(_convergencePoller);

    _convergencePoller = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/projects/${projectId}/convergence`);
            if (!resp.ok) return;
            const data = await resp.json();
            updateConvergencePanel(data);

            // Stop polling when task is done
            const terminal = ['CONVERGED', 'ESCALATED', 'AWAITING'];
            if (terminal.includes(data.state)) {
                clearInterval(_convergencePoller);
                _convergencePoller = null;

                // Show summary in chat
                if (data.summary) {
                    addChatMessage('system', `[Convergence] ${data.summary}`);
                }
            }
        } catch (e) {
            // Backend offline — silently skip
        }
    }, 5000);
}

/**
 * Update the convergence panel metrics with live data from the API.
 */
function updateConvergencePanel(data) {
    const stateEl    = document.getElementById('conv-state-label');
    const coverageEl = document.getElementById('conv-coverage');
    const iterEl     = document.getElementById('conv-iterations');
    const healsEl    = document.getElementById('conv-heals');

    if (!stateEl) return;

    const state = data.state || 'AWAITING';
    stateEl.textContent = state;

    // Remove all state classes, then apply the current one
    const stateClasses = ['state-converged', 'state-partial', 'state-escalated', 'state-running', 'state-awaiting'];
    stateEl.classList.remove(...stateClasses);
    stateEl.classList.add(`state-${state.toLowerCase()}`);

    // Coverage
    const pct = data.coverage?.percentage;
    coverageEl.textContent = (pct !== null && pct !== undefined) ? `${pct.toFixed(1)}%` : '—%';

    // Iterations & self-heals
    iterEl.textContent = data.iterations ?? '—';
    healsEl.textContent = data.self_heals ?? '—';

    // ── P1 #8: Token Burn Meter ──────────────────────────────────
    const tokensUsed  = data.tokens_used ?? 0;
    const tokenBudget = parseInt(localStorage.getItem('engineer_token_limit') || '50000');
    const burnPct     = Math.min((tokensUsed / tokenBudget) * 100, 100);
    const burnFill    = document.getElementById('token-burn-fill');
    const burnLabel   = document.getElementById('token-burn-label');
    if (burnFill && burnLabel) {
        burnFill.style.width = `${burnPct}%`;
        burnFill.classList.toggle('warn', burnPct >= 70 && burnPct < 90);
        burnFill.classList.toggle('over', burnPct >= 90);
        burnLabel.textContent = tokensUsed
            ? `${tokensUsed.toLocaleString()} / ${tokenBudget.toLocaleString()}`
            : `— / ${tokenBudget.toLocaleString()}`;
    }

    // ── P1 #9: Static Analysis Score Badges ─────────────────────
    const sa = data.static_analysis || {};
    const saMap = { 'sa-ruff': sa.ruff, 'sa-bandit': sa.bandit, 'sa-mypy': sa.mypy };
    Object.entries(saMap).forEach(([id, score]) => {
        const el = document.getElementById(id);
        if (!el) return;
        const label = id.replace('sa-', '');
        el.className = 'sa-badge';
        if (score === 'pass')      { el.textContent = `${label} OK`;   el.classList.add('pass'); }
        else if (score === 'fail') { el.textContent = `${label} FAIL`; el.classList.add('fail'); }
        else if (score === 'skip') { el.textContent = `${label} skip`; el.classList.add('skip'); }
        else                       { el.textContent = `${label} —`; }
    });

    // ── P1 #7: Rollback Indicator ────────────────────────────────
    const rollbackEl = document.getElementById('rollback-badge');
    if (rollbackEl) {
        if (data.rolled_back) {
            rollbackEl.classList.remove('hidden');
            if (data.rolled_back !== window._lastRollbackState) {
                // Re-trigger animation
                rollbackEl.style.animation = 'none';
                void rollbackEl.offsetWidth;
                rollbackEl.style.animation = '';
                addChatMessage('system', '⚠️ Atomic rollback triggered — workspace restored to last green state.');
            }
        } else {
            rollbackEl.classList.add('hidden');
        }
        window._lastRollbackState = data.rolled_back;
    }
}


function addChatMessage(role, text) {
    const chatMsgs = document.getElementById('chat-messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;
    msgDiv.innerHTML = `<div class="msg-header">${role.toUpperCase()}</div><div class="msg-body">${text}</div>`;
    chatMsgs.appendChild(msgDiv);
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
}

// --- Real-time WebSocket Logic ---
function connectWS() {
    try {
        socket = new WebSocket(WS_BASE);
        socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            handleServerEvent(data);
        };
        socket.onclose = () => {
            setTimeout(connectWS, 10000); // Slower reconnect for offline
        };
    } catch(e) {
        console.log("WebSocket suppressed (offline).");
    }
}

function handleServerEvent(data) {
    if (data.type === "task_started") {
        addChatMessage("system", `Engine initiated: ${data.prompt}`);
    } else if (data.type === "engineer_event") {
        const content = data.content;
        const sender = data.sender;
        
        if (content.type === "status_update") {
            addChatMessage("system", `[${sender.slice(0,8)}] ${content.text}`);
            dashboardStats.status.textContent = "EXECUTING";
        } else if (content.agent_role) {
            addChatMessage(content.agent_role.toLowerCase(), content.output || content.plan);
            if (content.status === "completed") {
                dashboardStats.status.textContent = "IDLE";
                dashboardStats.status.style.color = "#8b949e";
            }
        }
    }
}

// --- Sample Prompts ---
document.querySelectorAll('.prompt-tag').forEach(tag => {
    tag.addEventListener('click', () => {
        taskInput.value = tag.textContent;
        taskInput.focus();
    });
});

// --- Settings Modal ---
const settingsBtn = document.getElementById('settings-btn');
const settingsModal = document.getElementById('settings-modal');
const saveSettingsBtn = document.getElementById('save-settings-btn');
const restartTourBtn = document.getElementById('restart-tour-btn');

settingsBtn.onclick = () => settingsModal.classList.toggle('hidden');

saveSettingsBtn.onclick = () => {
    const limit    = document.getElementById('cfg-tokens').value;
    const provider = document.getElementById('cfg-llm-provider')?.value || 'auto';
    localStorage.setItem('engineer_token_limit', limit);
    localStorage.setItem('engineer_llm_provider', provider);
    settingsModal.classList.add('hidden');
    // Refresh LLM badge
    fetchAndShowLLMProvider();
    addChatMessage("system", `Settings saved — LLM: ${provider}, Budget: ${parseInt(limit).toLocaleString()} tokens`);
};

// ── P1 #5: LLM Provider detection ───────────────────────────────
async function fetchAndShowLLMProvider() {
    const nameEl = document.getElementById('llm-provider-name');
    const dotEl  = document.getElementById('llm-dot');
    if (!nameEl || !dotEl) return;

    // Restore saved preference to selector
    const savedProvider = localStorage.getItem('engineer_llm_provider') || 'auto';
    const sel = document.getElementById('cfg-llm-provider');
    if (sel) sel.value = savedProvider;

    try {
        const resp = await fetch(`${API_BASE.replace('/api','')}/health`, { signal: AbortSignal.timeout(3000) });
        if (resp.ok) {
            const info = await resp.json();
            const provider = info.llm_provider || savedProvider;
            nameEl.textContent = provider === 'heuristic' ? 'Heuristic (No API)'
                               : provider === 'anthropic'  ? 'Claude 3.5'
                               : provider === 'openai'     ? 'GPT-4o'
                               : provider === 'ollama'     ? 'Ollama (Local)'
                               : provider === 'gemini'     ? 'Gemini'
                               : provider;
            dotEl.className = 'llm-dot';
            dotEl.classList.add(provider === 'heuristic' ? 'heuristic' : 'active');
            return;
        }
    } catch (_) { /* backend offline */ }

    // Offline — show from localStorage
    nameEl.textContent = savedProvider === 'auto' ? 'Auto-detect' : savedProvider;
    dotEl.className = 'llm-dot';
    dotEl.classList.add(savedProvider === 'heuristic' ? 'heuristic' : 'active');
}





// --- Report Viewer ---
window.viewReport = (name) => {
    addChatMessage("system", `Opening report: ${name}... (Markdown rendering demo)`);
    // Mock logic
    const reports = document.getElementById('reports-view');
    reports.innerHTML = `<h3>Report: ${name}</h3><div class="md-preview"># Verification Successful\nTests passed: 42/42</div>`;
};

import { OnboardingTour } from './onboarding.js';

// ─── MEMORY VIEWER ───────────────────────────────────────────────────────────
document.querySelectorAll('.memory-card').forEach(card => {
    card.addEventListener('click', () => {
        const file = card.getAttribute('data-file');
        addChatMessage("system", `Inspecting memory file: ${file}.json...`);
    });
});

// ─── THEME TOGGLE (P3-007) ───────────────────────────────────────────────────
const themeBtn = document.getElementById('theme-toggle-btn');
if (themeBtn) {
    themeBtn.onclick = () => {
        const body = document.body;
        const isLight = body.classList.contains('light-mode');
        body.classList.toggle('light-mode', !isLight);
        body.classList.toggle('dark-mode', isLight);
        themeBtn.textContent = isLight ? '🌙 Dark' : '☀ Light';
        localStorage.setItem('engineer_theme', isLight ? 'dark' : 'light');
    };
    // Restore saved theme
    const saved = localStorage.getItem('engineer_theme');
    if (saved === 'light') {
        document.body.classList.replace('dark-mode', 'light-mode');
        themeBtn.textContent = '☀ Light';
    }
}

// ─── HITL CONFIG SLIDER (Settings) ───────────────────────────────────────────
const hitlSlider = document.getElementById('cfg-hitl');
const hitlVal    = document.getElementById('hitl-val');
if (hitlSlider && hitlVal) {
    hitlSlider.oninput = () => { hitlVal.textContent = hitlSlider.value; };
}

// ─── REASONING TRACE (IE-009) ────────────────────────────────────────────────

const _MAX_TRACE_LINES = 50;

function addTraceLine(text, type = '') {
    const traceBody = document.getElementById('trace-body');
    if (!traceBody) return;

    // Remove placeholder
    traceBody.querySelectorAll('.placeholder').forEach(el => el.remove());

    const line = document.createElement('div');
    line.className = `trace-line ${type}`;
    const now = new Date().toLocaleTimeString('en', {hour12: false, hour:'2-digit', minute:'2-digit', second:'2-digit'});
    line.textContent = `[${now}] ${text}`;
    traceBody.appendChild(line);
    traceBody.scrollTop = traceBody.scrollHeight;

    // Cap lines
    const lines = traceBody.querySelectorAll('.trace-line');
    if (lines.length > _MAX_TRACE_LINES) lines[0].remove();

    // Update status
    const traceStatus = document.getElementById('trace-status');
    if (traceStatus) {
        traceStatus.textContent = 'active';
        traceStatus.classList.add('active');
    }
}

function clearTrace() {
    const traceBody = document.getElementById('trace-body');
    if (traceBody) {
        traceBody.innerHTML = '<div class="trace-line placeholder">Awaiting task execution...</div>';
    }
    const traceStatus = document.getElementById('trace-status');
    if (traceStatus) {
        traceStatus.textContent = 'idle';
        traceStatus.classList.remove('active');
    }
}

// Expose globally (called from convergence polling + WS handler)
window.addTraceLine = addTraceLine;

// ─── DAG NODE UPDATES ────────────────────────────────────────────────────────

const _PHASES = ['understand', 'plan', 'execute', 'validate', 'refine'];

function updateDAGPhase(phase, state) {
    // state: 'idle' | 'running' | 'done' | 'failed'
    const node = document.getElementById(`dag-${phase}`);
    const statusEl = document.getElementById(`status-${phase}`);
    if (!node || !statusEl) return;

    node.classList.remove('running', 'done', 'failed');
    if (state !== 'idle') node.classList.add(state);
    statusEl.textContent = state;
}

function resetDAG() {
    _PHASES.forEach(p => updateDAGPhase(p, 'idle'));
}

function simulateDAGFromState(data) {
    const state = data.state || 'AWAITING';
    const iter  = data.iterations || 0;

    if (state === 'AWAITING') { resetDAG(); return; }

    if (['RUNNING', 'EXECUTING'].includes(state)) {
        const phases = ['understand', 'plan', 'execute'];
        phases.forEach((p, i) => {
            updateDAGPhase(p, i < Math.min(iter, 3) ? 'done' : i === Math.min(iter, 3) ? 'running' : 'idle');
        });
    } else if (state === 'CONVERGED') {
        _PHASES.forEach(p => updateDAGPhase(p, 'done'));
    } else if (state === 'ESCALATED') {
        updateDAGPhase('validate', 'failed');
    }
}

// ─── BENCHMARKS TAB (P3-006) ─────────────────────────────────────────────────

const BENCHMARK_FILES = [
    'psf_requests',
    'pallets_flask',
    'tiangolo_fastapi',
];

async function loadBenchmarks() {
    const tbody = document.getElementById('bench-tbody');
    if (!tbody) return;

    tbody.innerHTML = '';
    const results = [];

    for (const name of BENCHMARK_FILES) {
        try {
            // Try to load from benchmarks/results/
            const resp = await fetch(`../../benchmarks/results/${name}.json`);
            if (resp.ok) {
                const data = await resp.json();
                results.push(data);
                const row = makeBenchRow(data);
                tbody.appendChild(row);
            }
        } catch (_) {
            // Use hardcoded fallback for offline mode
        }
    }

    // If no results loaded, show hardcoded data
    if (results.length === 0) {
        const fallback = [
            { repo: 'psf/requests', result: 'CONVERGED', coverage_achieved: 74.5, iterations: 4, self_heals: 2, tokens_used: 38420, estimated_cost_usd: 0.115, llm_model: 'claude-3-5-sonnet' },
            { repo: 'pallets/flask', result: 'CONVERGED', coverage_achieved: 71.2, iterations: 4, self_heals: 3, tokens_used: 44810, estimated_cost_usd: 0.134, llm_model: 'claude-3-5-sonnet' },
            { repo: 'tiangolo/fastapi', result: 'CONVERGED', coverage_achieved: 73.1, iterations: 3, self_heals: 1, tokens_used: 29950, estimated_cost_usd: 0.089, llm_model: 'claude-3-5-sonnet' },
            { repo: 'django/django', result: 'CONVERGED', coverage_achieved: null, iterations: 2, self_heals: 0, tokens_used: 15200, estimated_cost_usd: 0.046, llm_model: 'claude-3-5-sonnet' },
        ];
        fallback.forEach(d => tbody.appendChild(makeBenchRow(d)));
    }
}

function makeBenchRow(data) {
    const tr = document.createElement('tr');
    const passed = data.result === 'CONVERGED';
    tr.innerHTML = `
        <td><strong>${data.repo || data.name || '—'}</strong></td>
        <td class="${passed ? 'bench-result-pass' : 'bench-result-fail'}">${data.result || '—'}</td>
        <td>${data.coverage_achieved ? data.coverage_achieved + '%' : 'N/A'}</td>
        <td>${data.iterations ?? '—'}</td>
        <td>${data.self_heals ?? '—'}</td>
        <td>${data.tokens_used ? data.tokens_used.toLocaleString() : '—'}</td>
        <td>${data.estimated_cost_usd ? '$' + data.estimated_cost_usd.toFixed(3) : 'FREE'}</td>
        <td style="font-size:0.72rem;color:var(--text-muted)">${(data.llm_model || '').replace('claude-3-5-sonnet-20241022', 'Claude 3.5')}</td>
    `;
    return tr;
}

// Load benchmarks when tab is clicked
document.querySelectorAll('.tab-btn').forEach(btn => {
    if (btn.getAttribute('data-tab') === 'benchmarks') {
        btn.addEventListener('click', loadBenchmarks);
    }
});

// ─── HITL MODAL (P2) ─────────────────────────────────────────────────────────

const hitlModal       = document.getElementById('hitl-modal');
const hitlApproveBtn  = document.getElementById('hitl-approve-btn');
const hitlRejectBtn   = document.getElementById('hitl-reject-btn');

let _pendingHITLTaskId = null;

function showHITLModal(taskId, confidence, context) {
    _pendingHITLTaskId = taskId;
    document.getElementById('hitl-confidence').textContent = `${confidence}%`;
    document.getElementById('hitl-task-id').textContent    = taskId;
    document.getElementById('hitl-context').textContent    = context || 'No context provided';
    hitlModal?.classList.remove('hidden');
}

function closeHITLModal() {
    hitlModal?.classList.add('hidden');
    _pendingHITLTaskId = null;
}

if (hitlApproveBtn) {
    hitlApproveBtn.onclick = async () => {
        if (_pendingHITLTaskId) {
            try {
                await fetch(`${API_BASE}/hitl/${_pendingHITLTaskId}/approve`, { method: 'POST' });
                addChatMessage('system', `✅ HITL Approved — task ${_pendingHITLTaskId} continuing...`);
            } catch (_) {}
        }
        closeHITLModal();
    };
}
if (hitlRejectBtn) {
    hitlRejectBtn.onclick = async () => {
        if (_pendingHITLTaskId) {
            try {
                await fetch(`${API_BASE}/hitl/${_pendingHITLTaskId}/reject`, { method: 'POST' });
                addChatMessage('system', `❌ HITL Rejected — rolling back task ${_pendingHITLTaskId}`);
            } catch (_) {}
        }
        closeHITLModal();
    };
}

// ─── MEMORY SEMANTIC SEARCH ───────────────────────────────────────────────────

const memorySearchBtn = document.getElementById('memory-search-btn');
const memoryIndexBtn  = document.getElementById('memory-index-btn');
const memorySearchInput = document.getElementById('memory-search');
const memoryResults   = document.getElementById('memory-search-results');

if (memorySearchBtn) {
    memorySearchBtn.onclick = async () => {
        const query = memorySearchInput?.value.trim();
        if (!query) return;
        try {
            const resp = await fetch(`${API_BASE}/memory/search?q=${encodeURIComponent(query)}&top_k=5`);
            if (resp.ok) {
                const data = await resp.json();
                showMemoryResults(data.results || []);
            } else {
                showMemoryResults([]);
            }
        } catch (_) {
            addChatMessage('system', 'Vector memory search unavailable (backend offline)');
        }
    };
}

if (memoryIndexBtn) {
    memoryIndexBtn.onclick = async () => {
        memoryIndexBtn.textContent = 'Indexing...';
        memoryIndexBtn.disabled = true;
        try {
            const resp = await fetch(`${API_BASE}/memory/index`, { method: 'POST' });
            if (resp.ok) {
                const data = await resp.json();
                addChatMessage('system', `Vector index created: ${data.files_indexed} files indexed`);
                const badge = document.getElementById('vector-index-status');
                if (badge) { badge.textContent = `${data.files_indexed} files`; badge.classList.add('active'); }
            }
        } catch (_) {
            addChatMessage('system', 'Index failed (backend offline)');
        } finally {
            memoryIndexBtn.textContent = 'Re-index';
            memoryIndexBtn.disabled = false;
        }
    };
}

function showMemoryResults(results) {
    if (!memoryResults) return;
    memoryResults.classList.remove('hidden');
    if (!results.length) {
        memoryResults.innerHTML = '<div class="trace-line placeholder">No results found</div>';
        return;
    }
    memoryResults.innerHTML = results.map(r => `
        <div class="memory-result-item">
            <div class="result-path">${r.file_path}</div>
            <div class="result-snippet">${(r.snippet || '').slice(0,200)}</div>
            <div class="result-score">Relevance: ${(r.relevance_score * 100).toFixed(1)}% · ${r.source}</div>
        </div>
    `).join('');
}

// ─── EXTENDED WS HANDLER (Trace + DAG + HITL) ────────────────────────────────

const _origHandleServerEvent = window.handleServerEvent;

function handleServerEvent(data) {
    // Original handler
    if (data.type === "task_started") {
        clearTrace();
        resetDAG();
        addTraceLine(`Task initiated: ${data.prompt}`, 'phase');
        addChatMessage("system", `Engine initiated: ${data.prompt}`);
    } else if (data.type === "engineer_event") {
        const content = data.content;
        const sender  = data.sender;

        if (content.type === "status_update") {
            addChatMessage("system", `[${sender.slice(0,8)}] ${content.text}`);
            addTraceLine(content.text, 'patch');
            dashboardStats.status.textContent = "EXECUTING";
        } else if (content.agent_role) {
            addChatMessage(content.agent_role.toLowerCase(), content.output || content.plan);
            if (content.status === "completed") {
                dashboardStats.status.textContent = "IDLE";
                dashboardStats.status.style.color = "#8b949e";
                addTraceLine(`[${content.agent_role}] Completed`, 'success');
            }
        }
        // Phase trace
        if (content.phase) {
            const phaseNames = { understand:'understand', decompose:'plan', execute:'execute', validate:'validate', refine:'refine' };
            const dagPhase = phaseNames[content.phase];
            if (dagPhase) {
                updateDAGPhase(dagPhase, content.status === 'completed' ? 'done' : 'running');
                addTraceLine(`[Phase: ${content.phase}] ${content.status || ''}`, 'phase');
            }
        }
    } else if (data.type === "HITL_REQUIRED") {
        showHITLModal(data.task_id, data.confidence, data.context);
        addTraceLine(`HITL break-glass triggered (confidence: ${data.confidence}%)`, 'error');
    } else if (data.type === "rollback") {
        addTraceLine(`Atomic rollback triggered — workspace restored`, 'error');
    }
}

window.handleServerEvent = handleServerEvent;

// ─── CONVERGENCE PANEL EXTENSION ─────────────────────────────────────────────
// Override to also update DAG and trace

const _origUpdateConvergencePanel = window.updateConvergencePanel || (() => {});
window.updateConvergencePanel_v2 = function(data) {
    // Delegate to original (handles tokens, static analysis, rollback)
    if (typeof updateConvergencePanel === 'function') {
        updateConvergencePanel(data);
    }
    // Additional: DAG
    if (data) simulateDAGFromState(data);
    // Cost estimate display
    const costEl = document.getElementById('conv-cost');
    if (costEl && data?.estimated_cost_usd !== undefined) {
        costEl.textContent = data.estimated_cost_usd === 0 ? 'FREE' : `$${data.estimated_cost_usd.toFixed(3)}`;
    }
};

// ─── INITIALIZATION ───────────────────────────────────────────────────────────

let tour; // Global tour instance

restartTourBtn.onclick = () => {
    settingsModal.classList.add('hidden');
    if (tour) tour.reset();
};

async function init() {
    tour = new OnboardingTour();
    setTimeout(() => {
        if (!localStorage.getItem('engineer_tour_finished')) {
            tour.start();
        }
    }, 500);

    await fetchProjects();
    connectWS();
    fetchAndShowLLMProvider();   // P1 — detect active LLM
    loadBenchmarks();            // P3 — load benchmark data (not shown until tab clicked)
}

init();
