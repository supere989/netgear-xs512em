# xs512em MCP — remote (streamable-http) server for the shared tool-hub.
# Build:  docker build -t xs512em-mcp:local .
# Run:    see docker-compose.yml (recommended) or `docker run`.
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/supere989/netgear-xs512em" \
      org.opencontainers.image.description="NETGEAR XS512EM MCP server (streamable-http / sse)" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir ".[mcp]"

# Remote defaults; override the switch creds + token at runtime.
ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8765
EXPOSE 8765

# Unauthenticated liveness probe served by the MCP wrapper.
HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8765/healthz',timeout=3).status==200 else 1)"

ENTRYPOINT ["xs512em-mcp"]
