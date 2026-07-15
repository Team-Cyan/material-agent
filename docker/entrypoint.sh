#!/usr/bin/env sh
set -eu

app_user="material-agent"
app_group="material-agent"
run_as_root=false
source_input_dir="${MATERIAL_AGENT_INPUT_DIR:-/photos}"

discover_run_input() {
  help_seen=false
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -h|--help)
        help_seen=true
        shift
        ;;
      --config|--scorers)
        if [ "$#" -lt 2 ]; then
          echo "Missing value for run option: $1" >&2
          return 2
        fi
        case "$2" in
          -*)
            echo "Missing value for run option: $1" >&2
            return 2
            ;;
        esac
        shift 2
        ;;
      --config=|--scorers=)
        echo "Missing value for run option: ${1%%=*}" >&2
        return 2
        ;;
      --config=?*|--scorers=?*|--reprocess|--dry-run|--allow-empty|--no-visual-merge)
        shift
        ;;
      --)
        shift
        if [ "$#" -eq 0 ]; then
          echo "Missing input directory for run command" >&2
          return 2
        fi
        printf '%s\n' "$1"
        return 0
        ;;
      -*)
        echo "Unsupported run option while resolving input: $1" >&2
        return 2
        ;;
      *)
        printf '%s\n' "$1"
        return 0
        ;;
    esac
  done
  if [ "$help_seen" = true ]; then
    return 1
  fi
  echo "Missing input directory for run command" >&2
  return 2
}

discover_dir_input() {
  discovered_dir=""
  help_seen=false
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -h|--help)
        help_seen=true
        shift
        ;;
      --dir)
        if [ "$#" -lt 2 ]; then
          echo "Missing value for maintenance option: --dir" >&2
          return 2
        fi
        case "$2" in
          -*)
            echo "Missing value for maintenance option: --dir" >&2
            return 2
            ;;
        esac
        if [ -n "$discovered_dir" ]; then
          echo "Duplicate maintenance option: --dir" >&2
          return 2
        fi
        discovered_dir="$2"
        shift 2
        ;;
      --dir=)
        echo "Missing value for maintenance option: --dir" >&2
        return 2
        ;;
      --dir=?*)
        if [ -n "$discovered_dir" ]; then
          echo "Duplicate maintenance option: --dir" >&2
          return 2
        fi
        discovered_dir=${1#--dir=}
        shift
        ;;
      *)
        shift
        ;;
    esac
  done
  if [ -z "$discovered_dir" ]; then
    if [ "$help_seen" = true ]; then
      return 1
    fi
    echo "Missing --dir for maintenance command" >&2
    return 2
  fi
  printf '%s\n' "$discovered_dir"
}

discover_source_input() {
  if [ "${1:-}" = "material-agent" ]; then
    shift
  fi
  command_name="${1:-}"
  [ -n "$command_name" ] || return 1
  shift
  case "$command_name" in
    run)
      discover_run_input "$@"
      ;;
    scan-scenes|suggest-scenes|remap-scenes|rescore|rewrite-xmp|rewrite-commentary|reset-ai|fix-db)
      discover_dir_input "$@"
      ;;
    *)
      return 1
      ;;
  esac
}

if explicit_input=$(discover_source_input "$@"); then
  source_input_dir="$explicit_input"
else
  discover_status=$?
  if [ "$discover_status" -ne 1 ]; then
    exit 64
  fi
fi

invalid_id() {
  name="$1"
  value="$2"
  echo "Invalid $name value: $value (expected an integer from 1 to 2147483647)" >&2
  exit 64
}

validate_id() {
  name="$1"
  value="$2"
  case "$value" in
    ""|*[!0-9]*) invalid_id "$name" "$value" ;;
  esac
  if [ "${#value}" -gt 10 ] || [ "$value" -lt 1 ] || [ "$value" -gt 2147483647 ]; then
    invalid_id "$name" "$value"
  fi
}

add_dri_groups() {
  primary_gid="$1"
  seen_gids=" "
  for device in /dev/dri/renderD* /dev/dri/card*; do
    [ -e "$device" ] || continue
    device_gid=$(stat -c '%g' "$device") || continue
    case "$device_gid" in
      ""|*[!0-9]*|0) continue ;;
    esac
    [ "$device_gid" = "$primary_gid" ] && continue
    case "$seen_gids" in
      *" $device_gid "*) continue ;;
    esac
    seen_gids="$seen_gids$device_gid "
    device_group=$(getent group "$device_gid" | cut -d: -f1 | head -n 1)
    if [ -z "$device_group" ]; then
      device_group="material-dri-$device_gid"
      groupadd --gid "$device_gid" "$device_group"
    fi
    usermod -a -G "$device_group" "$app_user"
  done
}

