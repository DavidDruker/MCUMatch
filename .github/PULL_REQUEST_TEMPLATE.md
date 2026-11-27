## What this changes

<!-- One or two sentences. Link the issue or the roadmap task if there is one. -->

## How it was checked

<!-- The tests you added or ran. If something could not be tested (no board, no document), say so. -->

## Checklist

- [ ] Tests are added or updated, and `python -m unittest discover -s tests -t .` passes.
- [ ] Every new number cites a manufacturer's document by section and printed page.
- [ ] No output says code fits, meets a deadline, has headroom, or recommends a part.
- [ ] Docs I touched are updated, and `CHANGELOG.md` has an entry.
- [ ] If the JSON output, a verdict string, an exit code or an option changed: `docs/JSON.md` is
      updated and the change is listed as breaking.
- [ ] If this adds or changes a target spec: its `[checked]` record says truthfully who checked it
      and how, and `docs/CATALOGUE_CHECK.md` has its table.
- [ ] Anything unverified is marked as unverified, in the code and in the docs.
- [ ] Every commit is signed off (`git commit -s`), under the Developer Certificate of Origin.
