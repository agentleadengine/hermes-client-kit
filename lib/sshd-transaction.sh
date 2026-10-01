#!/usr/bin/env bash

# Pairs are (target, source); --remove means the target should be absent.
# Validate the whole set together so an upgrade can repair two bad drop-ins.
sshd_files_apply() {
  local backup_dir target source staged index=0 result=0
  local -a targets=() sources=()
  (( $# > 0 && $# % 2 == 0 )) || return 2
  backup_dir=$(mktemp -d) || return 1
  while (( $# )); do
    target=$1 source=$2; shift 2
    if [[ -L $target || ( -e $target && ! -f $target ) ]]; then
      echo "Refusing non-regular sshd file: $target" >&2
      rm -rf -- "$backup_dir"
      return 1
    fi
    if [[ -e $target ]]; then
      cp -p -- "$target" "$backup_dir/$index" || { rm -rf -- "$backup_dir"; return 1; }
    fi
    targets+=("$target") sources+=("$source")
    index=$((index + 1))
  done
  for (( index=0; index<${#targets[@]}; index++ )); do
    target=${targets[index]} source=${sources[index]}
    if [[ $source == --remove ]]; then
      rm -f -- "$target" || { result=1; break; }
    else
      staged=$(mktemp "$(dirname "$target")/.hermes-ssh-stage.XXXXXX") || { result=1; break; }
      if ! install -m 0644 -- "$source" "$staged" || ! mv -f -- "$staged" "$target"; then
        rm -f -- "$staged"
        result=1
        break
      fi
    fi
  done
  if (( result == 0 )) && sshd -t; then
    rm -rf -- "$backup_dir"
    return 0
  fi
  for (( index=0; index<${#targets[@]}; index++ )); do
    target=${targets[index]}
    if [[ -f $backup_dir/$index ]]; then
      mv -f -- "$backup_dir/$index" "$target"
    else
      rm -f -- "$target"
    fi
  done
  rm -rf -- "$backup_dir"
  if sshd -t; then
    echo 'sshd update failed validation; previous file state restored.' >&2
  else
    echo 'sshd update failed validation; previous file state restored, but sshd still fails validation.' >&2
  fi
  return 1
}

sshd_file_apply() {
  sshd_files_apply "$1" "${2:---remove}"
}
