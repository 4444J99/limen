"""Exercise the exact fixed-event predicate; no credential or provider calls."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]
TEXT=(ROOT/'.github/workflows/ops-owner-release.yml').read_text()
PREDICATE=' '.join(TEXT.split('    if: >-\n',1)[1].split('    uses:',1)[0].split())
def allowed(event='issue_comment',action='created',issue=2731,user=24796448,body='/ops inspect'):
 values={'github.event_name':event,'github.event.action':action,'github.event.issue.number':issue,
         'github.event.comment.user.id':user,'github.event.comment.body':body}
 expression=PREDICATE
 for key in sorted(values,key=len,reverse=True):expression=expression.replace(key,repr(values[key]))
 return eval(expression.replace('&&',' and ').replace('||',' or '),{'__builtins__':{}},{})
class CarrierTests(unittest.TestCase):
 def test_one_fixed_owner_read_command(self):self.assertTrue(allowed())
 def test_wrong_owner_or_thread_refused(self):
  self.assertFalse(allowed(user=1));self.assertFalse(allowed(issue=2732))
 def test_edits_and_other_events_refused(self):
  self.assertFalse(allowed(action='edited'));self.assertFalse(allowed(event='pull_request'))
 def test_arbitrary_commands_or_code_refused(self):
  for text in ('/ops deploy','/ops inspect main','/ops inspect\nrm -rf /',' /ops inspect'):
   self.assertFalse(allowed(body=text))
 def test_existing_accepted_main_carriers_preserved(self):
  self.assertTrue(allowed(event='push'));self.assertTrue(allowed(event='workflow_dispatch'))
 def test_recovery_source_is_independent_of_workflow_pin(self):
  self.assertIn('@08d493caf5cf6fe7a64cbb67f6ed7e6b07ea119e',TEXT)
  self.assertIn("source_sha: 62469ec5b402460a5610145e67901fcdd0ca00b9",TEXT)
  self.assertIn("OPS_SOURCE_GITHUB_TOKEN: ${{ secrets.OPS_SOURCE_GITHUB_TOKEN }}",TEXT)
 def test_apply_defaults_to_inspection(self):
  self.assertIn("default: false",TEXT)
  self.assertEqual(apply_source(), "")
 def test_only_owner_manual_main_apply(self):
  self.assertEqual(apply_source(apply=True), "62469ec5b402460a5610145e67901fcdd0ca00b9")
  for overrides in ({"actor":"1"},{"ref":"refs/heads/topic"},{"event":"push"},{"event":"issue_comment"},{"event":"pull_request"}):
   self.assertEqual(apply_source(apply=True,**overrides), "")

def apply_source(event="workflow_dispatch",actor="24796448",ref="refs/heads/main",apply=False):
 expression=TEXT.split("      apply_source: ${{ ",1)[1].split(" }}",1)[0]
 values={"github.event_name":event,"github.actor_id":actor,"github.ref":ref,"inputs.apply":apply}
 for key,value in values.items():expression=expression.replace(key,repr(value))
 return eval(expression.replace("&&"," and ").replace("||"," or ").replace("true","True"),{"__builtins__":{}},{})
