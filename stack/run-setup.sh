#!/bin/bash
# Run upstream's setup.py on the host: seeds the Mattermost team/users and
# wires Mattermost <-> switch-core. Idempotent per upstream docs; the script
# itself polls both services until they answer.
set -euo pipefail
cd "$(dirname "$0")"
set -a; . ./.env; set +a
# Sanitize: this environment's NO_PROXY carries bracketed IPv6 entries that crash httpx URL parsing.
export NO_PROXY=localhost,127.0.0.1
export no_proxy=localhost,127.0.0.1
export SWITCH_URL=http://localhost:8000
export MATTERMOST_URL=http://localhost:8065
export MATTERMOST_URL_FOR_SWITCH=http://localhost:8065
export MATTERMOST_CALLBACK_BASE_URL=http://localhost:8081
cd ${SWITCH_CHECKOUT:-$HOME/switch}/deploy/shared_resources
exec ${SWITCH_CHECKOUT:-$HOME/switch}/core/.venv/bin/python setup.py
