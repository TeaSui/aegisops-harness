#!/usr/bin/env bash
# Bisection script to find which test creates unwanted files/state.
# Runs each matching test file alone with `npm test <file>`; adapt the runner line for other projects.
# Usage: find-polluter.sh <file_or_dir_to_check> <test_pattern>
# Example: bash "${CLAUDE_PLUGIN_ROOT}/skills/systematic-debugging/find-polluter.sh" '.git' './src/**/*.test.ts'
# Exit codes: 0 no polluter found, 1 polluter found, 2 usage error / nothing to test.

set -e

if [ $# -ne 2 ]; then
  echo "Usage: $0 <file_to_check> <test_pattern>"
  echo "Example: $0 '.git' './src/**/*.test.ts'"
  exit 2
fi

POLLUTION_CHECK="$1"
TEST_PATTERN="$2"

echo "Searching for test that creates: $POLLUTION_CHECK"
echo "Test pattern: $TEST_PATTERN"
echo ""

if [ -e "$POLLUTION_CHECK" ]; then
  echo "$POLLUTION_CHECK already exists before any test ran; remove it first, then rerun."
  exit 2
fi

# find -path matches against paths that start with "./", so normalize the pattern to that form.
TEST_FILES=$(find . -path "./${TEST_PATTERN#./}" | sort)
if [ -z "$TEST_FILES" ]; then
  echo "no test files matched: ./${TEST_PATTERN#./}"
  exit 2
fi
TOTAL=$(printf '%s\n' "$TEST_FILES" | wc -l | tr -d ' ')

echo "Found $TOTAL test files"
echo ""

COUNT=0
while IFS= read -r TEST_FILE; do
  COUNT=$((COUNT + 1))
  echo "[$COUNT/$TOTAL] Testing: $TEST_FILE"

  # Run the test
  npm test "$TEST_FILE" > /dev/null 2>&1 || true

  # Check if pollution appeared
  if [ -e "$POLLUTION_CHECK" ]; then
    echo ""
    echo "FOUND POLLUTER"
    echo "   Test: $TEST_FILE"
    echo "   Created: $POLLUTION_CHECK"
    echo ""
    echo "Pollution details:"
    ls -la "$POLLUTION_CHECK"
    echo ""
    echo "To investigate:"
    echo "  npm test \"$TEST_FILE\"    # Run just this test"
    echo "  cat \"$TEST_FILE\"         # Review test code"
    exit 1
  fi
done <<< "$TEST_FILES"

echo ""
echo "No polluter found among $TOTAL test files."
exit 0
