#!/bin/zsh
set -eu

script_dir="${0:A:h}"
submit_script="$script_dir/submit-to-tmux.zsh"
test_root="$(mktemp -d /tmp/gemini-cli-submit-test.XXXXXX)"
trap 'rm -rf "$test_root"' EXIT

fake_bin="$test_root/bin"
mkdir -p "$fake_bin"

cat > "$fake_bin/tmux" <<'FAKE_TMUX'
#!/bin/zsh
set -eu
printf '%s\n' "$*" >> "$TMUX_TEST_LOG"
if [[ "${TMUX_TEST_FAIL_ON:-}" == "$1" ]]; then
  exit 1
fi
if [[ "$1" == "list-panes" ]]; then
  print -- "gemini-test:0.0"
fi
FAKE_TMUX
chmod 700 "$fake_bin/tmux"

export PATH="$fake_bin:$PATH"
export TMUX_TEST_LOG="$test_root/tmux.log"
input_file="$test_root/input.txt"
print -r -- '请读取 /tmp/rework.md 并执行。' > "$input_file"

"$submit_script" '=gemini-test:0.0' "$input_file"

expected_log="$test_root/expected.log"
buffer_name="$(awk '$1 == "load-buffer" { print $3 }' "$TMUX_TEST_LOG")"
[[ -n "$buffer_name" ]]
cat > "$expected_log" <<EOF
list-panes -t =gemini-test:0.0 -F #{session_name}:#{window_index}.#{pane_index}
load-buffer -b $buffer_name $input_file
paste-buffer -b $buffer_name -t =gemini-test:0.0 -d
send-keys -t =gemini-test:0.0 Enter
EOF
diff -u "$expected_log" "$TMUX_TEST_LOG"

print -r -- $'第一行\n第二行' > "$input_file"
: > "$TMUX_TEST_LOG"
if "$submit_script" '=gemini-test:0.0' "$input_file" >/dev/null 2>&1; then
  print -u2 'multiline input unexpectedly succeeded'
  exit 1
fi
[[ ! -s "$TMUX_TEST_LOG" ]]

print '' > "$input_file"
: > "$TMUX_TEST_LOG"
if "$submit_script" '=gemini-test:0.0' "$input_file" >/dev/null 2>&1; then
  print -u2 'blank input unexpectedly succeeded'
  exit 1
fi
[[ ! -s "$TMUX_TEST_LOG" ]]

print -r -- '继续执行。' > "$input_file"
: > "$TMUX_TEST_LOG"
export TMUX_TEST_FAIL_ON='send-keys'
if "$submit_script" '=gemini-test:0.0' "$input_file" >/dev/null 2>&1; then
  print -u2 'send-keys failure unexpectedly succeeded'
  exit 1
fi
unset TMUX_TEST_FAIL_ON

[[ "$(grep -c '^paste-buffer ' "$TMUX_TEST_LOG")" == 1 ]]
[[ "$(grep -c '^send-keys .* Enter$' "$TMUX_TEST_LOG")" == 1 ]]

print 'submit-to-tmux tests passed'
