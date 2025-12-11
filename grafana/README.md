# Claude Code Metrics Dashboard

A local Grafana dashboard for visualizing Claude Code OpenTelemetry metrics.

Based on the dashboard shared by [mikelane](https://gist.github.com/mikelane/f6c3a175cd9f92410aba06b5ac24ba54) from the [Reddit post](https://www.reddit.com/r/ClaudeCode/comments/1pjon1r/til_that_claude_code_has_opentelemetry_metrics/).

## Quick Start

1. **Start the metrics stack:**
   ```bash
   ./start.sh
   ```

2. **Configure Claude Code** to send metrics (choose one method):

   **Option A: Environment variable**
   ```bash
   export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
   ```

   **Option B: Claude Code settings** (`~/.claude/settings.json`)
   ```json
   {
     "telemetry": {
       "enabled": true,
       "endpoint": "http://localhost:4318"
     }
   }
   ```

3. **View the dashboard:**
   - Open http://localhost:3000
   - Login: `admin` / `claude-metrics`
   - Navigate to Dashboards > Claude Code > Claude Code Metrics

## Architecture

```
┌──────────────┐     OTLP      ┌─────────────────┐
│ Claude Code  │──────────────>│ OpenTelemetry   │
│              │  (HTTP/gRPC)  │ Collector       │
└──────────────┘               └────────┬────────┘
                                        │ Prometheus
                                        │ scrape
                               ┌────────▼────────┐
                               │   Prometheus    │
                               │                 │
                               └────────┬────────┘
                                        │ query
                               ┌────────▼────────┐
                               │    Grafana      │
                               │   Dashboard     │
                               └─────────────────┘
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| Grafana | 3000 | Dashboard UI |
| Prometheus | 9090 | Metrics storage |
| OTLP gRPC | 4317 | OpenTelemetry gRPC receiver |
| OTLP HTTP | 4318 | OpenTelemetry HTTP receiver |

## Dashboard Panels

The dashboard includes:

### Summary Row
- **Sessions**: Total Claude Code sessions tracked
- **Commits Made**: Total commits via Claude Code
- **Active Time (CLI)**: Time Claude spent working
- **Active Time (You)**: Your interaction time
- **Total Cost**: API cost in USD
- **Lines of Code**: Accepted code lines

### Token Metrics
- Input/Output tokens
- Cache read/creation tokens
- Cache efficiency gauge
- Tokens by type (pie chart)
- Tokens by model (pie chart)

### Cost Analysis
- Cost per 1K output tokens
- Cost by model (bar gauge)
- Cost over time (time series)

### Productivity
- Productivity ratio (CLI time / User time)
- Peak leverage
- Active time distribution
- Activity over time

## Commands

```bash
# Start the stack
./start.sh

# Stop the stack
./stop.sh

# View logs
docker compose logs -f

# View specific service logs
docker compose logs -f grafana
docker compose logs -f prometheus
docker compose logs -f otel-collector

# Reset all data
docker compose down -v
```

## Customization

### Change Grafana password
Edit `docker-compose.yml`:
```yaml
environment:
  - GF_SECURITY_ADMIN_PASSWORD=your-new-password
```

### Adjust data retention
Edit `docker-compose.yml` prometheus command:
```yaml
command:
  - '--storage.tsdb.retention.time=90d'  # Keep 90 days
```

### Add alerting
You can configure Grafana alerts through the UI or add alert rules to the provisioning directory.

## Troubleshooting

**No data in dashboard?**
1. Check Claude Code is sending metrics: `docker compose logs otel-collector`
2. Verify Prometheus is scraping: http://localhost:9090/targets
3. Check the OTLP endpoint configuration in Claude Code

**Services won't start?**
1. Check if ports are already in use: `lsof -i :3000,4317,4318,9090`
2. View logs: `docker compose logs`

**Reset everything:**
```bash
docker compose down -v
./start.sh
```
