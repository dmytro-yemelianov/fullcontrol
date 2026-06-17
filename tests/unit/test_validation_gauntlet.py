"""The validation gauntlet is self-checking: every entry must trip exactly the rule it
documents. This test runs each gauntlet design through the 'validate' backend and asserts the
EXPECTED (severity, substring) message fires - if a design ever stops tripping its rule, this
fails. It also pins EXPECTED and the gauntlet to the same set of rule names so no rule is left
undocumented (or documented but absent).
"""
import fullcontrol as fc

from examples.validation_gauntlet import EXPECTED, INIT, validation_gauntlet


def _validate(steps, init):
    return fc.transform(steps, 'validate',
                        fc.GcodeControls(printer_name='generic', initialization_data=init),
                        show_tips=False)


def _messages_for_severity(result, severity):
    return [i['message'] for i in result.issues if i['severity'] == severity]


def test_expected_documents_every_gauntlet_rule_and_no_more():
    gauntlet = validation_gauntlet()
    assert set(EXPECTED) == set(gauntlet), (
        'EXPECTED and the gauntlet must cover exactly the same rules')
    assert set(INIT) == set(gauntlet), (
        'INIT must provide initialization_data for exactly the same rules')


def test_every_gauntlet_design_trips_its_rule():
    gauntlet = validation_gauntlet()
    for rule, steps in gauntlet.items():
        severity, substring = EXPECTED[rule]
        result = _validate(steps, INIT[rule])
        messages = _messages_for_severity(result, severity)
        assert any(substring in m for m in messages), (
            f'rule {rule!r}: expected a {severity} message containing {substring!r}, '
            f'got {severity}s={messages!r} (all issues={result.issues!r})')


def test_each_gauntlet_design_has_at_least_one_point():
    # an empty design raises 'No point found in steps...'; every entry must define a Point
    for rule, steps in validation_gauntlet().items():
        assert any(isinstance(s, fc.Point) for s in steps), (
            f'rule {rule!r}: design must contain at least one Point')
