# Functional tests for the TOU analyzer

This suite calls the real `apply_tou_and_anomaly` function on small DataFrames. It is not a syntax check and does not use mocks.

## Run locally or in CI

Use Python 3.12 in a separate virtualenv, then run these commands from the repository root:
```sh
python -m pip install -r requirements-test.txt
python -m unittest discover -s tests -p 'test_*.py' -v
```

This repo has the workflow `.github/workflows/python-functional.yml` (named Python Functional Tests). It runs on `push`, `pull_request`, and `workflow_dispatch`, on `ubuntu-latest`. It uses Python 3.12, installs `requirements-test.txt`, and runs the unittest command above. It has a 10-minute timeout and read-only `contents` permission. Checkout does not keep credentials, and the workflow uses no secrets. The suite uses Python's built-in unittest, so no new test framework is added. The packages in `requirements-test.txt` are for the test environment; they do not lock dependencies for the whole app.

## What is checked
- The On-Peak start time is included in the window, and the end time is Off-Peak.
- Saturday, Sunday, and holidays take priority over On-Peak.
- Holidays apply at every time of day, and an empty holiday list still runs.
- An On-Peak window can cross midnight.
- Cost is calculated from the actual energy, and the original DataFrame is not modified.
- High anomalies, low anomalies, and zero load are detected.
- Unreadable or non-existent holiday dates are ignored, and valid holidays in a mixed list still take effect.

Unreadable dates and dates that do not exist are tested so that they do not make the analysis fail. A mixed holiday list that contains valid and malformed dates keeps the valid holidays.

This suite covers the TOU analysis function. It does not verify the Streamlit UI, file uploads, or the whole app.

## Using this approach with other repositories

The system can survey a repository's language, framework, and existing commands, then propose suitable tests and CI. Automatic setup is not enabled for every repository in this change:

1. The owner chooses which repos to connect to the GitHub App and Jules.
2. Use the existing test framework and dependency lock first. If there is none, propose alternatives and ask for approval before adding any new dependency.
3. Read the entry points and business behavior. Build normal cases, edge cases, and error cases from real evidence.
4. Run in CI, separate from the Controller's secrets, and check that changing the expected results makes the tests fail.
5. The owner reviews and merges the PR, sets the scope of test commands and the trusted check provider, and then confirms Functional Test in the Dashboard.

Finding a framework or a green CI is not enough to turn on automation. Check that the tests match the behavior the owner actually needs, and that jobs do not skip tests.

For this repo, the workflow already exists. This document only checks the files in the repo and does not confirm the actual results of runs. Before enabling Functional Test, check in GitHub Actions that the run on `main` passes. Then use the commands above with the scope `tou_analyzer.py` and the files in the `tests/` folder for bug-fix work. Do not extend the scope to the system's workflows or Controller.
