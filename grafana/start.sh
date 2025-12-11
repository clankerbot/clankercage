#!/bin/bash
# Start the Claude Code metrics stack (Grafana + Prometheus + OpenTelemetry Collector)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting Claude Code metrics stack..."
docker compose up -d

echo ""
echo "Waiting for services to be ready..."
sleep 5

echo ""
echo "=== Claude Code Metrics Stack Started ==="
echo ""
echo "Services:"
echo "  - Grafana:              http://localhost:3000 (admin / claude-metrics)"
echo "  - Prometheus:           http://localhost:9090"
echo "  - OpenTelemetry gRPC:   localhost:4317"
echo "  - OpenTelemetry HTTP:   localhost:4318"
echo ""
echo "To configure Claude Code to send metrics, add to your settings.json:"
echo ""
echo '  "telemetry": {'
echo '    "enabled": true,'
echo '    "endpoint": "http://localhost:4318"'
echo '  }'
echo ""
echo "Or set environment variable:"
echo "  export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318"
echo ""
echo "To stop: docker compose down"
echo "To view logs: docker compose logs -f"
