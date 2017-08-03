# Lint checker/fixer

check_paths="nyaa/ utils/"
isort_paths="nyaa/" # just nyaa/ for now
max_line_length=100

function auto_pep8() {
  autopep8 ${check_paths} \
    --recursive \
    --in-place \
    --pep8-passes 2000 \
    --max-line-length ${max_line_length} \
    --verbose \
  && \
  isort ${isort_paths} \
    --recursive
}

function check_lint() {
  pycodestyle ${check_paths} \
    --show-source \
    --max-line-length=${max_line_length} \
    --format '%(path)s [%(row)s:%(col)s] %(code)s: %(text)s' \
  && \
  isort ${isort_paths} \
    --recursive \
    --diff \
    --check-only
}

# MAIN
action=auto_pep8 # default action
for arg in "$@"
do
  case "$arg" in
  "-h" | "--help")
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
result=$?

if [[ ${action} == check_lint ]]; then
  if [[ ${result} == 0 ]]; then
    echo "Looks good!"
  else
    echo "The code requires some changes."
  fi
fi

if [[ ${result} -ne 0 ]]; then exit 1; fi
