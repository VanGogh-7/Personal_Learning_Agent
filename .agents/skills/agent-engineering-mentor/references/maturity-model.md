# Agent Product Maturity Model

## Level 0 — Experiment

Purpose:

* learn an API;
* validate a prompt;
* test a library.

Typical properties:

* local-only;
* hardcoded configuration;
* no persistent state;
* manual testing;
* no failure recovery.

This is acceptable only when explicitly treated as an experiment.

## Level 1 — Demonstrable prototype

Purpose:

* demonstrate the user workflow;
* validate technical feasibility.

Expected minimum:

* main happy path works;
* architecture is understandable;
* known limitations are documented;
* provider calls have basic error reporting;
* secrets are not committed.

Not yet suitable for dependable user use.

## Level 2 — Small-user MVP

Purpose:

* support a limited number of real users;
* collect product feedback.

Expected minimum:

* persistent state;
* database migrations;
* input validation;
* request timeouts;
* bounded agent execution;
* basic structured logging;
* critical-path tests;
* reproducible setup;
* clear data ownership;
* documented recovery procedure;
* basic cost controls;
* basic security boundaries.

## Level 3 — Small-scale production

Purpose:

* provide a dependable service to real users.

Expected minimum:

* explicit service-level expectations;
* health and readiness checks;
* reliable deployment process;
* rollback procedure;
* backups and restore validation;
* metrics and distributed traces where applicable;
* rate limiting;
* retry and idempotency policies;
* provider outage behavior;
* load testing;
* security review;
* evaluation and regression gates;
* incident diagnostics;
* data retention and deletion behavior.

## Level 4 — Scalable production

Purpose:

* serve significant or variable workloads;
* support organizational reliability requirements.

Potential requirements:

* horizontal scaling;
* distributed workers;
* tenant isolation;
* capacity planning;
* autoscaling;
* load shedding;
* regional failure handling;
* disaster recovery;
* formal SLOs;
* cost attribution;
* compliance controls;
* controlled schema and model rollouts.

Level 4 requirements must be justified by measured workload, contractual requirements, or credible near-term demand.

## Classification rule

Classify the product according to its weakest critical dimension, not its most advanced component.

For example:

* advanced LangGraph routing does not compensate for missing authentication;
* Kubernetes does not compensate for missing tests;
* multiple agents do not compensate for uncontrolled loops;
* a vector database does not compensate for poor retrieval evaluation;
* structured logging does not compensate for a missing backup strategy.

## Required report

State:

* current level;
* evidence;
* strongest dimensions;
* weakest critical dimensions;
* immediate requirements for the next level;
* improvements that should be deferred.
