#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
This tool is designed to assist developers run common tasks, such as
checking the code for lint issues, auto fixing some lint issues and running tests.
It imports modules lazily (as-needed basis), so it runs faster!
"""
import sys

LINT_PATHS = [
    'nyaa/',
    'utils/',
]
TEST_PATHS = ['tests']


def print_cmd(cmd, args):
    """ Prints the command and args as you would run them manually. """
    print('Running: {0}\n'.format(
        ' '.join([('\'' + a + '\'' if ' ' in a else a) for a in [cmd] + args])))
    sys.stdout.flush()  # Make sure stdout is flushed before continuing.


def check_config_values():
    """ Verify that all max_line_length values match. """
    import configparser
    config = configparser.ConfigParser()
    config.read('setup.cfg')

    # Max line length:
    flake8 = config.get('flake8', 'max_line_length', fallback=None)
    autopep8 = config.get('pycodestyle', 'max_line_length', fallback=None)
    isort = config.get('isort', 'line_length', fallback=None)

    values = (v for v in (flake8, autopep8, isort) if v is not None)
    found = next(values, False)
    if not found:
        print('Warning: No max line length setting set in setup.cfg.')
        return False
    elif any(v != found for v in values):
        print('Warning: Max line length settings differ in setup.cfg.')
        return False

    return True


def print_help():
    print('Nyaa Development Helper')
    print('=======================\n')
    print('Usage: {0} command [different arguments]'.format(sys.argv[0]))
    print('Command can be one of the following:\n')
    print('  lint | check       : do a lint check (flake8 + flake8-isort)')
    print('  fix  | autolint    : try and auto-fix lint (autopep8)')
    print('  isort              : fix import sorting (isort)')
    print('  test | pytest      : run tests (pytest)')
    print('  help | -h | --help : show this help and exit')
    print('')
    print('You may pass different arguments to the script that is being run.')
    print('For example: {0} test tests/ --verbose'.format(sys.argv[0]))
    print('')
    return 1


if __name__ == '__main__':
    assert sys.version_info >= (3, 6), "Python 3.6 is required"

    check_config_values()

    if len(sys.argv) < 2:
        sys.exit(print_help())

    cmd = sys.argv[1].lower()
    if cmd in ('help', '-h', '--help'):
        sys.exit(print_help())

    args = sys.argv[2:]
    run_default = not (args or set(('--version', '-h', '--help')).intersection(args))

    # Flake8 - lint and common errors checker
    # When combined with flake8-isort, also checks for unsorted imports.
    if cmd in ('lint', 'check'):
        if run_default:
            # Putting format in the setup.cfg file breaks `pip install flake8`
            settings = ['--format', '%(path)s [%(row)s:%(col)s] %(code)s: %(text)s',
                        '--show-source']
            args = LINT_PATHS + settings + args

        print_cmd('flake8', args)
        try:
            from flake8.main.application import Application as Flake8
        except ImportError as err:
            print('Unable to load module: {0!r}'.format(err))
            result = False
        else:
            f8 = Flake8()
            f8.run(args)
            result = f8.result_count == 0

            if not result:
                print("The code requires some changes.")
            else:
                print("Looks good!")
        finally:
            sys.exit(int(not result))

    # AutoPEP8 - auto code linter for most simple errors.
    if cmd in ('fix', 'autolint'):
        if run_default:
            args = LINT_PATHS + args

        print_cmd('autopep8', args)
        try:
            from autopep8 import main as autopep8
        except ImportError as err:
            print('Unable to load module: {0!r}'.format(err))
            result = False
        else:
            args = [''] + args  # Workaround
            result = autopep8(args)
        finally:
            sys.exit(result)

    # isort - automate import sorting.
    if cmd in ('isort', ):
        if run_default:
            args = LINT_PATHS + ['-rc'] + args

        print_cmd('isort', args)
        try:
            from isort.main import main as isort
        except ImportError as err:
            print('Unable to load module: {0!r}'.format(err))
            result = False
        else:
            # Need to patch sys.argv for argparse in isort
            sys.argv.remove(cmd)
            sys.argv = [sys.argv[0] + ' ' + cmd] + args
            result = isort()
        finally:
            sys.exit(result)

    # py.test - test runner
    if cmd in ('test', 'pytest'):
        if run_default:
            args = TEST_PATHS + args

        print_cmd('pytest', args)
        try:
            from pytest import main as pytest
        except ImportError as err:
            print('Unable to load module: {0!r}'.format(err))
            result = False
        else:
            result = pytest(args)
            result = result == 0
        finally:
            sys.exit(int(not result))

    sys.exit(print_help())
