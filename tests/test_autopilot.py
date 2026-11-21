import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOK = ROOT / 'hooks' / 'autopilot.py'
SESSION_START = ROOT / 'hooks' / 'session-start'


class HookCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.home, self.repo = base / 'home', base / 'repo'
        self.home.mkdir()
        self.repo.mkdir()
        (self.repo / 'package.json').write_text('{}')

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, extra=None):
        env = {k: v for k, v in os.environ.items() if not k.startswith('TEA_SDLC_')}
        env['HOME'] = str(self.home)
        env.update(extra or {})
        return env

    def run_hook(self, mode, payload, env=None):
        payload = {'session_id': 's1', 'cwd': str(self.repo), **payload}
        return subprocess.run([sys.executable, str(HOOK), mode], input=json.dumps(payload),
                              env=self.env(env), capture_output=True, text=True, timeout=20)

    def context(self, result, event):
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return ''
        out = json.loads(result.stdout)
        self.assertEqual(out['hookSpecificOutput']['hookEventName'], event)
        return out['hookSpecificOutput']['additionalContext']


class PromptRouterTest(HookCase):
    def route(self, prompt, env=None):
        return self.context(self.run_hook('prompt', {'prompt': prompt}, env), 'UserPromptSubmit')

    def test_silent_for_slash_commands_and_small_talk(self):
        self.assertEqual(self.route('/upgrade-service-docs payments'), '')
        self.assertEqual(self.route('thanks!'), '')

    # Shapes replayed from real prompts (paraphrased): none of these is a code change for the workflow to gate.
    NOT_CODE = (
        'Remove all the experiment branches and old worktrees',
        'Bump version and commit',
        'bump version and publish the plugin',
        'Create a new repo named demo-copy and move the code there',
        'Change the author of every commit to my personal email',
        'Update README.md to match the current setup',
        'Add backward compatibility to the rules',
        'Agreed, change it so the wording is consistent',
        'Should we remove "/map-codebase" too?',
        'Is this prompt following spec → adr → tdd → implement → test → create-pr?',
        'Do we need to create a long-term API key?',
        'Check the whole "/eval-upgrade" setup, structure and wording',
    )

    def test_non_code_requests_get_no_workflow_note(self):
        for prompt in self.NOT_CODE:
            ctx = self.route(prompt)
            self.assertNotIn('tea-sdlc:test-driven-development', ctx, prompt)
            self.assertNotIn('tea-sdlc:spec', ctx, prompt)
            self.assertNotIn('trust boundary', ctx, prompt)

    def test_mentioning_a_flow_is_not_asking_for_its_steps(self):
        self.assertEqual(self.route('Is this prompt following spec → adr → tdd → implement → test → create PR?'), '')
        self.assertEqual(self.route('Prompt builder now emits six stages: spec → adr → tdd → implement → create PR'), '')
        self.assertIn('tea-sdlc:writing-software-docs', self.route('Write an ADR for the decision to use Kafka'))
        self.assertIn('tea-sdlc:finishing-a-development-branch', self.route('create a PR for this branch'))

    def test_removing_a_slash_command_is_not_code_work(self):
        ctx = self.route('Remove "/tdd-feature", I do not need the new-project feature')
        self.assertNotIn('tea-sdlc:test-driven-development', ctx)

    def test_claude_vocabulary_is_not_auth(self):
        for prompt in ('Fix the retry logic, then spawn a new session to rerun it',
                       '<role>\nYou are a backend engineer.\n</role>\nAdd a retry to the order client',
                       'Reduce the tokens the summarize function spends per model call'):
            ctx = self.route(prompt)
            self.assertIn('tea-sdlc:test-driven-development', ctx, prompt)
            self.assertNotIn('auth', ctx, prompt)

    def test_code_changes_route_with_their_trust_items(self):
        ctx = self.route('Add a function that computes the transfer fee')
        self.assertIn('tea-sdlc:test-driven-development', ctx)
        self.assertIn('money', ctx)
        self.assertIn('new public surface', self.route('Create a new endpoint that lists orders'))

    def test_router_is_english_only(self):
        self.assertEqual(self.route('Thêm API thanh toán cho ví điện tử'), '')
        self.assertEqual(self.route('sửa lỗi đăng nhập'), '')

    # Prompts from the passive-trigger experiment (headless sessions) that the router missed.
    def test_red_build_is_a_bug(self):
        ctx = self.route('npm test is red since this morning, sort it out.')
        # The bootstrap loads spec first for any fix, so the note lists it and then the debugging step.
        self.assertLess(ctx.index('tea-sdlc:spec'), ctx.index('tea-sdlc:systematic-debugging'))

    def test_review_feedback_is_received_not_requested(self):
        ctx = self.route("A reviewer left this on src/math.js: 'divide() must guard against zero.' Deal with the review.")
        self.assertIn('tea-sdlc:receiving-code-review', ctx)
        self.assertNotIn('tea-sdlc:review', ctx)

    def test_domain_skills_are_named_without_a_change_verb(self):
        self.assertIn('tea-sdlc:messaging-patterns', self.route(
            'Design a Kafka consumer for order-created events with retries and a dead-letter topic.'))
        self.assertIn('tea-sdlc:database-patterns', self.route(
            "Write a Postgres query that returns each customer's latest order, using CTEs."))
        self.assertIn('tea-sdlc:fintech-security', self.route('Threat model the transfer function in src/wallet.js.'))

    def test_domain_keywords_do_not_over_match(self):
        for prompt, wrong in (('Add a CloudWatch alarm for Lambda errors', 'observability'),
                              ('Fix the React Native login screen', 'frontend-react'),
                              ('Validate the mobile number format', 'fintech-mobile'),
                              ('Add a Pact consumer-driven test', 'messaging-patterns'),
                              ('Fix the TanStack queries cache bug', 'database-patterns'),
                              ('Lint the CloudFormation template', 'cdk-testing')):
            self.assertNotIn('tea-sdlc:' + wrong, self.route(prompt), prompt)

    def test_backend_language_and_threat_model_hints(self):
        self.assertIn('tea-sdlc:backend-languages', self.route('Add a FastAPI endpoint that lists orders'))
        self.assertIn('security-engineer-subagent', self.route('Threat model the transfer function', {'TEA_SDLC_WORKFLOW': 'full'}))
        self.assertNotIn('security-engineer-subagent', self.route('Threat model the transfer function'))

    def test_question_followed_by_an_ask_is_still_a_question(self):
        ctx = self.route('Does the Node.js test runner support test.each like Jest? Give me the source.')
        self.assertNotIn('tea-sdlc:test-driven-development', ctx)
        self.assertIn('tea-sdlc:find-docs', ctx)

    def test_readiness_and_review_requests(self):
        self.assertIn('tea-sdlc:validate-feature', self.route('Check the pending change is ready before I open a PR.'))
        self.assertIn('tea-sdlc:review', self.route('I am done with the sub() change; get it reviewed '
                                                                    'before merge.'))

    def test_release_requests_go_to_shipping(self):
        for prompt in ('ship it', 'Cut a release for the refund feature', 'deploy this to production'):
            self.assertIn('tea-sdlc:ship', self.route(prompt), prompt)

    def test_lifecycle_status_questions_point_to_the_cli(self):
        for prompt in ('where are we with the refund feature?', "what's next?"):
            self.assertIn('aidlc.py', self.route(prompt), prompt)

    def test_short_steering_messages_still_route(self):
        self.assertIn('tea-sdlc:systematic-debugging', self.route('ok, fix that bug'))
        self.assertIn('tea-sdlc:spec', self.route('no, add a retry'))

    FULL = {'TEA_SDLC_WORKFLOW': 'full'}

    def test_bug_fix_with_auth_signal(self):
        ctx = self.route('Fix the login bug: users get a 500 error after the token expires', self.FULL)
        self.assertIn('tea-sdlc:systematic-debugging', ctx)
        self.assertIn('tea-sdlc:test-driven-development', ctx)
        self.assertIn('auth', ctx)
        self.assertIn('Full workflow (Security first)', ctx)

    def test_payment_feature_is_a_trust_boundary(self):
        ctx = self.route('Add a payment API for the e-wallet', self.FULL)
        self.assertIn('tea-sdlc:spec', ctx)
        self.assertIn('money', ctx)
        self.assertIn('Full workflow (Security first)', ctx)

    def test_lean_is_the_default_and_keeps_trust_work_in_session(self):
        # Subagent-heavy runs cost too much to be the default: a trust boundary gets a security pass in the session.
        ctx = self.route('Add a payment API for the e-wallet')
        self.assertIn('money', ctx)
        self.assertIn('lean', ctx)
        self.assertIn('Fast path with a security pass', ctx)
        self.assertIn('no subagents', ctx)
        self.assertNotIn('Full workflow (Security first)', ctx)
        self.assertNotIn('produced by tea-sdlc:security-engineer-subagent', self.route('Add PCI DSS checks to the card flow'))

    def test_user_can_ask_for_the_full_workflow_in_the_prompt(self):
        for prompt in ('Add a payment API for the e-wallet, full workflow please',
                       'Use the AIDLC lifecycle to add refunds to the payment service'):
            self.assertIn('Full workflow (Security first)', self.route(prompt), prompt)

    def test_lean_mode_does_not_fan_out_debugging(self):
        prompt = 'The 502 errors across services started after the deploy, fix it'
        self.assertNotIn('tea-sdlc:debug-parallel', self.route(prompt))
        self.assertIn('tea-sdlc:debug-parallel', self.route(prompt, self.FULL))

    HANDED = ('Do it with stages spec → plan → build:\n\nStatus: ready-for-agent\n\n# Refunds\n\n## Problem Statement\n'
              'Support cannot undo a transfer.\n\n## Solution\nRefund by id.\n\n## User Stories\n\n'
              '1. As a support agent, I want to refund a transfer, so that the sender gets the money back.\n')

    def test_handed_over_spec_is_used_verbatim(self):
        lean, full = self.route(self.HANDED), self.route(self.HANDED, self.FULL)
        for ctx in (lean, full):
            self.assertIn('tea-sdlc:spec', ctx)
            self.assertIn('Spec handed over (to-spec template)', ctx)
            self.assertIn('no grilling', ctx)
        self.assertIn('save it verbatim as docs/specs/<feature>/spec.md', full)
        self.assertIn('no README, ledger or gates', lean)
        self.assertNotIn('Spec handed over', self.route('Add a refund endpoint for transfers'))

    def test_grill_me_loads_grilling_first(self):
        ctx = self.route('Grill me on the refund design before we build it')
        self.assertIn('tea-sdlc:grilling', ctx)

    def test_ui_bug_is_fast_path(self):
        ctx = self.route('Fix the bug where the Save button is misaligned')
        self.assertIn('tea-sdlc:systematic-debugging', ctx)
        self.assertNotIn('trust boundary', ctx)
        self.assertIn('Fast path', ctx)

    def test_domain_skill_hint(self):
        ctx = self.route('Add an index and a migration for the orders table in Postgres')
        self.assertIn('tea-sdlc:database-patterns', ctx)

    def test_plain_questions_stay_silent_even_with_sensitive_words(self):
        self.assertEqual(self.route('how does the session table index work?'), '')
        self.assertEqual(self.route('explain how the payment flow works?'), '')

    def test_markdown_table_is_not_database_work(self):
        self.assertNotIn('database-patterns', self.route('Refactor the README table'))

    def test_outer_workflow_skills_come_first(self):
        ctx = self.route('fix the flaky checkout test end-to-end, until done')
        self.assertLess(ctx.index('tea-sdlc:goal'), ctx.index('tea-sdlc:spec'))

    def test_load_balancer_is_not_money(self):
        self.assertNotIn('money', self.route('Update the load balancer health check path'))

    def test_autonomy_and_delivery_intents(self):
        self.assertIn('tea-sdlc:goal', self.route('handle everything end-to-end, I do not want to keep reminding you'))
        ctx = self.route('open a PR for this branch')
        self.assertIn('tea-sdlc:finishing-a-development-branch', ctx)
        self.assertIn('pre-pr-review', ctx)

    def test_incident_and_doubt_intents(self):
        self.assertIn('tea-sdlc:incident-to-eval', self.route('We had to rollback yesterday, the release broke checkout'))
        self.assertIn('tea-sdlc:prove-it', self.route('are you sure? double-check it'))

    def test_docs_intent(self):
        self.assertIn('tea-sdlc:generate-service-docs', self.route('generate the docs for the order-api service'))

    def test_output_is_bounded(self):
        ctx = self.route(' '.join(['fix the payment login webhook kafka react flutter datadog sql cdk spark error'] * 300))
        self.assertLess(len(ctx), 1600)

    def test_can_be_turned_off(self):
        self.assertEqual(self.route('Fix the login bug', {'TEA_SDLC_AUTOPILOT': 'off'}), '')

    def test_garbage_input_never_breaks_the_prompt(self):
        result = subprocess.run([sys.executable, str(HOOK), 'prompt'], input='not json', env=self.env(),
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)


