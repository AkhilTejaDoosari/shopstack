# ShopStack Worker — Multi-stage Go build
#
# Stage 1: builder
# Full Go toolchain (~800MB) compiles the binary.
# This stage is never shipped — it exists only to compile.
#
# Stage 2: runner
# Scratch-like alpine image (~5MB) runs the binary.
# No Go compiler, no source code, no shell.
# The attack surface is the binary and nothing else.
#
# This is the pattern used by the Go services inside Kubernetes itself.
# When an interviewer asks "what is a multi-stage build and why use it" —
# this Dockerfile is your answer.

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

WORKDIR /build

# Copy go.mod first — if it doesn't change, 'go mod download' is cached
COPY go.mod .
RUN go mod download

# Copy source and compile
# CGO_ENABLED=0  — static binary, no C library dependency
# GOOS=linux     — target OS (explicit even in a Linux container)
# GOARCH=amd64   — target architecture
#                  If your AWS instance is ARM (Graviton/t4g), change to arm64.
#                  Without this flag on a cross-compile, you get: exec format error
COPY . .
# TARGETARCH is set automatically by Docker BuildKit based on the platform.
# On Apple Silicon (arm64): builds arm64 binary.
# On AWS x86 (amd64):       builds amd64 binary.
# On AWS Graviton (arm64):  builds arm64 binary.
# No manual change needed when switching machines.
ARG TARGETARCH
RUN CGO_ENABLED=0 GOOS=linux GOARCH=${TARGETARCH} go build -o worker .

# ── Stage 2: runner ───────────────────────────────────────────────────────────
FROM alpine:3.19

# ca-certificates — needed for HTTPS requests (the /api/health ping is HTTP,
# but if you ever change the API to HTTPS, this is already here)
RUN apk --no-cache add ca-certificates

WORKDIR /app

# Copy ONLY the compiled binary from the builder stage
# Nothing else from stage 1 comes with it
COPY --from=builder /build/worker .

CMD ["./worker"]
