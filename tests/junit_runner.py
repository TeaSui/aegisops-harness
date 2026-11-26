#!/usr/bin/env python3
"""Run unittest discovery and write a JUnit XML report (standard library only).

This repository's pinned verify command (.aidlc.json): the lifecycle gates read a JUnit report to see which story
tests ran and passed, and `python3 -m unittest` writes none.

Usage: python3 tests/junit_runner.py [-s START_DIR] [-p PATTERN] [-o REPORT]
Exit 0 when every test passed (skips allowed), 1 otherwise, 2 when no test ran.
"""
import argparse
import os
import pathlib
import sys
import time
import unittest
import xml.etree.ElementTree as ET


class Result(unittest.TextTestResult):
    """Keeps one record per test: (classname, name, state, detail, seconds); state pass | failure | error | skipped."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cases = []
        self._started = time.time()

    def startTest(self, test):
        self._started = time.time()
        super().startTest(test)

    def _record(self, test, state, detail=''):
        name = getattr(test, '_testMethodName', None)
        if name is None or type(test).__name__ == '_FailedTest':  # a module that did not import
            classname, name = type(test).__module__ + '.' + type(test).__qualname__, str(test.id()).rsplit('.', 1)[-1]
        else:
            classname = type(test).__module__ + '.' + type(test).__qualname__
        self.cases.append((classname, name, state, detail, time.time() - self._started))

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, 'pass')

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, 'pass')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, 'failure', self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, 'failure', 'unexpected success')

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, 'error', self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, 'skipped', reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:  # a passing subtest is covered by its test's own record
            state = 'failure' if issubclass(err[0], test.failureException) else 'error'
            self._record(test, state, '%s\n%s' % (subtest, self._exc_info_to_string(err, test)))


def report(cases, seconds):
    count = lambda state: sum(1 for case in cases if case[2] == state)  # noqa: E731
    suite = ET.Element('testsuite', name='unittest', tests=str(len(cases)), failures=str(count('failure')),
                       errors=str(count('error')), skipped=str(count('skipped')), time='%.3f' % seconds)
    for classname, name, state, detail, took in cases:
        case = ET.SubElement(suite, 'testcase', classname=classname, name=name, time='%.3f' % took)
        if state != 'pass':
            node = ET.SubElement(case, state, message=detail.strip().splitlines()[-1][:200] if detail.strip() else '')
            node.text = detail
    root = ET.Element('testsuites')
    root.append(suite)
    return ET.tostring(root, encoding='unicode')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('-s', '--start-directory', default='tests')
    parser.add_argument('-p', '--pattern', default='test*.py')
    parser.add_argument('-o', '--output', default='reports/junit.xml')
    args = parser.parse_args(argv)
    started = time.time()
    suite = unittest.defaultTestLoader.discover(args.start_directory, pattern=args.pattern)
    result = unittest.TextTestRunner(resultclass=Result, verbosity=1).run(suite)
    target = pathlib.Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_name('.%s.%d.tmp' % (target.name, os.getpid()))
    scratch.write_text(report(result.cases, time.time() - started), encoding='utf-8')
    os.replace(scratch, target)
    if not result.cases:
        return 2
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