if [ "$(id -u)" = "0" ]; then
  run_as_root=true
  puid="${PUID:-1000}"
  pgid="${PGID:-1000}"
  validate_id PUID "$puid"
  validate_id PGID "$pgid"

  current_gid=$(id -g "$app_user")
  if [ "$current_gid" != "$pgid" ]; then
    groupmod -o -g "$pgid" "$app_group"
  fi
  current_uid=$(id -u "$app_user")
  if [ "$current_uid" != "$puid" ]; then
    usermod -o -u "$puid" "$app_user"
  fi
  usermod -g "$pgid" "$app_user"
  add_dri_groups "$pgid"

  requested_work_dir="${MATERIAL_AGENT_WORK_DIR:-/app/.material-agent}"
  requested_input_dir="$source_input_dir"
  if [ -L "$requested_work_dir" ]; then
    echo "MATERIAL_AGENT_WORK_DIR must not be a symbolic link: $requested_work_dir" >&2
    exit 64
  fi
  work_dir=$(realpath -m -- "$requested_work_dir")
  input_dir=$(realpath -m -- "$requested_input_dir")
  if [ "$work_dir" = "/" ]; then
    echo "MATERIAL_AGENT_WORK_DIR must not resolve to /" >&2
    exit 64
  fi
  if [ "$input_dir" = "/" ] || [ "$work_dir" = "$input_dir" ]; then
    echo "MATERIAL_AGENT_WORK_DIR must stay outside MATERIAL_AGENT_INPUT_DIR" >&2
    exit 64
  fi
  case "$work_dir" in
    "$input_dir"/*)
      echo "MATERIAL_AGENT_WORK_DIR must stay outside MATERIAL_AGENT_INPUT_DIR" >&2
      exit 64
      ;;
  esac
  mkdir -p "$work_dir"
  chown -h "$puid:$pgid" "$work_dir" /home/material-agent
  for runtime_file in \
    "$work_dir/state.db" \
    "$work_dir/state.db-wal" \
    "$work_dir/state.db-shm" \
    "$work_dir/state.db-journal" \
    "$work_dir/run.log" \
    "$work_dir/run.lock"
  do
    if [ -L "$runtime_file" ]; then
      echo "Runtime state file must not be a symbolic link: $runtime_file" >&2
      exit 64
    fi
    if [ -e "$runtime_file" ]; then
      chown -h "$puid:$pgid" "$runtime_file"
    fi
  done
  cache_dir="$work_dir/openvino-cache"
  if [ -L "$cache_dir" ]; then
    echo "OpenVINO cache directory must not be a symbolic link: $cache_dir" >&2
    exit 64
  fi
  if [ -d "$cache_dir" ]; then
    cache_symlink=$(find "$cache_dir" -xdev -type l -print -quit)
    if [ -n "$cache_symlink" ]; then
      echo "OpenVINO cache must not contain symbolic links: $cache_symlink" >&2
      exit 64
    fi
    find "$cache_dir" -xdev -exec chown -h "$puid:$pgid" {} +
  fi
  for managed_dir in \
    "$work_dir/models" \
    "$work_dir/labels" \
    "$work_dir/web" \
    "$work_dir/runtime-config" \
    "$work_dir/runtime-secrets"
  do
    if [ -L "$managed_dir" ]; then
      echo "Managed runtime directory must not be a symbolic link: $managed_dir" >&2
      exit 64
    fi
    mkdir -p "$managed_dir"
    find "$managed_dir" -xdev -exec chown -h "$puid:$pgid" {} +
  done
  export HOME=/home/material-agent USER="$app_user" LOGNAME="$app_user"
fi

run_material_agent() {
  if [ "$run_as_root" = true ]; then
    exec gosu "$app_user" material-agent "$@"
  fi
  exec material-agent "$@"
}

if [ "${1:-}" = "material-agent" ]; then
  shift
  run_material_agent "$@"
fi

case "${1:-}" in
  "")
    input_dir="${MATERIAL_AGENT_INPUT_DIR:-/photos}"
    dry_run=$(printf '%s' "${MATERIAL_AGENT_DRY_RUN:-false}" | tr '[:upper:]' '[:lower:]')
    case "$dry_run" in
      1|true|yes|on)
        run_material_agent run "$input_dir" --config "$MATERIAL_AGENT_CONFIG" --dry-run
        ;;
      0|false|no|off|"")
        run_material_agent run "$input_dir" --config "$MATERIAL_AGENT_CONFIG"
        ;;
      *)
        echo "Invalid MATERIAL_AGENT_DRY_RUN value: $dry_run" >&2
        exit 64
        ;;
    esac
    ;;
  -*)
    run_material_agent "$@"
    ;;
  *)
    run_material_agent "$@"
    ;;
esac
