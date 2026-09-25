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
 def test_comment_can_never_supply_source_or_apply(self):
  self.assertNotIn('apply_source:',TEXT)
  pin=re.search(r'uses: 4444J99/ops/[^\n]+@([a-f0-9]{40})',TEXT).group(1)
  self.assertIn('source_sha: '+pin,TEXT)
  self.assertNotIn('${{ github.event',TEXT)
