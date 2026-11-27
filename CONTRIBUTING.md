# Contributing

Thank you for considering it. This project makes one narrow kind of statement, "this code cannot
work on this part, even in the best case", and tries hard never to say more than it can show. The
most useful contributions help with exactly that:

- **a target spec** for a part you have the datasheet for, checked by you against the rendered pages;
- **a hardware measurement** taken with the measurement kit;
- **a report that the tool was wrong**: a bound above a real measurement, a wrong capacity, a
  message that misled you;
- **a rule-out story**: a case where the tool removed a part you were seriously considering, or
  failed to.

## Set up

You need Python 3.11 or newer and the Arm GNU Toolchain (see [docs/INSTALL.md](docs/INSTALL.md)).

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[emu]"
```

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```

On Linux or macOS use `.venv/bin/python`. The suite takes a few minutes. Tests that need the
toolchain or the emulator skip themselves when one is missing, so check the summary line for
skips you did not expect. CI fails if those tests would be skipped.

## Rules for every change

- **Tests with every change.** A new feature comes with tests. A bug fix comes with a test that
  fails without the fix.
- **Every number has a source.** A capacity, a clock or a cycle count comes from a manufacturer's
  document, cited by section and printed page, or from the binary itself.
- **The verdicts stay as they are.** `RULED OUT` or `NOT RULED OUT: measure on hardware`. The
  tests that search every output for claims of a fit, a pass, headroom or a recommendation must
  keep passing, and new outputs must be added to them.
- **Say what was not done.** If something is untested, unverified or read by a script and not by
  a person, the code, the docs and the commit message say so.
- **Update the docs you touch**, the changelog ([CHANGELOG.md](CHANGELOG.md)), and, if you change
  the JSON output, [docs/JSON.md](docs/JSON.md). A change to verdict wording, a JSON field, an
  exit code or an option is a breaking change; say so in the pull request.
- Keep the style of the code around you: type hints, short docstrings that say why, lines up to
  120 characters, and no new dependency without a discussion first.

## Adding a target

Read [docs/TARGETS.md](docs/TARGETS.md) first. In short:

1. Download the manufacturer's datasheet or reference manual yourself, from the manufacturer's
   own site.
2. Write the spec by hand. Cite the section and the printed page for every number. Take the most
   generous figure the document gives, and put any condition in a note.
3. Open every cited page in the rendered document and confirm the number, its unit and the page.
4. Set `[checked]` to `by = "person"` with the date and how you checked. Only do this if you
   really did step 3: the whole value of the record is that it is true.
5. Add a section for the part to [docs/CATALOGUE_CHECK.md](docs/CATALOGUE_CHECK.md):
   `python scripts/catalogue_checklist.py <id>` prints the table to fill in.
6. Run the tests.

A spec read by a script or a language model is welcome as a starting point, marked
`by = "agent"`. It will be shown with the `^` mark until a person has checked it.

Cores other than the Cortex-M0+ and the Cortex-M4F are out of scope for now, because the method
needs Arm's per-instruction cycle tables and has them for these two only.

## Submitting a measurement

Read [docs/MEASURE.md](docs/MEASURE.md) first. A measurement is accepted only with:

- the measurement file written by `mcu-ruleout measurement import`, which holds every raw run and
  the register readout;
- the exact ELF that was flashed;
- the board port's source, if the port is not in the repository yet.

It is verified here by running `mcu-ruleout compare` on your ELF. A measurement that shows the
bound to be wrong is the most valuable kind. It will never be dropped or edited.

Do not submit a measurement taken with a port that writes option bytes, security bits or fuses.

## Sign your work

Contributions are accepted under the project's licence (MIT for code, CC-BY-4.0 for dataset rows),
with a sign-off under the [Developer Certificate of Origin](https://developercertificate.org/).
Add a line to each commit message:

```text
Signed-off-by: Your Name <your.email@example.com>
```

`git commit -s` adds it for you. By signing off you state that you wrote the change or otherwise
have the right to submit it under that licence. There is no contributor licence agreement.

## What will not be accepted

- **Ranking or recommending parts**, or any output that says code fits, meets a deadline or has
  headroom. The tool only rules out.
- **A fitted or learned model** of execution time. No machine learning, no regression on
  measurements, no correction factors tuned to make the bound tighter.
- **A number without a citation**, or one taken from a distributor's page, a wiki, a forum or
  memory.
- **Upper bounds presented as verdicts**, worst-case execution time, or anything aimed at
  safety certification.
- **Third-party code without a licence that allows it** copied into the repository. Validation
  recipes fetch such code by commit at run time instead.
- **A hosted service**, accounts, or anything that runs other people's code on someone's server.
- **A change to a pre-registration, a completeness rule or a dataset row** made after results
  were seen, unless it is logged as a deviation.

## Reporting a bug

Open an issue with the command you ran, what it printed, and what you expected. `mcu-ruleout
doctor` output helps. If you cannot share your code, a result written with `--share` holds the
verdicts and versions without any source text or file names.

For a security problem, see [SECURITY.md](SECURITY.md) and do not open a public issue.

## How this project is maintained

One person maintains it, in spare time, so an answer can take a while. Target specs and
measurements are reviewed first, because other people's results depend on them. Requests that fall
under "What will not be accepted" are closed with a pointer to this file.
