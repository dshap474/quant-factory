# family-registry

The runner registry and family discovery shared by `signals` and `strategies`.

A consuming package subclasses `FamilyRegistry`, points `package_root` at its own
root, and decorates each family runner with `@MyRegistry.register("family-name", ...)`.
Families live at `<package_root>/extensions/lib/<family>/src/<package>/runner.py`.
Underscore directories (`_archive`, `_template`) and runners loaded from `_archive/`
or `optimization/version/` paths are never registered.

```python
from family_registry import FamilyRegistry

class SignalRegistry(FamilyRegistry):
    label = "Signal"
    package_root = SIGNALS_ROOT
    module_prefix = "signals."
    defaults = {"output_type": "time_series", "default_preset": "default"}

SignalRegistry.populate()            # import every family runner
SignalRegistry.catalog()             # {name: metadata}, discovering on first use
SignalRegistry.presets("my-signal")  # preset names under the family's presets_dir
```

The package works with `extensions/` absent: discovery returns nothing.
