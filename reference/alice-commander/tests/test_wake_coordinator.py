import importlib.util,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('rgb_coordinator',Path(__file__).resolve().parents[2]/'pc-notifications/agent.py');a=importlib.util.module_from_spec(spec)
with patch('logging.basicConfig'):
    spec.loader.exec_module(a)
class Ownership(unittest.TestCase):
    def tearDown(self):a.BUSY=False;a.ACTIVE_JOB=None;a.CANCEL.clear()
    def test_stop_cannot_cancel_manual_or_other_wake(self):
        a.BUSY=True;a.ACTIVE_JOB={'effect':'rainbow'}
        self.assertFalse(a.wake_control({'action':'stop','request_id':'a'*32})['cancelled']);self.assertFalse(a.CANCEL.is_set())
        a.ACTIVE_JOB={'_wake_request':'b'*32}
        self.assertFalse(a.wake_control({'action':'stop','request_id':'a'*32})['cancelled']);self.assertFalse(a.CANCEL.is_set())
    def test_owned_stop_yields_without_new_job(self):
        a.BUSY=True;a.ACTIVE_JOB={'_wake_request':'a'*32}
        self.assertTrue(a.wake_control({'action':'stop','request_id':'a'*32})['cancelled']);self.assertTrue(a.CANCEL.is_set());self.assertTrue(a.ACTIVE_JOB['_native_yield'])
    def test_start_is_always_two_seconds_and_existing_submit(self):
        with patch.object(a,'cfg',return_value={'palette':'purple','brightness_percent':25}), patch.object(a,'submit',return_value=(True,'accepted')) as submit:
            result=a.wake_control({'action':'start','request_id':'a'*32})
            self.assertTrue(result['accepted']);job=submit.call_args.args[0];self.assertEqual(job['duration'],2);self.assertEqual(job['effect'],'rainbow')
    def test_reject_unknown_fields_and_actions(self):
        for value in ({'action':'exec','request_id':'a'*32},{'action':'start','request_id':'bad'},{'action':'start','request_id':'a'*32,'argv':['id']}):
            with self.assertRaises(ValueError):a.wake_control(value)
