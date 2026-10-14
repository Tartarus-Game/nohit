"""Fault injection into the acceptance contract, using actual native evidence."""
import copy
import json
from pathlib import Path
import unittest
from run_suite import validate_nohit, validate_replay

EVIDENCE = Path(__file__).parents[2] / 'research/native-meow-delivery'

class AcceptanceFaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        report = json.loads((EVIDENCE/'suite.json').read_text())
        case = report['cases'][0]
        cls.candidate = json.loads((EVIDENCE/case['candidate']).read_text())
        cls.replay = json.loads((EVIDENCE/case['replay']).read_text())

    def test_actual_trace_is_accepted(self):
        validate_replay(self.candidate, self.replay)

    def test_regained_hp_cannot_hide_damage(self):
        d = copy.deepcopy(self.candidate)
        d['damage_calls'] = 1
        with self.assertRaises(ValueError): validate_nohit(d)

    def test_temporary_kr_cannot_hide_at_end(self):
        d = copy.deepcopy(self.candidate)
        d['states'][100]['kr'] = 1
        with self.assertRaises(ValueError): validate_nohit(d)

    def test_invulnerability_is_rejected(self):
        d = copy.deepcopy(self.candidate)
        d['states'][100]['invulnerable'] = True
        with self.assertRaises(ValueError): validate_nohit(d)

    def test_incomplete_attack_is_rejected(self):
        d = copy.deepcopy(self.candidate)
        d['observed_bullets'] -= 1
        with self.assertRaises(ValueError): validate_nohit(d)

    def test_different_input_or_position_is_rejected(self):
        for key in ('route','states'):
            d = copy.deepcopy(self.replay)
            if key == 'route': d[key][100] ^= 1
            else: d[key][100]['x'] += 0.000001
            with self.assertRaises(ValueError): validate_replay(self.candidate,d)

if __name__ == '__main__': unittest.main()
