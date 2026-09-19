# web test - AI Agent Monitor Dashboard

Real-time monitoring dashboard for AI agents (Hermes, Ollama, N8N). Static HTML/JS, no backend required.

## Features

- 📊 **Live Agent Status**: Hermes, Ollama, N8N real-time status
- 💻 **System Metrics**: CPU, Memory, Disk usage with progress bars
- 📡 **Event Stream**: Real-time event log with filtering
- ⚡ **Agent Spawning**: Trigger new subagent tasks directly
- 🔄 **Auto-Refresh**: 10-second automatic status updates
- 🌙 **Dark Theme**: GitHub-inspired dark UI

## Usage

### Local
```bash
# Simply open in browser
open index.html

# Or serve via simple HTTP server
python3 -m http.server 8080
# Visit http://localhost:8080
```

### GitHub Pages (Deployed)
Live at: **https://wisnuputra17.github.io/web-test/**

## How It Works

- **Static HTML/JS**: No backend needed, pure client-side
- **Mock Data**: Simulates agent activity for demo (easily swap with real API calls)
- **Auto-Refresh**: Polls status every 10 seconds
- **Event Log**: Stores up to 50 events in memory

## Customization

Edit `index.html` to:
- Change mock data to real API calls (`generateMockData()`)
- Add WebSocket connection to Hermes/N8N
- Modify card styling via CSS variables
- Add more metrics or agents

## License

MIT
