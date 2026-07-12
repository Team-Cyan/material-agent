#!/usr/bin/env sh
set -eu

if [ "${1:-}" = "material-agent" ]; then
  shift
  exec material-agent "$@"
fi

case "${1:-}" in
  "")
    input_dir="${MATERIAL_AGENT_INPUT_DIR:-/photos}"
    if [ "${MATERIAL_AGENT_DRY_RUN:-false}" = "true" ]; then
      exec material-agent run "$input_dir" --config "$MATERIAL_AGENT_CONFIG" --dry-run
    fi
    exec material-agent run "$input_dir" --config "$MATERIAL_AGENT_CONFIG"
    ;;
  -*)
    exec material-agent "$@"
    ;;
  *)
    exec material-agent "$@"
    ;;
esac
