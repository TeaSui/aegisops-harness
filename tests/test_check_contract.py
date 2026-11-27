import importlib.util
import json
import pathlib
import tempfile
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / 'plugins' / 'aegisops-harness' / 'scripts' / 'check-contract.py'
spec = importlib.util.spec_from_file_location('check_contract', SCRIPT)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

ERROR = {'content': {'application/json': {'schema': {'type': 'object', 'properties': {
    'error': {'type': 'object', 'properties': {'code': {'type': 'string'}, 'message': {'type': 'string'}}}}}}}}


def op(oid='getUser', ok=('200',), err=('404',), body=None, ok_props=None):
    responses = {code: {'description': 'ok', 'content': {'application/json': {'schema': {
        'type': 'object', 'properties': ok_props or {'id': {'type': 'string'}}}}}} for code in ok}
    responses.update({code: {'description': 'err', **ERROR} for code in err})
    out = {'operationId': oid, 'responses': responses}
    if body:
        out['requestBody'] = {'content': {'application/json': {'schema': body}}}
    return out


def full(paths):
    return {'openapi': '3.0.3', 'info': {'title': 'T', 'version': '1'}, 'paths': paths}


class CheckContractTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)
        self.spec = self.root / 'docs' / 'specs' / 'feat'
        (self.spec / 'contracts').mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def readme(self, **meta):
        lines = ['---'] + [f'{k}: {v}' for k, v in meta.items()] + ['---', '# feat']
        (self.spec / 'README.md').write_text('\n'.join(lines))

    def contract(self, doc, name='api.json'):
        (self.spec / 'contracts' / name).write_text(doc if isinstance(doc, str) else json.dumps(doc))

    def base(self, doc):
        (self.root / 'api').mkdir(exist_ok=True)
        (self.root / 'api' / 'openapi.json').write_text(json.dumps(doc))

    def run_gate(self):
        return cc.run(self.spec, repo_arg=self.root)

    def failed(self, findings):
        return [m for level, m in findings if level == 'FAIL']

    def test_contract_none_passes(self):
        self.readme(contract='none')
        self.assertEqual(self.failed(self.run_gate()), [])

    def test_no_readme_and_no_contracts_is_none(self):
        (self.spec / 'contracts').rmdir()
        self.assertEqual(self.failed(self.run_gate()), [])

    def test_external_without_contract_files_fails(self):
        self.readme(contract='external')
        self.assertTrue(any('missing or empty' in m for m in self.failed(self.run_gate())))

    def test_valid_full_document_passes(self):
        self.readme(contract='external')
        self.contract(full({'/u': {'get': op()}}))
        self.assertEqual(self.failed(self.run_gate()), [])

    def test_structure_failures(self):
        self.readme(contract='external')
        cases = {
            'operationId is missing': {'/u': {'get': {k: v for k, v in op().items() if k != 'operationId'}}},
            'duplicates': {'/u': {'get': op('x')}, '/v': {'get': op('x')}},
            'no 2xx': {'/u': {'get': op(ok=())}},
            'error response': {'/u': {'get': op(err=())}},
        }
        for needle, paths in cases.items():
            self.contract(full(paths))
            self.assertTrue(any(needle in m for m in self.failed(self.run_gate())), needle)

    def test_unresolved_ref_fails(self):
        self.readme(contract='external')
        doc = full({'/u': {'get': op()}})
        doc['paths']['/u']['get']['parameters'] = [{'$ref': '#/components/parameters/Missing'}]
        self.contract(doc)
        self.assertTrue(any('unresolved $ref' in m for m in self.failed(self.run_gate())))

    def test_delta_without_info_passes(self):
        self.readme(contract='external')
        self.contract({'paths': {'/u': {'get': op()}}})
        self.assertEqual(self.failed(self.run_gate()), [])

    def test_unparsable_json_fails(self):
        self.readme(contract='external')
        self.contract('{not json')
        self.assertTrue(any('does not parse' in m for m in self.failed(self.run_gate())))

    def test_removed_response_property_is_breaking(self):
        self.readme(contract='external')
        self.base(full({'/u': {'get': op(ok_props={'id': {'type': 'string'}, 'name': {'type': 'string'}})}}))
        self.contract({'paths': {'/u': {'get': op(ok_props={'id': {'type': 'string'}})}}})
        self.assertTrue(any("'name' removed" in m for m in self.failed(self.run_gate())))

    def test_changed_type_is_breaking(self):
        self.readme(contract='external')
        self.base(full({'/u': {'get': op(ok_props={'id': {'type': 'string'}})}}))
        self.contract({'paths': {'/u': {'get': op(ok_props={'id': {'type': 'integer'}})}}})
        self.assertTrue(any('changed type' in m for m in self.failed(self.run_gate())))

    def test_new_required_request_property_is_breaking(self):
        self.readme(contract='external')
        old = {'type': 'object', 'properties': {'a': {'type': 'string'}}}
        new = {'type': 'object', 'required': ['b'], 'properties': {'a': {'type': 'string'}, 'b': {'type': 'string'}}}
        self.base(full({'/u': {'post': op('create', body=old)}}))
        self.contract({'paths': {'/u': {'post': op('create', body=new)}}})
        self.assertTrue(any('new required request property' in m for m in self.failed(self.run_gate())))

    def test_additive_change_is_compatible(self):
        self.readme(contract='external')
        self.base(full({'/u': {'get': op(ok_props={'id': {'type': 'string'}})}}))
        self.contract({'paths': {'/u': {'get': op(ok_props={'id': {'type': 'string'}, 'extra': {'type': 'string'}})}}})
        self.assertEqual(self.failed(self.run_gate()), [])

    def test_approved_breaking_change_downgrades_to_warning(self):
        self.readme(contract='external', breaking='approved')
        self.base(full({'/u': {'get': op(ok_props={'id': {'type': 'string'}, 'name': {'type': 'string'}})}}))
        self.contract({'paths': {'/u': {'get': op(ok_props={'id': {'type': 'string'}})}}})
        findings = self.run_gate()
        self.assertEqual(self.failed(findings), [])
        self.assertTrue(any(level == 'WARN' and 'approved' in m for level, m in findings))

    def test_yaml_without_any_parser_warns_and_does_not_claim_a_clean_pass(self):
        self.readme(contract='external')
        self.contract('openapi: 3.0.3\n', name='api.yaml')
        saved_yaml, saved_which = cc.yaml, cc.shutil.which
        cc.yaml, cc.shutil.which = None, lambda _name: None
        try:
            findings = self.run_gate()
        finally:
            cc.yaml, cc.shutil.which = saved_yaml, saved_which
        self.assertEqual(self.failed(findings), [])
        self.assertTrue(any(level == 'WARN' for level, _ in findings))
        self.assertTrue(any('WITH WARNINGS' in m for _, m in findings))

    @unittest.skipUnless(cc.shutil.which('ruby'), 'ruby not installed')
    def test_yaml_is_parsed_through_ruby_when_pyyaml_is_missing(self):
        self.readme(contract='external')
        good = ('openapi: 3.0.3\ninfo: {title: T, version: "1"}\npaths:\n  /u:\n    get:\n      operationId: getUser\n'
                '      responses:\n        "200": {description: ok}\n        "404":\n          description: err\n'
                '          content:\n            application/json:\n              schema:\n                type: object\n'
                '                properties:\n                  error:\n                    type: object\n'
                '                    properties: {code: {type: string}, message: {type: string}}\n')
        saved = cc.yaml
        cc.yaml = None
        try:
            self.contract(good, name='api.yaml')
            self.assertEqual(self.failed(self.run_gate()), [])
            self.contract(good.replace('      operationId: getUser\n', ''), name='api.yaml')
            self.assertTrue(any('operationId is missing' in m for m in self.failed(self.run_gate())))
            self.contract('openapi: 3.0.3\ndescription: Response carries a body: not allowed here\n', name='api.yaml')
            self.assertTrue(any('does not parse' in m for m in self.failed(self.run_gate())))
        finally:
            cc.yaml = saved

    def test_active_specs_cover_every_active_aidlc_stage(self):
        for status in ('proposed', 'accepted', 'planned', 'building', 'verified', 'reviewed', 'shipped'):
            self.readme(contract='external', status=status)
            self.assertEqual(cc.active_specs(self.root), [self.spec], status)
        for status in ('implemented', 'partially-implemented', 'superseded', 'abandoned'):
            self.readme(contract='external', status=status)
            self.assertEqual(cc.active_specs(self.root), [], status)

    def test_exit_codes(self):
        self.readme(contract='external')
        self.contract(full({'/u': {'get': op()}}))
        self.assertEqual(cc.main([str(self.spec), '--repo', str(self.root)]), 0)
        self.contract(full({'/u': {'get': op(ok=())}}))
        self.assertEqual(cc.main([str(self.spec), '--repo', str(self.root)]), 1)
        self.assertEqual(cc.main([str(self.root / 'nope')]), 2)


if __name__ == '__main__':
    unittest.main()
