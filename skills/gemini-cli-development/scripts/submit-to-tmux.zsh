#!/bin/zsh
set -eu

if [[ $# -ne 2 ]]; then
  print -u2 "usage: $0 <=session:window.pane> </absolute/path/to/single-line-input>"
  exit 64
fi

target="$1"
input_file="$2"

if [[ ! "$target" =~ '^=[A-Za-z0-9._-]+:[0-9]+\.[0-9]+$' ]]; then
  print -u2 "tmux target must be exact: =session:window.pane"
  exit 64
fi
if [[ "$input_file" != /* || ! -f "$input_file" || ! -r "$input_file" ]]; then
  print -u2 "input must be an absolute readable file: $input_file"
  exit 66
fi
input_line="$(<"$input_file")"
if [[ "$(LC_ALL=C awk 'END { print NR }' "$input_file")" != 1 || -z "$input_line" ]]; then
  print -u2 "input must contain exactly one non-empty line"
  exit 65
fi

tmux_bin="$(command -v tmux || true)"
if [[ -z "$tmux_bin" ]]; then
  print -u2 "tmux is not installed"
  exit 69
fi

resolved_target="$("$tmux_bin" list-panes -t "$target" -F '#{session_name}:#{window_index}.#{pane_index}')"
if [[ "$resolved_target" != "${target#=}" ]]; then
  print -u2 "tmux target is unavailable or ambiguous: $target"
  exit 69
fi

buffer_name="gemini-cli-submit-$$"
"$tmux_bin" load-buffer -b "$buffer_name" "$input_file"
if ! "$tmux_bin" paste-buffer -b "$buffer_name" -t "$target" -d; then
  "$tmux_bin" delete-buffer -b "$buffer_name" 2>/dev/null || true
  print -u2 "failed to paste input into tmux target: $target"
  exit 74
fi

sleep 0.1
if ! "$tmux_bin" send-keys -t "$target" Enter; then
  print -u2 "input was pasted but Enter could not be sent: $target"
  exit 74
fi

print "submitted one line to tmux target: $target"
