import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

HOOK = pathlib.Path(__file__).resolve().parent.parent / 'plugins' / 'aegisops-harness' / 'hooks' / 'tdd-gate.py'


class TddGateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = pathlib.Path(self.tmp.name) / 'home'
        self.repo = pathlib.Path(self.tmp.name) / 'repo'
        self.home.mkdir()
        self.repo.mkdir()
        (self.repo / 'build.gradle').write_text('')

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, mode, payload, env_extra=None):
        env = {**os.environ, 'HOME': str(self.home)}
        env.update(env_extra or {})
        payload = {'session_id': 's1', 'cwd': str(self.repo), **payload}
        return subprocess.run([sys.executable, str(HOOK), mode], input=json.dumps(payload), env=env,
                              capture_output=True, text=True)

    def edit(self, path, tool='Edit'):
        return self.run_hook('check', {'tool_name': tool, 'tool_input': {'file_path': path}})

    def test_blocks_first_production_edit_once(self):
        first = self.edit('/r/core/src/main/java/app/Fee.java')
        self.assertEqual(first.returncode, 2)
        self.assertIn('failing test', first.stderr)
        self.assertEqual(self.edit('/r/core/src/main/java/app/Fee.java').returncode, 0)

    def test_failing_test_run_clears_the_gate(self):
        rec = self.run_hook('record', {'tool_name': 'Bash', 'tool_input': {'command': 'gradle test'},
                                       'tool_response': {'stdout': '5 tests completed, 1 failed\nBUILD FAILED'}})
        self.assertEqual(rec.returncode, 0)
        self.assertEqual(self.edit('/r/core/src/main/java/app/Fee.java').returncode, 0)

    def test_red_is_recorded_whatever_the_output_field_is_called(self):
        self.run_hook('record', {'tool_name': 'Bash', 'tool_input': {'command': 'npm test'},
                                 'tool_output': '# tests 1\n# fail 1'})
        self.assertEqual(self.edit('/r/src/main/java/A.java').returncode, 0)

    def test_passing_test_run_does_not_clear_the_gate(self):
        self.run_hook('record', {'tool_name': 'Bash', 'tool_input': {'command': 'gradle test'},
                                 'tool_response': {'stdout': 'BUILD SUCCESSFUL'}})
        self.assertEqual(self.edit('/r/src/main/java/A.java').returncode, 2)

    def test_non_test_command_with_failure_text_is_not_red(self):
        self.run_hook('record', {'tool_name': 'Bash', 'tool_input': {'command': 'cat log.txt'},
                                 'tool_response': {'stdout': 'FAILED'}})
        self.assertEqual(self.edit('/r/src/main/java/A.java').returncode, 2)

    def test_skips_tests_docs_and_config(self):
        for path in ('/r/core/src/test/java/app/FeeTest.java', '/r/web/branch.test.js', '/r/tests/test_x.py',
                     '/r/README.md', '/r/build.gradle', '/r/web/node_modules/x/index.js', '/r/build/gen/A.java'):
            self.assertEqual(self.edit(path).returncode, 0, path)

    def test_bash_heredoc_write_to_production_code_is_gated(self):
        cmd = "python3 - <<'EOF'\nopen('core/src/main/java/A.java','w').write('x')\nEOF"
        res = self.run_hook('check', {'tool_name': 'Bash', 'tool_input': {'command': cmd}})
        self.assertEqual(res.returncode, 2)

    def test_bash_that_only_reads_or_runs_tests_is_not_gated(self):
        for cmd in ('gradle test', 'git diff', 'cat core/src/main/java/A.java', 'ls src/main'):
            res = self.run_hook('check', {'tool_name': 'Bash', 'tool_input': {'command': cmd}})
            self.assertEqual(res.returncode, 0, cmd)

    def test_redirects_and_reads_that_mention_code_are_not_writes(self):
        # Seen in a real session: a read-only inspection was blocked because of `2>/dev/null`.
        for cmd in ('cat src/math.js; ls; ls src test* 2>/dev/null; cat package.json 2>/dev/null',
                    'grep -n fee src/main/java/A.java > /tmp/hits.txt', 'npm test 2>&1 | tee out.log',
                    'node src/app.js >&2', 'diff src/a.py src/b.py >/dev/null'):
            res = self.run_hook('check', {'tool_name': 'Bash', 'tool_input': {'command': cmd}})
            self.assertEqual(res.returncode, 0, cmd)

    def test_shell_writes_to_production_code_are_gated(self):
        for index, cmd in enumerate(("echo 'export const mul = 1' >> src/math.js", "cat > src/app.py <<'EOF'\nx = 1\nEOF",
                                     "sed -i '' 's/a/b/' src/main/java/A.java", 'printf x | tee src/a.ts',
                                     "perl -pi -e 's/a/b/' lib/a.rb")):
            res = self.run_hook('check', {'session_id': f'w{index}', 'tool_name': 'Bash',
                                          'tool_input': {'command': cmd}})
            self.assertEqual(res.returncode, 2, cmd)

    def test_repo_without_test_setup_is_not_gated(self):
        (self.repo / 'build.gradle').unlink()
        self.assertEqual(self.edit('/r/src/main/java/A.java').returncode, 0)

    def test_env_off_and_bad_input_fail_open(self):
        off = self.run_hook('check', {'tool_name': 'Edit', 'tool_input': {'file_path': '/r/src/main/A.java'}},
                            {'AEGISOPS_HARNESS_TDD_GATE': 'off'})
        self.assertEqual(off.returncode, 0)
        bad = subprocess.run([sys.executable, str(HOOK), 'check'], input='not json', capture_output=True,
                             text=True, env={**os.environ, 'HOME': str(self.home)})
        self.assertEqual(bad.returncode, 0)

    def test_sessions_are_independent(self):
        self.assertEqual(self.edit('/r/src/main/A.java').returncode, 2)
        other = self.run_hook('check', {'session_id': 's2', 'tool_name': 'Write',
                                        'tool_input': {'file_path': '/r/src/main/A.java'}})
        self.assertEqual(other.returncode, 2)

    def test_common_runners_are_recognised(self):
        runners = ('pnpm test', 'yarn test', 'bun test', 'python3 -m unittest discover -s tests', 'python -m pytest -q',
                   './mvnw verify', './gradlew check', 'cargo nextest run', 'swift test', 'deno test', 'rspec',
                   'npx playwright test', 'dotnet test', 'mix test')
        for index, command in enumerate(runners):
            session = f'runner{index}'
            self.run_hook('record', {'session_id': session, 'tool_name': 'Bash', 'tool_input': {'command': command},
                                     'tool_response': {'stdout': '1 failed'}})
            gate = self.run_hook('check', {'session_id': session, 'tool_name': 'Edit',
                                           'tool_input': {'file_path': '/r/src/main/java/A.java'}})
            self.assertEqual(gate.returncode, 0, command)

    def gate(self, cmd, session):
        return self.run_hook('check', {'session_id': session, 'tool_name': 'Bash', 'tool_input': {'command': cmd}})

    def test_writes_the_first_detector_missed_are_gated(self):
        cmds = ("python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('src/app.py')\np.write_text('x')\nEOF",
                'python3 -c "p=\'src/app.py\'; s=open(p).read(); open(p,\'w\').write(s)"',
                'echo x 1> src/app.py', 'echo x &> src/app.py', 'echo x &>> src/app.py', 'echo x >| src/app.py',
                'printf x | tee --append src/app.py', 'printf x | tee -i src/app.py', 'printf x | tee /dev/null src/app.py',
                "perl -p -i -e 's/a/b/' src/app.py", "sed --in-place 's/a/b/' src/app.py")
        for index, cmd in enumerate(cmds):
            self.assertEqual(self.gate(cmd, f'm{index}').returncode, 2, cmd)

    def test_mentioning_a_test_tool_is_not_a_test_run(self):
        for index, cmd in enumerate(('npm install -D jest', 'git commit -am "add jest config"', 'cat jest.config.js',
                                     'mvn -q verify -DskipTests', 'pip install pytest', 'ls karma.conf.js')):
            session = f'mention{index}'
            self.run_hook('record', {'session_id': session, 'tool_name': 'Bash', 'tool_input': {'command': cmd},
                                     'tool_response': {'stdout': 'FAILED'}})
            self.assertEqual(self.edit_in(session).returncode, 2, cmd)

    def edit_in(self, session):
        return self.run_hook('check', {'session_id': session, 'tool_name': 'Edit',
                                       'tool_input': {'file_path': '/r/src/main/java/A.java'}})

    def test_long_path_like_input_stays_fast(self):
        import time
        started = time.time()
        self.gate("sed -i 's/x/y/' " + 'a.' * 40000, 'slow')
        self.assertLess(time.time() - started, 3)


if __name__ == '__main__':
    unittest.main()
