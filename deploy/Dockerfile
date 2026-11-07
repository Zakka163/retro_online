FROM python:3.9-slim

LABEL maintainer="Arcade Online Team"
LABEL description="Arcade Online Matchmaking, Signaling and TCP Relay Server"

WORKDIR /app

# Copy application files
COPY catalog/ /app/catalog/
COPY server/ /app/server/
COPY config.json /app/config.json

ENV PYTHONUNBUFFERED=1

# Expose HTTP API & Signaling (8080) and Netplay Relay (55436)
EXPOSE 8080 55436

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')" || exit 1

ENTRYPOINT ["python3", "-m", "server.app"]
CMD ["--host", "0.0.0.0", "--port", "8080", "--relay-port", "55436"]

