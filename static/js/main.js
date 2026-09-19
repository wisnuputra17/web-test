/* main.js */
const socket = io();
let autoRefresh = true;

// Elements
const systemMetrics = {
    cpu: document.getElementById('sys-cpu'),
    mem: document.getElementById('sys-mem'),
    disk: document.getElementById('sys-disk'),
};

const statusIndicators = {
    hermes: {
        status: document.getElementById('hermes-status'),
        last: document.getElementById('hermes-last')
    },
    ollama: {
        status: document.getElementById('ollama-status'),
        models: document.getElementById('ollama-models'),
        last: document.getElementById('ollama-last')
    },
    n8n: {
        status: document.getElementById('n8n-status'),
        last: document.getElementById('n8n-last')
    }
};

const eventLog = document.getElementById('event-log');
const eventCount = document.getElementById('event-count');

// Button handlers
document.getElementById('auto-refresh-btn').addEventListener('click', function() {
    autoRefresh = !autoRefresh;
    this.textContent = autoRefresh ? 'Disable Auto-Refresh' : 'Enable Auto-Refresh';
    if (!autoRefresh) {
        socket.disconnect();
    }
});

document.getElementById('refresh-status').addEventListener('click', function() {
    socket.emit('request_refresh');
});

// Spawn Hermes Agent
document.getElementById('spawn-hermes-agent').addEventListener('click', function() {
    fetch('/api/hermes/delegate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            goal: 'Monitor agent activity',
            context: 'Initial setup for web test'
        })
    })
    .then(response => response.json())
    .then(data => {
        alert('Agent spawned: ' + data.task_id);
        socket.emit('request_refresh');
    })
    .catch(err => {
        console.error('Error:', err);
        alert('Failed to spawn agent: ' + err.message);
    });
});

// Auto-refresh interval
if (autoRefresh) {
    setInterval(() => {
        socket.emit('request_refresh');
    }, 10000);
}

// Socket.IO event handlers
socket.on('connect', function() {
    console.log('Connected to server');
    socket.emit('request_refresh');
});

socket.on('state_sync', function(data) {
    updateSystemMetrics(data.system);
    updateAgentStatus(data);
    updateEventLog(data.events);
});

socket.on('new_event', function(event) {
    addEventToLog(event);
    updateEventCount();
});

socket.on('system_update', function(data) {
    updateSystemMetrics(data);
});


function updateSystemMetrics(data) {
    systemMetrics.cpu.textContent = data.cpu;
    systemMetrics.mem.textContent = data.memory.percent;
    systemMetrics.disk.textContent = data.disk.percent;
}

function updateAgentStatus(data) {
    // Hermes
    setIndicator(statusIndicators.hermes, data.hermes);
    // Ollama
    setIndicator(statusIndicators.ollama, data.ollama);
    if (data.ollama.models && data.ollama.models.length > 0) {
        statusIndicators.ollama.models.innerHTML = data.ollama.models
            .map(m => `<span class="badge badge-info me-1 mb-1">${m.name}</span>`)
            .join('');
    }
    // N8N
    setIndicator(statusIndicators.n8n, data.n8n);
}

function setIndicator(container, agentData) {
    let statusClass = 'warning';
    if (agentData.status === 'running') statusClass = 'running';
    else if (['error', 'timeout', 'not_installed', 'not_running'].includes(agentData.status)) {
        statusClass = 'error';
    }
    container.status.className = 'status-indicator ' + statusClass;
    container.last.textContent = agentData.last_seen || '--';
}

function updateEventLog(events) {
    eventLog.innerHTML = '';
    if (events.length === 0) {
        eventLog.innerHTML = '<div class="placeholder">No events yet</div>';
        return;
    }
    events.forEach(event => addEventToLog(event));
    updateEventCount();
}

function updateEventCount() {
    eventCount.textContent = 'Events: ' + (window.agentEventsCount || 0);
}

function addEventToLog(event) {
    const levelClass = event.level === 'error' ? 'badge-error' :
                       event.level === 'warning' ? 'badge-warning' : 'badge-info';

    const eventDiv = document.createElement('div');
    eventDiv.className = 'event';
    eventDiv.innerHTML = `
        <span class="${levelClass}">${event.level}</span>
        <strong>[${event.type}]</strong>
        <span class="text-muted">${event.source}</span> —
        ${event.message}
        <small class="text-muted float-end">${event.timestamp}</small>
    `;
    eventLog.prepend(eventDiv);

    // Keep log trimmed
    while (eventLog.children.length > 500) {
        eventLog.removeChild(eventLog.lastChild);
    }
}
