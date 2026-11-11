# tests/

Unit and integration tests written while developing the family. They aid construction; the checks
that decide whether the code is correct live in `verification/`.

Tests of the verification machinery itself (planted-defect demonstrations, certifier behavior)
also live here: they are ordinary tests about code.

`qf-signals validate` requires this directory to exist for every active family. The scaffold
ships it with no tests yet.
