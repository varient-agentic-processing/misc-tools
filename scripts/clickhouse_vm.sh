#!/usr/bin/env bash
#
# Manage the ClickHouse GCE VM: check status, start, or stop.
# Finds the VM by tag (clickhouse-server) or by instance name.
#
set -euo pipefail

PROJECT_ID="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
INSTANCE=""
ZONE=""
TAG="clickhouse-server"

usage() {
  cat <<EOF
Usage: $0 COMMAND [OPTIONS]

Commands:
  status    Show if ClickHouse VM is running (and its external IP)
  start     Start the ClickHouse VM
  stop      Stop the ClickHouse VM
  list      List all VMs in the project (name, zone, status, external IP)

Options:
  -i, --instance NAME  VM instance name (default: discover by tag $TAG)
  -z, --zone ZONE      GCE zone (default: discover from instance)
  -p, --project ID     GCP project ID (default: from gcloud config)
  -h, --help           Show this help
EOF
}

find_instance() {
  if [[ -n "${INSTANCE:-}" && -n "${ZONE:-}" ]]; then
    return 0
  fi
  if [[ -n "${INSTANCE:-}" ]]; then
    # Have instance, need zone - list all and find it
    local line
    line=$(gcloud compute instances list --project="$PROJECT_ID" \
      --filter="name=$INSTANCE" \
      --format="value(name,zone)" 2>/dev/null | head -1)
    if [[ -n "$line" ]]; then
      ZONE=$(echo "$line" | awk '{print $2}')
      return 0
    fi
  fi
  # Discover by tag
  local line
  line=$(gcloud compute instances list --project="$PROJECT_ID" \
    --filter="tags.items=$TAG" \
    --format="value(name,zone)" 2>/dev/null | head -1)
  if [[ -z "$line" ]]; then
    echo "Error: No VM found with tag $TAG. Use -i INSTANCE -z ZONE to specify." >&2
    return 1
  fi
  INSTANCE=$(echo "$line" | awk '{print $1}')
  ZONE=$(echo "$line" | awk '{print $2}')
  return 0
}

cmd_status() {
  find_instance || exit 1
  local status ip
  status=$(gcloud compute instances describe "$INSTANCE" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --format="value(status)" 2>/dev/null)
  ip=$(gcloud compute instances describe "$INSTANCE" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --format="value(networkInterfaces[0].accessConfigs[0].natIP)" 2>/dev/null || echo "")
  echo "Instance: $INSTANCE"
  echo "Zone:     $ZONE"
  echo "Status:   $status"
  if [[ -n "${ip:-}" && "$ip" != "None" ]]; then
    echo "External IP: $ip"
    echo "ClickHouse HTTP: http://${ip}:8123"
  fi
  if [[ "$status" == "RUNNING" ]]; then
    exit 0
  else
    exit 1
  fi
}

cmd_start() {
  find_instance || exit 1
  echo "Starting $INSTANCE in $ZONE..."
  gcloud compute instances start "$INSTANCE" \
    --project="$PROJECT_ID" \
    --zone="$ZONE"
  echo "Started. Use 'status' to get the external IP."
}

cmd_stop() {
  find_instance || exit 1
  echo "Stopping $INSTANCE in $ZONE..."
  gcloud compute instances stop "$INSTANCE" \
    --project="$PROJECT_ID" \
    --zone="$ZONE"
  echo "Stopped."
}

cmd_list() {
  echo "VMs in project $PROJECT_ID:"
  echo ""
  gcloud compute instances list --project="$PROJECT_ID" \
    --format="table(name,zone,status,networkInterfaces[0].accessConfigs[0].natIP:label=EXTERNAL_IP)"
}

# First arg is command (status, start, stop, list)
if [[ -z "${1:-}" ]]; then
  echo "Error: Command required (status, start, stop, list)" >&2
  usage >&2
  exit 1
fi

CMD=$1
shift

# Parse options (can come after command: status -i x -z y)
while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--instance)
      INSTANCE="$2"
      shift 2
      ;;
    -z|--zone)
      ZONE="$2"
      shift 2
      ;;
    -p|--project)
      PROJECT_ID="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "Error: No project ID. Set GCP_PROJECT, use -p/--project, or run 'gcloud config set project PROJECT_ID'" >&2
  exit 1
fi

case "$CMD" in
  status) cmd_status ;;
  start)  cmd_start ;;
  stop)   cmd_stop ;;
  list)   cmd_list ;;
  *)
    echo "Unknown command: $CMD" >&2
    usage >&2
    exit 1
    ;;
esac
