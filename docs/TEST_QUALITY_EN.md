# Jules behavior checks in CI

This suite is the first adapter. It supports Python 3.12 with unittest only, and it is not enabled automatically for other repos. The owner must review this PR before merging it, then set the quality profile in the Controller directly. Pin the workflow ID, the revision, and the blob SHA of the workflow and of `.github/quality/runner.py`, `.github/quality/phase.py`, and `.github/quality/profile.json`, together with the check name `jules-quality` and the GitHub Actions App ID, using real evidence. Do not turn the system on with placeholder values.

The Controller calls the workflow through a tag pinned to a revision on the default branch. It does not use the workflow or harness from the target PR. A selftest job triggered by `pull_request` is not evidence for accepting work. The system still checks the PR author, the scope, CI, and the existing merge policy. Work without a profile keeps the existing policy until the owner opens the gate for the first time. After the gate is open, deleting the profile makes the work wait for configuration.

## Evidence checked

- Bug-fix work must add or change a test within the existing scope. Run the same test against the base code and the candidate code: the base must fail on a behavior assertion, and the candidate must pass. An import or setup error does not count as red.
- Work that adds tests must pass on the real code, catch a temporary mutation in an app module, and pass again after the original file is restored.
- Work with several members must have a separate result for each member. Passing the whole set through a shared CI run is not enough.
- Tests with no assertion, constant assertions, swallowed exceptions, or a replaced `sys.modules` must be fixed, or reviewed by the owner. Existing tests in the repo are not treated as high quality automatically, and the adapter does not edit existing tests itself.

## How runs are isolated

`runner.py` runs on a host that has no Jules secret and does not import the target code. It reads the Git objects for the given SHAs, builds a temporary snapshot, and runs them in a Python 3.12 container. The container installs `requirements-test.txt` from an approved base only.

The test container has no token, no network, no Docker socket, no host workspace, and no mount for writing reports. The snapshot and `phase.py` are read-only. The user is not root. CPU, RAM, and processes are limited. The container is removed when the run finishes or times out.

Each phase is limited to 180 seconds. The wrapper as a whole is limited to about 12 minutes, and the job to 15 minutes. Mutation experiments are limited to 3 per member and are never pushed. Output is kept in limited memory. The report is built on the host after the process ends. The Controller reads it as bounded JSON, and no artifact is extracted or executed.

`test_command` names the unittest command that the profile allows. `executed_commands` records the argv of each phase that actually ran inside the container. This keeps the policy values separate from what really ran.

## Limits and enabling

Static screening, red/green checks, and mutation sensitivity are evidence for specific cases only. They do not prove coverage of the whole app, and they do not guarantee that deliberately misleading tests will always be caught. The target's stdout is still untrusted data. Pinning the wrapper and checking its provenance, and the owner's PR review, are still required.

If the framework, the imports, or the layout is not supported, or the scope has no test files, mark only that work as BLOCKED. Do not expand the scope or the dependencies on your own.

Before enabling the profile, run this on GitHub CI, which has Docker:

```sh
python -m unittest discover -s tests -p test_quality_runner.py -v
```

On a local machine without Docker, the container checks are skipped. Report that as "container not tested". Do not use mock or static results, or a skipped selftest, in place of real container results. Merge and enabling still need separate approval.
