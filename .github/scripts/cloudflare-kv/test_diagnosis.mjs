import assert from 'node:assert/strict';
import test from 'node:test';
import {failureDiagnosis} from './diagnosis.mjs';
test('SQL failures retain only actionable class and schema identifier',()=>{
 for(const [text,expected] of [
  ['D1_ERROR: no such column: w.enabled: SQLITE_ERROR',{category:'missing_column',schema_identifier:'w.enabled'}],
  ['D1_ERROR: no such table: queue_records: SQLITE_ERROR',{category:'missing_table',schema_identifier:'queue_records'}],
  ['no such function: NOW',{category:'missing_function',schema_identifier:'NOW'}],
  ['NOT NULL constraint failed: jobs.org_id; private-secret',{category:'not_null',schema_identifier:'jobs.org_id'}],
  ['D1_ERROR near FOR: syntax error; private-secret',{category:'syntax_error'}],
  ['D1_TYPE_ERROR: Type undefined is not supported',{category:'bind_type'}],
 ]) assert.deepEqual(failureDiagnosis(text),expected);
});
test('arbitrary request and provider values are not copied',()=>{
 assert.deepEqual(failureDiagnosis('private-secret'),{category:'unclassified'});
 assert.deepEqual(failureDiagnosis('SQLITE_ERROR: private-secret'),{category:'database_unclassified'});
});
