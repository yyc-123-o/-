# Learner Profile Agent Import

## Source

- Remote branch: `学情agent`
- Source commit: `3684063a6d4e6db3f750526010b066dd8dd9b41b`
- Imported snapshot: `学情诊断Agent/`

The snapshot was downloaded from the repository API because the local Git
transport could not connect to GitHub. It is kept as a standalone FastAPI
application and has not been merged into the three-Agent platform graph.

## Contents

- IRT ability estimation with prior shrinkage
- Knowledge-point mastery and gap analysis
- Adaptive testing
- Chapter-level depth labels and resource-generation hints
- Mock learners, question bank, and the ECharts web console

Generated `__pycache__` directories and `test_outputs/` artifacts were omitted.

## Integration Boundary

The standalone output is `LearnerProfile` v2.1. The platform currently accepts
the normalized `LearnerProfileSnapshot` contract, so an adapter is still needed
before this Agent can become the platform's input stage. The adapter must map
concept IDs, graph version, mastery, abilities, error patterns, preferences, and
provenance without copying path or resource decisions into the profile snapshot.

The imported Agent declares `numpy` and `scipy` dependencies separately from the
platform environment. The current project environment can compile the files but
does not yet provide `scipy`; install the Agent's requirements in an isolated
environment before running its IRT service.
