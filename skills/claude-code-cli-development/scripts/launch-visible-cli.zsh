#!/bin/zsh
set -eu

if [[ $# -ne 3 ]]; then
  print -u2 "usage: $0 <tmux-session-name> </absolute/path/to/runner.zsh> </absolute/path/to/task-worktree>"
  exit 64
fi

session_name="$1"
runner_path="$2"
task_worktree="$3"

if [[ ! "$session_name" =~ '^[A-Za-z0-9._-]+$' ]]; then
  print -u2 "invalid tmux session name: $session_name"
  exit 64
fi
if [[ "$runner_path" != /* || ! -f "$runner_path" || ! -x "$runner_path" ]]; then
  print -u2 "runner must be an absolute executable file: $runner_path"
  exit 66
fi
if [[ "$task_worktree" != /* || ! -d "$task_worktree" ]]; then
  print -u2 "task worktree must be an absolute existing directory: $task_worktree"
  exit 66
fi
task_worktree="${task_worktree:A}"

tmux_bin="$(command -v tmux || true)"
if [[ -z "$tmux_bin" ]]; then
  print -u2 "tmux is not installed"
  exit 69
fi
if [[ ! -d /System/Applications/Utilities/Terminal.app ]]; then
  print -u2 "macOS Terminal.app is unavailable"
  exit 69
fi

script_dir="${0:A:h}"
tmux_config="$script_dir/tmux-visible.conf"
if [[ ! -f "$tmux_config" ]]; then
  print -u2 "tmux config is unavailable: $tmux_config"
  exit 69
fi
if "$tmux_bin" has-session -t "=$session_name" 2>/dev/null; then
  print -u2 "tmux session already exists; refuse to attach or reuse at initial launch: $session_name"
  exit 73
fi

wrapper_path="/tmp/codex-claude-${session_name}.command"
terminal_window_id_path="/tmp/codex-claude-${session_name}.terminal-window-id"
if [[ -e "$wrapper_path" || -e "$terminal_window_id_path" ]]; then
  print -u2 "visible launcher state already exists: $wrapper_path or $terminal_window_id_path"
  exit 73
fi

printf '#!/bin/zsh\nset +e\ncd %q\nterminal_window_id_path=%q\nif %q list-sessions >/dev/null 2>&1; then\n  %q set-option -g mouse on\n  %q set-option -g history-limit 50000\nfi\n%q -f %q new-session -s %q -c %q %q\ntmux_rc=$?\nfor _attempt in {1..20}; do\n  [[ -s "$terminal_window_id_path" ]] && break\n  sleep 0.05\ndone\nif [[ -s "$terminal_window_id_path" ]]; then\n  terminal_window_id="$(<"$terminal_window_id_path")"\n  /usr/bin/osascript - "$terminal_window_id" <<'"'"'APPLESCRIPT'"'"' >/dev/null 2>&1\non run argv\n  set target_window_id to (item 1 of argv) as integer\n  tell application "Terminal"\n    repeat with task_window in windows\n      if id of task_window is target_window_id then\n        if (count of tabs of task_window) is 1 then\n          close task_window\n          return "closed"\n        end if\n        return "kept-multiple-tabs"\n      end if\n    end repeat\n  end tell\n  return "not-found"\nend run\nAPPLESCRIPT\nfi\nrm -f "$terminal_window_id_path" %q\nexit "$tmux_rc"\n' \
  "$task_worktree" "$terminal_window_id_path" "$tmux_bin" "$tmux_bin" "$tmux_bin" "$tmux_bin" \
  "$tmux_config" "$session_name" "$task_worktree" "$runner_path" "$wrapper_path" > "$wrapper_path"
chmod 700 "$wrapper_path"

if ! terminal_window_id="$(/usr/bin/osascript - "$wrapper_path" <<'APPLESCRIPT'
on run argv
  tell application "Terminal"
    activate
    set previous_window_ids to id of every window
    do script quoted form of (item 1 of argv)
    repeat with task_window in windows
      if (id of task_window) is not in previous_window_ids then return id of task_window
    end repeat
    error "new Terminal window not found"
  end tell
end run
APPLESCRIPT
)"; then
  if "$tmux_bin" has-session -t "=$session_name" 2>/dev/null; then
    "$tmux_bin" kill-session -t "=$session_name"
  fi
  rm -f "$wrapper_path" "$terminal_window_id_path"
  print -u2 "failed to create and identify a dedicated Terminal window"
  exit 74
fi
if [[ ! "$terminal_window_id" =~ '^[0-9]+$' ]]; then
  if "$tmux_bin" has-session -t "=$session_name" 2>/dev/null; then
    "$tmux_bin" kill-session -t "=$session_name"
  fi
  rm -f "$wrapper_path" "$terminal_window_id_path"
  print -u2 "failed to identify a dedicated Terminal window"
  exit 74
fi
printf '%s\n' "$terminal_window_id" > "$terminal_window_id_path"

for _attempt in {1..50}; do
  if "$tmux_bin" has-session -t "=$session_name" 2>/dev/null; then
    pane_path="$("$tmux_bin" display-message -p -t "=$session_name:0.0" '#{pane_current_path}')"
    if [[ -n "$pane_path" && "${pane_path:A}" == "$task_worktree" ]]; then
      print "opened visible Terminal tmux session: $session_name"
      print "verified task worktree: $task_worktree"
      print "recorded dedicated Terminal window id: $terminal_window_id"
      exit 0
    fi
  fi
  sleep 0.1
done

print -u2 "visible tmux session did not enter expected task worktree: $task_worktree"
exit 74
