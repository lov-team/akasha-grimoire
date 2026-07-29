#!/bin/zsh
set -eu

if ! command -v rg >/dev/null 2>&1; then
  print -u2 "rg is required"
  exit 69
fi

base_ref=""
typeset -a candidates test_files

if [[ ${1:-} == "--base" ]]; then
  if [[ $# -lt 2 ]]; then
    print -u2 "usage: $0 [--base <git-ref>] [test-file ...]"
    exit 64
  fi
  base_ref="$2"
  shift 2
fi

if (( $# > 0 )); then
  candidates=("$@")
elif [[ -n "$base_ref" ]]; then
  if ! git rev-parse --verify "${base_ref}^{commit}" >/dev/null 2>&1; then
    print -u2 "invalid base ref: $base_ref"
    exit 64
  fi
  candidates=("${(@f)$(git diff --name-only --diff-filter=ACMR "$base_ref" --)}")
  candidates+=("${(@f)$(git ls-files --others --exclude-standard)}")
else
  print -u2 "usage: $0 [--base <git-ref>] [test-file ...]"
  exit 64
fi

for file in "${candidates[@]}"; do
  [[ -f "$file" ]] || continue
  file_name="${file:t}"
  if [[ "$file" == */test/* || "$file" == */tests/* || "$file" == */spec/* || \
        "$file_name" == test_* || "$file_name" == test-* || "$file_name" == test.* || \
        "$file_name" == *_test.* || "$file_name" == *-test.* || "$file_name" == *.spec.* ]]; then
    test_files+=("$file")
  fi
done

if (( ${#test_files} == 0 )); then
  print "TEST_STRENGTH_AUDIT\tno-test-files"
  exit 0
fi

hard_pattern='\bor[[:space:]]+true\b|\|\|[[:space:]]*true\b'
advisory_pattern='^[[:space:]]*return([[:space:]]|$)|\._[A-Za-z][A-Za-z0-9_]*|assert[^#]*(if|unless)|assert[^#]*(==|<=)[[:space:]]*0\b'
hard_hits=0

print "TEST_STRENGTH_AUDIT\tfiles=${#test_files}"
for file in "${test_files[@]}"; do
  if rg -n --color never "$hard_pattern" "$file"; then
    hard_hits=1
  fi
done

print "TEST_STRENGTH_ADVISORY\tearly-return-private-access-conditional-or-zero-assert"
for file in "${test_files[@]}"; do
  rg -n --color never "$advisory_pattern" "$file" || true
done

if (( hard_hits != 0 )); then
  print -u2 "TEST_STRENGTH_BLOCKED\tconstant-true-bypass"
  exit 1
fi

print "TEST_STRENGTH_OK\tno-constant-true-bypass"
