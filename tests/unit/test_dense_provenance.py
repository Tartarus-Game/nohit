import copy
import pytest
from scratch.dense_provenance import validate,canonical_hash,dependencies

def test_dependencies_include_environment_operator_and_representation():
    names={path.name for path in dependencies()}
    assert {'resumable_wave.py','compact_wave.py','parametric_environment.py',
            'dialogue_operator.py','environment_state_key.py','discrete_operator.py',
            'cspace.py','red_axis_expansion.py','red_dense_frontier.py'}<=names

@pytest.mark.parametrize('field',['source','clock','operator','cspace','dense','arrays'])
def test_changed_problem_cannot_resume(field):
    original={key:'original' for key in ['source','clock','operator','cspace','dense','arrays']}
    record={'problem':original,'problem_sha256':canonical_hash(original)}
    current=copy.deepcopy(original);current[field]='different'
    with pytest.raises(ValueError,match='model mismatch'):validate(record,current)
    validate(record,original)
