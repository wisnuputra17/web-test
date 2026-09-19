"""
AI Agent Monitoring Dashboard - web test
Monitors AI agents (Hermes, local Ollama, N8N workflows, etc.)
Author: Wisnu Putra
"""

import os
import json
import time
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from flask_socketio import SocketIO, emit
import psutil

# Configuration
BASE_DIR = Path(__file__).parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

app = Flask(__name__, static_folder="static", template_folder="templates")
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-in-prod")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# In-memory state for real-time updates
agent_state = {
    "hermes": {"status": "unknown", "last_seen": None, "metrics": {}},
    "ollama": {"status": "unknown", "last_seen": None, "models": [], "metrics": {}},
    "n8n": {"status": "unknown", "last_seen": None, "workflows": [], "executions": []},
    "system": {"cpu": 0, "memory": 0, "disk": 0, "network": {}},
    "events": [],
}

MAX_EVENTS = 500
EVENT_LOCK = threading.Lock()


def log_event(event_type: str, source: str, message: str, level: str = "info", metadata: dict = None):
    """Add event to stream and persist to file."""
    event = {
        "id": f"{int(time.time() * 1000)}",
        "timestamp": datetime.now().isoformat(),
        "type": event_type,
        "source": source,
        "message": message,
        "level": level,
        "metadata": metadata or {},
    }
    with EVENT_LOCK:
        agent_state["events"].insert(0, event)
        if len(agent_state["events"]) > MAX_EVENTS:
            agent_state["events"] = agent_state["events"][:MAX_EVENTS]

    # Persist to daily log file
    log_file = LOG_DIR / f"events_{datetime.now():%Y-%m-%d}.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(event) + "\n")

    socketio.emit("new_event", event)
    return event


def get_system_metrics():
    """Collect system resource metrics."""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    net = psutil.net_io_counters()
    return {
        "cpu": cpu,
        "memory": {"percent": mem.percent, "used_gb": round(mem.used / 1e9, 2), "total_gb": round(mem.total / 1e9, 2)},
        "disk": {"percent": disk.percent, "used_gb": round(disk.used / 1e9, 2), "total_gb": round(disk.total / 1e9, 2)},
        "network": {"sent_mb": round(net.bytes_sent / 1e6, 2), "recv_mb": round(net.bytes_recv / 1e6, 2)},
        "timestamp": datetime.now().isoformat(),
    }


def check_ollama():
    """Check Ollama status and available models."""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            models = []
            for line in lines[1:]:  # Skip header
                parts = line.split()
                if len(parts) >= 2:
                    models.append({"name": parts[0], "size": parts[1], "modified": " ".join(parts[2:]) if len(parts) > 2 else ""})
            agent_state["ollama"]["status"] = "running"
            agent_state["ollama"]["models"] = models
            agent_state["ollama"]["last_seen"] = datetime.now().isoformat()
            log_event("health_check", "ollama", f"Ollama running with {len(models)} models", "success")
        else:
            agent_state["ollama"]["status"] = "error"
            log_event("health_check", "ollama", f"Ollama error: {result.stderr}", "error")
    except FileNotFoundError:
        agent_state["ollama"]["status"] = "not_installed"
        log_event("health_check", "ollama", "Ollama not installed", "warning")
    except subprocess.TimeoutExpired:
        agent_state["ollama"]["status"] = "timeout"
        log_event("health_check", "ollama", "Ollama check timed out", "error")
    except Exception as e:
        agent_state["ollama"]["status"] = "error"
        log_event("health_check", "ollama", f"Ollama check failed: {e}", "error")


def check_hermes():
    """Check Hermes Agent status via local API or process."""
    try:
        # Check if Hermes process is running
        hermes_processes = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if "hermes" in " ".join(proc.info["cmdline"] or []).lower():
                    hermes_processes.append({"pid": proc.info["pid"], "cmd": " ".join(proc.info["cmdline"][:3])})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if hermes_processes:
            agent_state["hermes"]["status"] = "running"
            agent_state["hermes"]["processes"] = hermes_processes
            agent_state["hermes"]["last_seen"] = datetime.now().isoformat()
            log_event("health_check", "hermes", f"Hermes running ({len(hermes_processes)} processes)", "success")
        else:
            agent_state["hermes"]["status"] = "not_running"
            log_event("health_check", "hermes", "Hermes process not found", "warning")
    except Exception as e:
        agent_state["hermes"]["status"] = "error"
        log_event("health_check", "hermes", f"Hermes check failed: {e}", "error")


def check_n8n():
    """Check N8N status if running locally."""
    try:
        # Check for N8N process
        n8n_processes = []
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if "n8n" in " ".join(proc.info["cmdline"] or []).lower():
                    n8n_processes.append({"pid": proc.info["pid"], "cmd": " ".join(proc.info["cmdline"][:3])})
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        if n8n_processes:
            agent_state["n8n"]["status"] = "running"
            agent_state["n8n"]["processes"] = n8n_processes
            agent_state["n8n"]["last_seen"] = datetime.now().isoformat()
            log_event("health_check", "n8n", f"N8N running ({len(n8n_processes)} processes)", "success")
        else:
            agent_state["n8n"]["status"] = "not_running"
            log_event("health_check", "n8n", "N8N process not found", "info")
    except Exception as e:
        agent_state["n8n"]["status"] = "error"
        log_event("health_check", "n8n", f"N8N check failed: {e}", "error")


