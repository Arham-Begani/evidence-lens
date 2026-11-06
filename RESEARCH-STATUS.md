# Research status and unresolved wording

This is pre-sprint development, with internal AI-assisted review and no independent human adjudication. The 16 saved answers concern one JumbledPath case and one order. They do not establish method superiority, generalization, calibrated confidence or an event-weekend result.

Two wording questions remain open. These are development adjudication items, not evaluation examples or independently established errors. The claims below are quoted exactly; their full answers and limitations remain unchanged.

## R02, claim 1

> The supplied paraphrase attributes Salt Typhoon’s use of JumbledPath to MITRE ATT&CK.

The phrase can be read awkwardly: MITRE is the reporting source, not the actor using the tool. The relationship field identifies it as a paraphrase of MITRE reporting. A human reviewer must decide whether that context resolves the ambiguity under a fixed support policy.

[Exact answer](site/7a30c35f9f6386277f304db9/answer.json) · [Exact input](site/7a30c35f9f6386277f304db9/prompt.txt)

Canonical answer SHA-256: `e2b6e1bfd57cf102300f3758bc8a8f0243a939f180ce1c651208738e70d50006`.

Human decision: **pending**.

## R06, claim 2

> The JumbledPath capability attributed to Salt Typhoon also includes compression and encryption of captured packet data. The cards do not establish that the actor exercised these functions in a particular operation.

A human reviewer must distinguish a qualified inference about a reported tool's functionality from evidence that the actor exercised that functionality. Read the claim, relationship and limitations together; do not silently rewrite the original statement into a stronger or weaker claim.

[Exact answer](site/1e8881dd77a5da978cd1128b/attempt-2/answer.json) · [Exact input](site/1e8881dd77a5da978cd1128b/attempt-2/prompt.txt)

Canonical answer SHA-256: `02f9c3d4cb0cef6a8034a3196b1d6b79be3263510adb4b3415f814d0f43bc777`.

Human decision: **pending**.

## Review and prospective study

The [blank shuffled review sheet](site/semantic-review-blank.csv) has no human decisions filled in. Reviewers seeking method blinding should use it before browsing method-labeled answers or internal judgments; answer style can still reveal the method. Reading this document also exposes the two development flags, so disclose that exposure. AI organization of a packet is not independent human review.

A separately prepared prospective protocol proposes six source families, six evidence conditions, two orders and four methods: 288 scheduled responses. That protocol is a draft, not frozen, preregistered, implemented or executed. The current code has four conditions and must not be described as implementing the proposed six-condition design. The 192-cell CLI fixture is a scripted engineering check of the current implementation.

Before evaluating, the proposed study needs lawful source review, distinct-observation and unresolved-origin controls, balanced packet lengths, a fixed qualified-inference rubric with an observation-only sensitivity analysis, source-root separation from development, real reviewers, a frozen model/configuration and an authorized resource budget. Missing and unresolved answers need explicit denominators and bounds. Existing development examples must not become evaluation evidence.

All current code, source cards, captured outputs, UI and review preparation predate the December 4–6, 2026 sprint. Record the actual event contribution separately. Eligibility, any guardian/prize requirements, author affiliation and the official-template final report remain unresolved.
