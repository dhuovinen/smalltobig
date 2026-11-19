#!/usr/bin/env bash
# Serve smalltobig for one tester in the focus trial (docs/FOCUS.md, Step 0).
#
#   scripts/serve-tester.sh NAME PORT [abstracted|full]
#
# Each tester gets their own data directory, so their profile, sessions and
# feedback never mix with anyone else's: the web UI has no login. The server
# listens on the Tailscale address only (override with STB_TESTER_HOST).
# Use `full` only with the tester's explicit agreement (DECISIONS #24).
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 NAME PORT [abstracted|full]" >&2
  exit 2
fi
name="$1"
port="$2"
profile="${3:-abstracted}"

if [[ ! "$name" =~ ^[a-z0-9-]+$ ]]; then
  echo "NAME must be lowercase letters, digits or hyphens" >&2
  exit 2
fi
if [[ "$profile" != "abstracted" && "$profile" != "full" ]]; then
  echo "profile must be abstracted or full" >&2
  exit 2
fi

host="${STB_TESTER_HOST:-100.103.52.82}"
data_dir="${STB_TESTER_ROOT:-$HOME/SmallToBig/testers}/$name"
mkdir -p "$data_dir"
chmod 700 "$data_dir"

echo "Tester $name: http://$host:$port/htmsw/profile (privacy: $profile, data: $data_dir)"
cd "$(dirname "$0")/.."
STB_DATA_DIR="$data_dir" STB_PRIVACY_PROFILE="$profile" exec .venv/bin/stb serve --host "$host" --port "$port"