def background_monitor():
    """Background thread to periodically check all agents and system."""
    while True:
        try:
            agent_state["system"] = get_system_metrics()
            check_ollama()
            check_hermes()
            check_n8n()
            socketio.emit("system_update", agent_state["system"])
        except Exception as e:
            log_event("monitor", "system", f"Background monitor error: {e}", "error")
        time.sleep(10)  # Check every 10 seconds


# Start background monitor
monitor_thread = threading.Thread(target=background_monitor, daemon=True)
monitor_thread.start()

# Initial log
log_event("startup", "system", "AI Agent Monitor started", "success")


# ============ API ROUTES ============

@app.route("/")
def index():
    return render_template("index.html", title="web test - AI Agent Monitor")


@app.route("/api/status")
def api_status():
    return jsonify({
        "hermes": agent_state["hermes"],
        "ollama": agent_state["ollama"],
        "n8n": agent_state["n8n"],
        "system": agent_state["system"],
    })


@app.route("/api/events")
def api_events():
    limit = request.args.get("limit", 100, type=int)
    level = request.args.get("level")
    source = request.args.get("source")
    events = agent_state["events"]
    if level:
        events = [e for e in events if e["level"] == level]
    if source:
        events = [e for e in events if e["source"] == source]
    return jsonify(events[:limit])


@app.route("/api/events/stream")
def api_events_stream():
    """Server-Sent Events stream for real-time events."""
    def event_stream():
        last_index = 0
        while True:
            with EVENT_LOCK:
                if last_index < len(agent_state["events"]):
                    for event in agent_state["events"][last_index:]:
                        yield f"data: {json.dumps(event)}\n\n"
                    last_index = len(agent_state["events"])
            time.sleep(1)
    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/api/ollama/generate", methods=["POST"])
def api_ollama_generate():
    """Proxy to Ollama generate endpoint for testing."""
    data = request.get_json() or {}
    model = data.get("model", "llama3.2:3b")
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "prompt required"}), 400

    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=60,
        )
        log_event("api_call", "ollama", f"Generate: {model}", "info", {"prompt": prompt[:100], "success": result.returncode == 0})
        if result.returncode == 0:
            return jsonify({"response": result.stdout.strip()})
        return jsonify({"error": result.stderr}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "timeout"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ollama/chat", methods=["POST"])
def api_ollama_chat():
    """Proxy to Ollama chat endpoint."""
    data = request.get_json() or {}
    model = data.get("model", "llama3.2:3b")
    messages = data.get("messages", [])
    if not messages:
        return jsonify({"error": "messages required"}), 400

    try:
        import requests
        resp = requests.post(
            "http://localhost:11434/api/chat",
            json={"model": model, "messages": messages, "stream": False},
            timeout=60,
        )
        log_event("api_call", "ollama", f"Chat: {model}", "info", {"messages": len(messages), "success": resp.ok})
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/hermes/delegate", methods=["POST"])
def api_hermes_delegate():
    """Trigger a Hermes delegate_task (subagent)."""
    data = request.get_json() or {}
    goal = data.get("goal", "")
    context = data.get("context", "")
    if not goal:
        return jsonify({"error": "goal required"}), 400

    # This would integrate with Hermes' delegate_task tool
    # For now, log the request and simulate
    log_event("delegate_task", "hermes", f"Delegated: {goal[:80]}", "info", {"goal": goal, "context": context[:200]})
    return jsonify({"status": "accepted", "task_id": f"task_{int(time.time())}", "message": "Subagent spawned (simulated)"})


@app.route("/api/logs/<date>")
def api_logs(date):
    """Serve daily event logs."""
    log_file = LOG_DIR / f"events_{date}.jsonl"
    if not log_file.exists():
        return jsonify({"events": []})
    events = []
    with open(log_file) as f:
        for line in f:
            try:
                events.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass
    return jsonify({"events": events})


@app.route("/api/logs/list")
def api_logs_list():
    """List available log dates."""
    dates = []
    for f in LOG_DIR.glob("events_*.jsonl"):
        try:
            date_str = f.stem.replace("events_", "")
            datetime.strptime(date_str, "%Y-%m-%d")
            dates.append(date_str)
        except ValueError:
            pass
    return jsonify({"dates": sorted(dates, reverse=True)})


@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)


# ============ SOCKET.IO EVENTS ============

@socketio.on("connect")
def handle_connect():
    emit("state_sync", {
        "hermes": agent_state["hermes"],
        "ollama": agent_state["ollama"],
        "n8n": agent_state["n8n"],
        "system": agent_state["system"],
        "events": agent_state["events"][:50],
    })
    log_event("websocket", "client", "Client connected", "info")


@socketio.on("disconnect")
def handle_disconnect():
    log_event("websocket", "client", "Client disconnected", "info")


@socketio.on("request_refresh")
def handle_refresh():
    check_ollama()
    check_hermes()
    check_n8n()
    emit("state_sync", {
        "hermes": agent_state["hermes"],
        "ollama": agent_state["ollama"],
        "n8n": agent_state["n8n"],
        "system": agent_state["system"],
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    log_event("startup", "system", f"Starting web test on port {port}", "success")
    socketio.run(app, host="0.0.0.0", port=port, debug=debug, allow_unsafe_werkzeug=True)