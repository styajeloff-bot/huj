#!/usr/bin/env bash
# Human-in-the-loop reproduction loop for a local Carcraft user flow.
# Copy this file to a disposable location, edit the steps below, and run it.
# The agent runs the script; the user follows prompts in their terminal.
#
# Usage:
#   bash hitl-loop.template.sh
#
# Two helpers:
#   step "<instruction>"          → show instruction, wait for Enter
#   capture VAR "<question>"      → show question, read response into VAR
#
# At the end, captured values are printed as KEY=VALUE for the agent to parse.

set -euo pipefail

step() {
  printf '\n>>> %s\n' "$1"
  read -r -p "    [Enter when done] " _
}

capture() {
  local var="$1" question="$2" answer
  printf '\n>>> %s\n' "$question"
  read -r -p "    > " answer
  printf -v "$var" '%s' "$answer"
}

# --- edit below ---------------------------------------------------------

step "Open the Carcraft app through its local Nginx URL and sign in with a non-production test account."

capture REPRODUCED "Perform the minimal reproduction steps. Did the exact reported symptom occur? (y/n)"

capture OBSERVED "Describe the visible symptom without tokens, cookies, secrets, or personal data:"

capture REQUEST_ID "Paste a sanitized request/trace id if one is available (or 'none'):"

# --- edit above ---------------------------------------------------------

printf '\n--- Captured ---\n'
printf 'REPRODUCED=%s\n' "$REPRODUCED"
printf 'OBSERVED=%s\n' "$OBSERVED"
printf 'REQUEST_ID=%s\n' "$REQUEST_ID"
