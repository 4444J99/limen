import json
import unittest
from unittest.mock import Mock
import schema_probe as m

class SchemaProbeTests(unittest.TestCase):
 def test_identifies_schema_mismatch_without_echoing_values(self):
  self.assertEqual(m.diagnose('D1_ERROR: no such column: lease_owner: SQLITE_ERROR; private-secret'),{'category':'missing_column','schema_identifier':'lease_owner'})
  self.assertEqual(m.diagnose('table jobs has no column named claim_owner'),{'category':'unknown_insert_column','schema_identifier':'claim_owner'})
  self.assertEqual(m.diagnose('D1_ERROR: no such table: webhook_deliveries: SQLITE_ERROR'),{'category':'missing_table','schema_identifier':'webhook_deliveries'})
  self.assertNotIn('private-secret',json.dumps(m.diagnose('private-secret')))
 def test_only_schema_pragmas_are_allowed(self):
  client=object.__new__(m.Client);client.aid='a'*32;client.db='known';client.request=Mock(return_value=[{'success':True,'results':[{'name':'id','dflt_value':'private-value'}]}])
  self.assertEqual(client.schema('jobs'),['id'])
  args=client.request.call_args.args
  self.assertEqual(json.loads(args[2])['sql'],'PRAGMA table_info(jobs)')
  with self.assertRaises(m.r.inv.o.SafeError):client.schema('jobs);DROP TABLE jobs;--')
 def test_sql_identifiers_are_not_arbitrary_provider_text(self):
  client=object.__new__(m.Client);client.aid='a'*32;client.db='known';client.request=Mock(return_value=[{'success':True,'results':[{'name':'private-secret'}]}])
  with self.assertRaises(m.r.inv.o.SafeError):client.schema('jobs')

class ErrorRecordTests(unittest.TestCase):
 def test_nested_errors_are_classified_without_payloads_or_credentials(self):
  value={'target':'ucc-staging','results':[{'payload':'private-value','error':'D1_ERROR: no such column: missing_column: SQLITE_ERROR'}]}
  result=m.error_categories(value)
  self.assertEqual(result,[{'category':'missing_column','schema_identifier':'missing_column'}])
  self.assertNotIn('private-value',json.dumps(result))
 def test_query_is_bounded_and_excludes_shared_state(self):
  c=Mock();c.aid='a'*32;c.db='known';c.request.side_effect=[[{'success':True,'results':[{'name':'scheduler_state'}]}],[{'success':True,'results':[{'name':'id'},{'name':'payload'}]}],[{'success':True,'results':[{'payload':json.dumps({'error':'SQLITE_ERROR: syntax error'})}]}]]
  result=m.recent_failures(c)
  self.assertEqual(result['error_categories'],[{'category':'syntax_error'}])
  query=json.loads(c.request.call_args.args[2])['sql']
  self.assertIn('LIMIT 12',query);self.assertIn("id <> 'scheduler:state'",query)
