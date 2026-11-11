## Architecture (deep modules: Ousterhout, A Philosophy of Software Design)

- Each module exposes one small, documented entrypoint over deep machinery. Callers depend only on the entrypoint's contract.
- The contract is the full behavior: outputs, dtypes, errors and their order. Optimize freely underneath only while the contract holds bitwise; prove it against a recorded run.
- Pull complexity down: handle hard cases (fallbacks, guards, edge data) inside the module, never in each caller.
- Hide implementation details, never the guarantees callers need (numeric drift, failure behavior); document those in the interface.
- Vary behavior through explicit parameters, not module-level names.
- Prefer one deep function over many shallow wrappers; don't add a layer that only forwards calls.
