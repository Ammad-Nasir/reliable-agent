from fastapi import APIRouter
from fastapi.responses import HTMLResponse

trace_viewer_router = APIRouter()

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent Trace Viewer & Supervisor Console</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
  <style>
    :root {
      --bg-dark: #0f172a;
      --card-bg: #1e293b;
      --border-color: #334155;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
    }
    body {
      background-color: var(--bg-dark);
      color: #f8fafc;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      height: 100vh;
      overflow: hidden;
    }
    .sidebar {
      background-color: #0b1120;
      border-right: 1px solid var(--border-color);
      height: 100vh;
      overflow-y: auto;
    }
    .main-panel {
      height: 100vh;
      overflow-y: auto;
      padding: 24px;
    }
    .run-item {
      padding: 12px 16px;
      border-bottom: 1px solid #1e293b;
      cursor: pointer;
      transition: background 0.15s;
    }
    .run-item:hover, .run-item.active {
      background-color: #1e293b;
      border-left: 3px solid var(--accent);
    }
    .trace-card {
      background-color: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      margin-bottom: 16px;
      padding: 16px;
    }
    .node-badge-plan { background-color: #0284c7; }
    .node-badge-act { background-color: #d97706; }
    .node-badge-reflect { background-color: #7c3aed; }
    .badge-PENDING_APPROVAL { background-color: #f59e0b; color: #000; font-weight: 600; }
    .badge-COMPLETED { background-color: #10b981; }
    .badge-LOOP_DETECTED { background-color: #ec4899; }
    .badge-STEP_LIMIT_EXCEEDED { background-color: #ef4444; }
    .badge-RUNNING { background-color: #3b82f6; }
    pre {
      background: #0b1120;
      padding: 10px;
      border-radius: 6px;
      color: #38bdf8;
      font-size: 13px;
      border: 1px solid #1e293b;
      max-height: 250px;
      overflow: auto;
    }
    .hitl-banner {
      background: linear-gradient(135deg, #78350f, #451a03);
      border: 1px solid #f59e0b;
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 24px;
    }
  </style>
</head>
<body>
<div class="container-fluid h-100">
  <div class="row h-100">
    <!-- Sidebar: Run History -->
    <div class="col-md-4 col-lg-3 sidebar p-0 d-flex flex-column">
      <div class="p-3 border-bottom border-secondary">
        <h5 class="mb-1 text-light"><i class="bi bi-cpu text-info"></i> Agent Runs</h5>
        <small class="text-muted">Observability & HITL Console</small>
        <button class="btn btn-sm btn-outline-info w-100 mt-2" onclick="showNewRunModal()">
          <i class="bi bi-plus-circle"></i> New Task
        </button>
      </div>
      <div id="runsList" class="flex-grow-1 overflow-auto">
        <div class="text-center p-4 text-muted">Loading runs...</div>
      </div>
    </div>

    <!-- Main View: Trace & Step Inspector -->
    <div class="col-md-8 col-lg-9 main-panel">
      <div id="noSelection" class="text-center text-muted mt-5">
        <i class="bi bi-diagram-3 fs-1 d-block mb-3"></i>
        <h4>Select an Agent Run</h4>
        <p>Choose an execution from the left sidebar to view thoughts, tool calls, and step replay traces.</p>
      </div>

      <div id="runDetails" style="display: none;">
        <!-- Header Info -->
        <div class="d-flex justify-content-between align-items-center mb-3 pb-3 border-bottom border-secondary">
          <div>
            <h4 id="viewRunId" class="mb-1 text-white"></h4>
            <div id="viewUserQuery" class="text-info fs-6"></div>
          </div>
          <div class="text-end">
            <span id="viewStatusBadge" class="badge p-2 fs-6"></span>
            <div class="text-muted small mt-1" id="viewMetrics"></div>
          </div>
        </div>

        <!-- HITL Approval Banner (Conditional) -->
        <div id="hitlBanner" class="hitl-banner" style="display: none;">
          <h5 class="text-warning"><i class="bi bi-shield-exclamation"></i> Supervisor Approval Required</h5>
          <p id="hitlReason" class="mb-2"></p>
          <div id="hitlDetails" class="mb-3 font-monospace small bg-black bg-opacity-50 p-2 rounded"></div>
          <div class="d-flex gap-2">
            <input type="text" id="hitlComment" class="form-control form-control-sm bg-dark text-white border-secondary" placeholder="Optional supervisor justification note..." style="max-width: 320px;">
            <button class="btn btn-sm btn-success px-3" onclick="submitDecision(true)"><i class="bi bi-check-lg"></i> Approve Action</button>
            <button class="btn btn-sm btn-danger px-3" onclick="submitDecision(false)"><i class="bi bi-x-lg"></i> Reject</button>
          </div>
        </div>

        <!-- Final Response Box -->
        <div id="finalResponseBox" class="card bg-dark border-info mb-4" style="display: none;">
          <div class="card-body">
            <h6 class="text-info mb-2"><i class="bi bi-chat-left-dots"></i> Final Agent Response</h6>
            <div id="finalResponseText" class="text-light"></div>
          </div>
        </div>

        <!-- Step Trace Timeline -->
        <h5 class="mb-3 text-secondary"><i class="bi bi-clock-history"></i> Execution Step Trace</h5>
        <div id="stepsTimeline"></div>
      </div>
    </div>
  </div>
</div>

<!-- New Run Modal -->
<div class="modal fade" id="newRunModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content bg-dark text-light border-secondary">
      <div class="modal-header border-secondary">
        <h5 class="modal-title">Trigger New Agent Run</h5>
        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <div class="mb-3">
          <label class="form-label text-muted">User Request / Customer Support Query</label>
          <textarea id="newRunQuery" class="form-control bg-black text-light border-secondary" rows="4" placeholder="e.g. My order ORD-8821 was delayed by 6 days. Can I get a refund of $60?"></textarea>
        </div>
      </div>
      <div class="modal-footer border-secondary">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
        <button type="button" class="btn btn-info" onclick="createRun()">Start Agent</button>
      </div>
    </div>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
let currentRunId = null;
let currentPendingApproval = null;
let newRunModalInstance = null;

async function fetchRuns() {
  try {
    const res = await fetch('/api/runs');
    const runs = await res.json();
    const list = document.getElementById('runsList');
    if (runs.length === 0) {
      list.innerHTML = '<div class="text-center p-4 text-muted">No runs found. Start one above!</div>';
      return;
    }
    list.innerHTML = runs.map(r => `
      <div class="run-item ${r.run_id === currentRunId ? 'active' : ''}" onclick="selectRun('${r.run_id}')">
        <div class="d-flex justify-content-between align-items-center mb-1">
          <strong class="font-monospace text-info">${r.run_id}</strong>
          <span class="badge badge-${r.status}">${r.status}</span>
        </div>
        <div class="text-truncate small text-light mb-1">${escapeHtml(r.user_query)}</div>
        <div class="d-flex justify-content-between text-muted" style="font-size: 11px;">
          <span>${r.total_steps} steps</span>
          <span>$${r.total_cost_usd.toFixed(4)}</span>
        </div>
      </div>
    `).join('');
  } catch(e) {
    console.error(e);
  }
}

async function selectRun(runId) {
  currentRunId = runId;
  fetchRuns();
  document.getElementById('noSelection').style.display = 'none';
  document.getElementById('runDetails').style.display = 'block';

  const [runRes, stepsRes, appsRes] = await Promise.all([
    fetch(`/api/runs/${runId}`).then(r => r.json()),
    fetch(`/api/runs/${runId}/steps`).then(r => r.json()),
    fetch(`/api/approvals?status=PENDING`).then(r => r.json())
  ]);

  document.getElementById('viewRunId').innerText = runRes.run_id;
  document.getElementById('viewUserQuery').innerText = `"${runRes.user_query}"`;
  
  const statusBadge = document.getElementById('viewStatusBadge');
  statusBadge.className = `badge badge-${runRes.status} p-2 fs-6`;
  statusBadge.innerText = runRes.status;

  document.getElementById('viewMetrics').innerHTML = `
    <span>Steps: <strong>${runRes.total_steps}</strong></span> | 
    <span>Tokens: <strong>${runRes.total_input_tokens + runRes.total_output_tokens}</strong></span> | 
    <span>Cost: <strong>$${runRes.total_cost_usd.toFixed(4)}</strong></span>
  `;

  // Final Response
  const finalBox = document.getElementById('finalResponseBox');
  if (runRes.final_response) {
    finalBox.style.display = 'block';
    document.getElementById('finalResponseText').innerText = runRes.final_response;
  } else {
    finalBox.style.display = 'none';
  }

  // HITL Approval Banner
  const pending = appsRes.find(a => a.run_id === runId);
  const banner = document.getElementById('hitlBanner');
  if (pending && runRes.status === 'PENDING_APPROVAL') {
    currentPendingApproval = pending;
    banner.style.display = 'block';
    document.getElementById('hitlReason').innerText = pending.risk_reason;
    document.getElementById('hitlDetails').innerText = `${pending.tool_name}(${JSON.stringify(pending.tool_input, null, 2)})`;
  } else {
    currentPendingApproval = null;
    banner.style.display = 'none';
  }

  // Steps Timeline
  const timeline = document.getElementById('stepsTimeline');
  if (stepsRes.length === 0) {
    timeline.innerHTML = '<div class="text-muted">No step traces recorded yet.</div>';
    return;
  }

  timeline.innerHTML = stepsRes.map(s => `
    <div class="trace-card">
      <div class="d-flex justify-content-between align-items-center mb-2">
        <div>
          <span class="badge node-badge-${s.node_name} text-uppercase px-2 py-1 me-2">${s.node_name}</span>
          <span class="text-muted small">Step #${s.step_number}</span>
        </div>
        <div class="text-muted small">
          <i class="bi bi-stopwatch"></i> ${s.latency_ms}ms | 
          <i class="bi bi-coin"></i> ${s.input_tokens + s.output_tokens} tok
        </div>
      </div>
      
      ${s.thought ? `<div class="mb-2"><strong class="text-secondary small">THOUGHT:</strong> <span class="text-light">${escapeHtml(s.thought)}</span></div>` : ''}

      ${s.tool_name ? `
        <div class="mb-2">
          <span class="badge bg-secondary mb-1">TOOL: ${s.tool_name}</span>
          <div class="row">
            <div class="col-md-6">
              <small class="text-muted">Input Arguments:</small>
              <pre>${escapeHtml(JSON.stringify(s.tool_input, null, 2))}</pre>
            </div>
            <div class="col-md-6">
              <small class="text-muted">Tool Output:</small>
              <pre>${escapeHtml(JSON.stringify(s.tool_output, null, 2))}</pre>
            </div>
          </div>
        </div>
      ` : ''}
    </div>
  `).join('');
}

async function submitDecision(approved) {
  if (!currentPendingApproval) return;
  const reason = document.getElementById('hitlComment').value.trim() || (approved ? "Approved by supervisor" : "Rejected by supervisor");
  await fetch(`/api/approvals/${currentPendingApproval.approval_id}/decision`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      approved: approved,
      reason: reason,
      reviewer: 'supervisor@enterprise.org'
    })
  });
  selectRun(currentRunId);
}

function showNewRunModal() {
  if (!newRunModalInstance) {
    newRunModalInstance = new bootstrap.Modal(document.getElementById('newRunModal'));
  }
  newRunModalInstance.show();
}

async function createRun() {
  const query = document.getElementById('newRunQuery').value.trim();
  if (!query) return;
  newRunModalInstance.hide();
  const res = await fetch('/api/runs', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({query: query, async_mode: false})
  });
  const data = await res.json();
  fetchRuns();
  if (data.run_id) {
    selectRun(data.run_id);
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

fetchRuns();
setInterval(fetchRuns, 4000);
</script>
</body>
</html>
"""

@trace_viewer_router.get("/ui", response_class=HTMLResponse)
@trace_viewer_router.get("/trace-viewer", response_class=HTMLResponse)
async def trace_viewer_page():
    """Serve the interactive HTML trace viewer & supervisor console."""
    return HTMLResponse(content=HTML_CONTENT)
