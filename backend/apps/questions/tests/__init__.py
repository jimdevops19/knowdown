"""The questions suite, split by what it is about.

One file per concern rather than one ``tests.py``: the loader's refusals, the
evaluator's verdicts and the play-time serializers' silence are three unrelated
subjects, and the third of them is the anti-cheat surface — a suite where it can
be found is a suite where somebody notices it is missing a case.

``factories`` builds question rows directly through the ORM. ``test_sync`` goes
the long way round, through a resources tree it writes itself, because the loader
is the thing it is testing; nothing else needs to pay for that.
"""
