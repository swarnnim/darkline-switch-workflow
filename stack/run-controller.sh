#!/bin/bash
# Run the headless Switch agent controller in the foreground.
# Expects: Node >= 22.13, switch-agent-controller and opencode on the
# directories below (adjust to your install locations).
export PATH=${NODE22_HOME:-$HOME/node22}/bin:${CONTROLLER_HOME:-$HOME/controller-app}/bin:${OPENCODE_HOME:-$HOME/opencode}/node_modules/.bin:$PATH
# Keep NO_PROXY minimal: some environments ship bracketed IPv6 entries
# that crash strict URL parsers in the stack.
export NO_PROXY=localhost,127.0.0.1
export no_proxy=localhost,127.0.0.1
exec switch-agent-controller run
