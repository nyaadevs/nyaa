#!/bin/bash
# Lint checker/fixer
# This script is deprecated, but still works.

function auto_fix() {
  ./dev.py fix && ./dev.py isort
}


function check_lint() {
  ./dev.py lint
}

# MAIN
action=auto_fix # default action
for arg in "$@"
do
  case "$arg" in
  "-h" | "--help")
    echo "+ ========================= +"
    echo "+ This script is deprecated +"
    echo "+    Please use ./dev.py    +"
    echo "+ ========================= +"
    echo ""
    echo "Lint checker/fixer"
    echo ""
    echo "Usage: $0 [-c|--check] [-h|--help]"
    echo "  No arguments : Check and auto-fix some warnings/errors"
    echo "  -c | --check : only check lint (don't auto-fix)"
    echo "  -h | --help  : show this help and exit"
    exit 0;
    ;;
  "-c" | "--check")
    action=check_lint
    ;;
  esac
done

${action} # run selected action
if [[ $? -ne 0 ]]; then exit 1; fi
