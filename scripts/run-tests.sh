#!/bin/bash

echo "Running Claude Code Setup Tests..."
echo ""

TESTS_DIR="$HOME/.claude/clankercage/tests"
PASSED=0
FAILED=0

for test in "$TESTS_DIR"/*.sh; do
  if bash "$test"; then
    ((PASSED++))
  else
    ((FAILED++))
  fi
done

echo ""
echo "================================"
if [ $FAILED -eq 0 ]; then
  echo "✓ All tests passed: $PASSED/$((PASSED+FAILED))"
  exit 0
else
  echo "✗ Some tests failed: $PASSED passed, $FAILED failed"
  exit 1
fi