class VerifyGateTest(HookCase):
    def edit(self, path):
        return self.run_hook('post', {'tool_name': 'Edit', 'tool_input': {'file_path': str(self.repo / path)},
                                      'tool_response': {}})

    def bash(self, command, output=''):
        return self.run_hook('post', {'tool_name': 'Bash', 'tool_input': {'command': command},
                                      'tool_response': {'stdout': output}})

    def stop(self, active=False, env=None):
        return self.run_hook('stop', {'stop_hook_active': active}, env)

    def blocked(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout.strip():
            return None
        out = json.loads(result.stdout)
        return out['reason'] if out.get('decision') == 'block' else None

    def test_blocks_stop_when_code_changed_after_the_last_test_run(self):
        self.edit('src/fee.ts')
        reason = self.blocked(self.stop())
        self.assertIsNotNone(reason)
        self.assertIn('src/fee.ts', reason)

    def test_test_run_after_the_edit_allows_stop(self):
        self.edit('src/fee.ts')
        self.bash('npm test', 'Tests: 3 passed')
        self.assertIsNone(self.blocked(self.stop()))

    def test_reminds_once_per_change_set(self):
        self.edit('src/fee.ts')
        self.assertIsNotNone(self.blocked(self.stop()))
        self.assertIsNone(self.blocked(self.stop()))

    def test_never_blocks_a_continuation(self):
        self.edit('src/fee.ts')
        self.assertIsNone(self.blocked(self.stop(active=True)))

    def test_mentioning_a_test_tool_does_not_count_as_a_test_run(self):
        self.edit('src/fee.ts')
        self.bash('npm install -D jest')
        self.assertIsNotNone(self.blocked(self.stop()))

    def test_a_write_chained_after_a_test_run_is_tracked(self):
        self.bash("npm test; sed -i 's/a/b/' src/app.py", 'Tests: 2 passed')
        self.assertIsNotNone(self.blocked(self.stop()))

    def test_concurrent_read_only_posts_keep_the_change_set(self):
        self.edit('src/fee.ts')
        payload = json.dumps({'session_id': 's1', 'cwd': str(self.repo), 'tool_name': 'Bash',
                              'tool_input': {'command': 'ls'}, 'tool_response': {}})
        procs = [subprocess.Popen([sys.executable, str(HOOK), 'post'], stdin=subprocess.PIPE, env=self.env(),
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for _ in range(16)]
        for proc in procs:
            proc.communicate(payload.encode())
        self.assertIsNotNone(self.blocked(self.stop()))

    def test_docs_and_config_edits_do_not_need_tests(self):
        self.edit('README.md')
        self.edit('config/app.yaml')
        self.assertIsNone(self.blocked(self.stop()))

    def test_no_test_setup_no_reminder(self):
        (self.repo / 'package.json').unlink()
        self.edit('src/fee.ts')
        self.assertIsNone(self.blocked(self.stop()))

    def test_can_be_turned_off(self):
        self.edit('src/fee.ts')
        self.assertIsNone(self.blocked(self.stop(env={'TEA_SDLC_VERIFY_GATE': 'off'})))

    def test_reminders_are_capped_per_session(self):
        for name in ('a', 'b', 'c', 'd'):
            self.edit(f'src/{name}.ts')
            self.stop()
        self.edit('src/e.ts')
        self.assertIsNone(self.blocked(self.stop()))


class NudgeTest(HookCase):
    def bash(self, command, output=''):
        return self.context(self.run_hook('post', {'tool_name': 'Bash', 'tool_input': {'command': command},
                                                   'tool_response': {'stdout': output}}), 'PostToolUse')

    def test_three_failing_runs_in_a_row_suggest_systematic_debugging(self):
        self.assertEqual(self.bash('npx vitest run', 'Tests: 1 failed'), '')
        self.assertEqual(self.bash('npx vitest run', 'Tests: 1 failed'), '')
        self.assertIn('tea-sdlc:systematic-debugging', self.bash('npx vitest run', 'Tests: 1 failed'))

    def test_a_green_run_resets_the_failure_streak(self):
        self.bash('pytest', '1 failed')
        self.bash('pytest', '1 failed')
        self.bash('pytest', '3 passed')
        self.assertEqual(self.bash('pytest', '1 failed'), '')

    def test_revert_suggests_incident_to_eval(self):
        self.assertIn('tea-sdlc:incident-to-eval', self.bash('git revert --no-edit abc123', '[main 1a2b3c] Revert'))

    def test_merge_with_an_accepted_spec_suggests_promoting_docs(self):
        spec = self.repo / 'docs' / 'specs' / 'refund'
        spec.mkdir(parents=True)
        (spec / 'README.md').write_text('---\nstatus: accepted\ncontract: none\n---\n# Refund\n')
        ctx = self.bash('gh pr merge 42 --squash', 'Merged')
        self.assertIn('tea-sdlc:upgrade-service-docs', ctx)
        self.assertIn('refund', ctx)

    def test_merge_of_a_shipped_spec_suggests_promoting_docs(self):
        spec = self.repo / 'docs' / 'specs' / 'payouts'
        spec.mkdir(parents=True)
        (spec / 'README.md').write_text('---\nstatus: shipped\nkey: PAY\n---\n# Payouts\n')
        self.assertIn('tea-sdlc:upgrade-service-docs', self.bash('gh pr merge 9 --squash', 'Merged'))

    def test_merge_without_active_specs_is_silent(self):
        self.assertEqual(self.bash('gh pr merge 42 --squash', 'Merged'), '')


class SubagentRulesTest(HookCase):
    def start(self, agent_type, env=None):
        return self.context(self.run_hook('subagent', {'agent_type': agent_type, 'agent_id': 'a1'}, env), 'SubagentStart')

    def test_implementers_get_the_house_rules(self):
        ctx = self.start('tea-sdlc:backend-engineer-subagent')
        for fragment in ('BLOCKED', 'requirement ID', 'tdd-gate', 'contracts/', 'do not dispatch'):
            self.assertIn(fragment, ctx)
        self.assertLess(len(ctx), 2000)

    def test_general_purpose_agents_get_them_too(self):
        self.assertIn('BLOCKED', self.start('general-purpose'))

    def test_read_only_built_ins_are_left_alone(self):
        for agent in ('Explore', 'claude-code-guide', 'statusline-setup'):
            self.assertEqual(self.start(agent), '', agent)

    def test_off_switch(self):
        self.assertEqual(self.start('general-purpose', {'TEA_SDLC_AUTOPILOT': 'off'}), '')


class SessionSnapshotTest(HookCase):
    def start(self, env=None):
        env = self.env(env)
        env['PATH'] = '/usr/bin:/bin'  # no gitleaks on this PATH
        result = subprocess.run(['/bin/bash', str(SESSION_START)], input=json.dumps({'cwd': str(self.repo),
                                'source': 'startup', 'session_id': 's1'}), env=env, capture_output=True, text=True,
                                timeout=20, cwd=str(self.repo))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_bootstrap_still_injected(self):
        out = self.start()
        self.assertIn('<session-bootstrap>', out['hookSpecificOutput']['additionalContext'])

    def test_reports_active_specs_with_plan_progress(self):
        spec = self.repo / 'docs' / 'specs' / 'refund'
        spec.mkdir(parents=True)
        (spec / 'README.md').write_text('---\nstatus: accepted\ncontract: external\n---\n')
        (spec / 'plan.md').write_text('- [x] one\n- [ ] two\n- [ ] three\n')
        ctx = self.start()['hookSpecificOutput']['additionalContext']
        self.assertIn('docs/specs/refund', ctx)
        self.assertIn('1/3', ctx)

    def test_spec_paths_are_resolved_from_the_repo_root(self):
        git_env = {**os.environ, 'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1'}
        subprocess.run(['git', 'init', '-q'], cwd=self.repo, check=True, env=git_env)
        spec = self.repo / 'docs' / 'specs' / 'refund'
        spec.mkdir(parents=True)
        (spec / 'README.md').write_text('---\nstatus: accepted\nkey: RFD\n---\n')
        (spec / 'plan.md').write_text('- [x] one\n- [ ] two\n')
        (self.repo / 'src').mkdir()
        env = self.env()
        env['PATH'] = '/usr/bin:/bin'
        result = subprocess.run(['/bin/bash', str(SESSION_START)], input=json.dumps({'cwd': str(self.repo / 'src')}),
                                env=env, capture_output=True, text=True, timeout=20, cwd=str(self.repo / 'src'))
        ctx = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
        self.assertIn('Spec docs/specs/refund at stage `accepted`, 1/2 tickets done', ctx)
        self.assertNotIn('src/docs', ctx)

    def test_workflow_mode_is_announced(self):
        ctx = self.start()['hookSpecificOutput']['additionalContext']
        self.assertIn('Workflow mode: lean', ctx)
        env = self.env({'TEA_SDLC_WORKFLOW': 'full'})
        result = subprocess.run(['/bin/bash', str(SESSION_START)], input=json.dumps({'cwd': str(self.repo)}),
                                env=env, capture_output=True, text=True, timeout=20, cwd=str(self.repo))
        self.assertIn('Workflow mode: full', json.loads(result.stdout)['hookSpecificOutput']['additionalContext'])

    def test_resumable_goal_state_is_announced(self):
        (self.repo / '.goal').mkdir()
        (self.repo / '.goal' / 'state.md').write_text('goal')
        self.assertIn('.goal/state.md', self.start()['hookSpecificOutput']['additionalContext'])

    def test_missing_gitleaks_is_told_to_the_user_up_front(self):
        self.assertIn('gitleaks', self.start().get('systemMessage', ''))

    def enable_superpowers(self, local_override=None):
        settings = self.repo / '.claude'
        settings.mkdir(exist_ok=True)
        (settings / 'settings.json').write_text(json.dumps({'enabledPlugins': {
            'superpowers@anthropic-plugin-directory': True, 'tea-sdlc@tea-sdlc': True}}))
        if local_override is not None:
            (settings / 'settings.local.json').write_text(json.dumps({'enabledPlugins': {
                'superpowers@anthropic-plugin-directory': local_override}}))

    def test_overlapping_superpowers_plugin_is_resolved(self):
        self.enable_superpowers()
        ctx = self.start()['hookSpecificOutput']['additionalContext']
        self.assertIn('superpowers', ctx)
        self.assertIn('tea-sdlc:spec', ctx)

    def test_superpowers_disabled_locally_is_not_mentioned(self):
        self.enable_superpowers(local_override=False)
        self.assertNotIn('superpowers', self.start()['hookSpecificOutput']['additionalContext'].split(
            '</session-bootstrap>')[-1])

    def test_old_gate_state_is_pruned(self):
        import time
        state = self.home / '.claude' / 'state' / 'tdd'
        state.mkdir(parents=True)
        old, new = state / 'old.json', state / 'new.json'
        old.write_text('{}')
        new.write_text('{}')
        stale = time.time() - 40 * 86400
        os.utime(old, (stale, stale))
        self.start()
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_missing_living_docs_suggest_generation(self):
        self.assertIn('tea-sdlc:generate-service-docs', self.start()['hookSpecificOutput']['additionalContext'])


if __name__ == '__main__':
    unittest.main()
