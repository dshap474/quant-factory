"""example_signal — core engine surface of the example scaffold signal family.

Engine changes follow AGENTS.md §6: reviewed changes with independent verification. Optimization versions import from here and freeze only their delta.

A family is discovered only through ``src/<module>/runner.py`` calling
``SignalRegistry.register(...)``; this scaffold's runner registers ``planned``, so it is never
listed, smoked, or published.
"""
