// ShopStack Worker — Go
// Job: ping /api/health every 10 seconds, write structured JSON logs.
//
// Why Go for this specific job:
// - Compiled binary, ~5MB final image vs ~200MB for Python
// - Near-zero CPU overhead for a background pinger
// - Demonstrates multi-stage build pattern — one of the most asked-about
//   Dockerfile patterns in DevOps interviews
// - You can kill this worker and the store keeps running — it has one job
//   and it owns nothing. That's the microservice principle in practice.

package main

import (
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"time"
)

// LogEntry is the structured log format.
// Same shape as the Python API logs — when you add Loki, one query finds both.
type LogEntry struct {
	TS      string `json:"ts"`
	Level   string `json:"level"`
	Service string `json:"service"`
	Event   string `json:"event"`
	Detail  string `json:"detail,omitempty"`
	Status  int    `json:"status,omitempty"`
	LatMS   int64  `json:"latency_ms,omitempty"`
}

func emit(level, event, detail string, status int, latMS int64) {
	entry := LogEntry{
		TS:      time.Now().UTC().Format(time.RFC3339),
		Level:   level,
		Service: "worker",
		Event:   event,
		Detail:  detail,
		Status:  status,
		LatMS:   latMS,
	}
	line, _ := json.Marshal(entry)
	fmt.Println(string(line))
}

func ping(apiURL string) {
	start := time.Now()
	resp, err := http.Get(apiURL + "/api/health")
	latMS := time.Since(start).Milliseconds()

	if err != nil {
		emit("warn", "health_ping_failed", err.Error(), 0, latMS)
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode == 200 {
		emit("info", "health_ping_ok", "api is healthy", resp.StatusCode, latMS)
	} else {
		emit("warn", "health_ping_degraded", "api returned non-200", resp.StatusCode, latMS)
	}
}

func main() {
	apiURL := os.Getenv("API_URL")
	if apiURL == "" {
		apiURL = "http://api:8080"
	}

	interval := 10 * time.Second

	emit("info", "worker_started", fmt.Sprintf("pinging %s every %s", apiURL, interval), 0, 0)

	// Ping immediately on startup, then on the interval
	ping(apiURL)

	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for range ticker.C {
		ping(apiURL)
	}
}
