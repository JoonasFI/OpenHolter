# Contributing to OpenHolter

🇫🇮 [Suomeksi](CONTRIBUTING.fi.md)

Thank you for wanting to help! Bug reports, suggestions and code are all welcome.

## Practices

- Open an issue first for larger changes, so we agree on the direction before you put in a lot of work.
- Run the tests before a pull request: `python -m pytest tests` (or without pytest: `PYTHONPATH=. python tests/test_pipeline.py`).
- The code must work on Python 3.9 (the macOS Command Line Tools Python).
- No cloud services, external analytics or telemetry: the data stays on the user's computer.
- Changes that affect the analysis: also run the validation on both datasets
  (`python -m openholter validate --mitdb <folder> --incartdb <folder>`, see `docs/VALIDATION.en.md`)
  and include the results in the pull request, also if they get worse. Tune parameters only on the DS1 half of MIT-BIH.
  DS2 and INCART are test data, and their results are reported without retuning.
- User-visible text: the Finnish string is the key; add the English translation to `openholter/static/i18n-en.js`
  (and `tr(fi, en)` / `T(fi, en)` on the server and in the PDF).

## Contributor License Agreement (CLA)

OpenHolter is released under the AGPL-3.0, and a commercial licence is also available (see the README).
To make this dual licensing possible, every contributor accepts a CLA before code is merged.
You accept it in the pull request (the CLA Assistant bot asks for it automatically).

The CLA does not transfer your copyright: you still own your code and can use it as you wish.

**Which CLA.** OpenHolter uses the ready-made, widely used
[Harmony Individual Contributor License Agreement, version 1.0](https://harmonyagreements.org/docs/ha-combined-v1)
(the *licence* version, not the copyright assignment version) with these choices:

| Template blank | OpenHolter |
|---|---|
| Version | Individual, copyright **licence** (you keep your copyright) |
| Project, "We/Us" | OpenHolter; Joonas Wilska (sole trader, Finland) |
| Outbound licence, section 2.3 | **Option Five**: any licence, including commercial, provided the contribution is also offered under the project's licence (AGPL-3.0-or-later) |
| Media licences | CC BY 4.0 |
| Governing law, section 6.1 | Finland |
| Submission | electronic acceptance through CLA Assistant on GitHub |
| If you do not own all of the copyright | tell us in the pull request; your employer or the owner signs the Harmony **Entity** CLA |

Section 6.3 of the template allows the rights and obligations to be transferred to a third party that agrees in
writing to abide by the agreement. This is how the agreement can move to a company if the project is later run
by one; your rights under the agreement stay the same.

*The filled-in agreement text (CLA.md) and the CLA Assistant set-up will be added before the first outside
contribution is merged. The Harmony templates are licensed under CC BY 3.0.*
