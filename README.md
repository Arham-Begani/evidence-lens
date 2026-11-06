# Evidence Lens

Trace a saved capability assessment to the exact source card it cites. Separate repeated reporting from distinct facts without treating repetition as independent corroboration.

**All current code, data preparation, UI and captured model outputs are AI-assisted pre-sprint preparation. Only work done during the December 4–6, 2026 Apart Research / SL5 sprint is eligible to be judged.** This is a development tool and inspectable case, not a completed empirical paper or evidence that one method wins.

## Try the app

Open `site/desk/index.html` directly in a browser. It is self-contained and makes no model calls or remote asset requests. Select an evidence condition and prompting method, compare with the ordinary assessment, then follow a citation. The source illustration has finite replayable motion, a motion switch and support for reduced motion.

## What is included

- A standard-library Python evaluation harness, nine draft source families, four prompting methods and scoring/review utilities.
- Sixteen stored Astra development responses, containing 35 final claims, from one JumbledPath case and one document order. Source cards are constructed paraphrases, not full reports or independent publications.
- Exact captured input and answer files, an explicit public content manifest, blank review forms and the source-tracing UI.

Changing a selection loads a saved answer. The CLI wrapper, unavailable immutable model digest, short explicit source cues, author-known cases and incomplete independent human review limit what can be concluded. No generalization, calibrated confidence or method superiority is established. The wider evaluation is planned, not completed.

## Reproduce and test

Python 3.10+ is required; runtime package installation is unnecessary. Use fresh output paths because builders refuse overwrites.

```sh
python scripts/build_desk.py site/desk/fresh-build.html
python scripts/verify_public_evidence.py
python scripts/check.py
python scripts/check_preview.py
python -m evidence_study validate data/cases-v2.json
python -m evidence_study export data/cases-v2.json work/evaluation
python -m evidence_study fixture work/evaluation work/fixture --mode false_corroboration
```

Pytest is needed for the test command. Browser checks additionally require separately installed Playwright and Edge at the Windows path configured in `scripts/check_desk_browser.py`; no browser or tool is downloaded by this project. `check_preview.py` starts a temporary loopback server and closes it when the checks finish. Fixture outputs are deterministic engineering samples, not model measurements. The optional local-model runner requires a model the user has already installed and is not invoked by the app or build.

See [VERIFICATION.md](VERIFICATION.md) for actual public-copy checks, their limits and screenshots.

## Provenance and publication

Read [PUBLICATION.md](PUBLICATION.md), [MITRE-NOTICE.txt](MITRE-NOTICE.txt) and [the public content manifest](site/publication.json). Private submission data, raw conversations, machine diagnostics, credentials and raw CLI logs are excluded. Original evidence remains unchanged locally; the public JSON view clearly lists its omitted metadata. No project-wide open-source license has been selected.

[RESEARCH-STATUS.md](RESEARCH-STATUS.md) records the two outstanding wording questions and distinguishes the implemented four-condition harness from the unimplemented prospective six-condition protocol.

## Competition status and submission destination

[Official sprint and embedded submission form](https://apartresearch.com/sprints/threat-intelligence-threat-modelling-2026).

The official page allows AI-assisted work with team responsibility and requires disclosure of preexisting code. Judging covers only the sprint weekend. The page includes a submission form in its markup and also a closed-window message; form presence does not establish current backend acceptance before December. No registration or submission has been made.

Still needed: independent semantic review, genuine event-weekend research, confirmed eligibility/any guardian or prize requirements, author affiliation, final report and official-template formatting. Eligibility and guardian approval are not asserted. The report must be a PDF using the current official template, with authors/affiliations and the required limitations and dual-use discussion.
