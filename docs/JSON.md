# JSON output

`shortlist`, `memory`, `timing` and `compare` print JSON with `--json`. Scripts, continuous
integration jobs and coding agents can rely on what is described here.

## Rules

- **`schema_version`** is `1`. It changes only when a field is removed, renamed, or changes
  meaning. A new field does not change it, so ignore fields you do not know.
- **`kind`** says which command produced the object: `shortlist`, `memory`, `timing` or `compare`.
- **Verdict strings are part of the interface.** A change to their wording is a breaking change
  and is listed in the changelog. Test `ruled_out` rather than parsing a string when you can.
- **Exit codes** match the JSON: 0 not ruled out, 3 ruled out, 1 error, 2 bad arguments. For a
  shortlist, 0 means at least one target is left and 3 means every target is ruled out. For
  `compare`, 0 is `OK`, 4 is `VIOLATION` and 5 is `WITHIN OVERHEAD`.
- **On an error nothing is printed to standard output.** The message goes to standard error and
  the exit code is 1.
- **Shares are fractions, not percentages**: a `load_limit` of `0.7` is 70 %.
- **`null` means "not known" or "does not apply"**, never zero.
- **Every "at least" figure is a lower bound**, not a prediction.
- Progress lines and the note about a `--share` file go to standard error, so standard output is
  always one JSON document.

## Shared objects

### `target`

| Field | Type | Meaning |
|---|---|---|
| `id` | string | The spec's id |
| `name` | string | Maker, part number and memory sizes |
| `core` | string | `cortex-m0plus` or `cortex-m4f` |
| `spec` | string | Path of the spec file that was used |
| `flash_capacity_bytes`, `ram_capacity_bytes` | integer | The sum of every region in the spec, including regions usable only in some configurations |
| `max_clock_hz` | integer | The highest clock the manufacturer rates the part for |
| `checked_by_person` | boolean | Whether a person has compared the spec's numbers with the cited document pages |
| `checked` | object or null | The spec's check record: `by` (`person` or `agent`), `date`, `method`, `notes`. `null` if the spec has none |

### `versions`

Strings keyed by component: `mcu-ruleout`, `toolchain` (the first line of `arm-none-eabi-gcc
--version`), `pyelftools`, `capstone`, and `unicorn` with the CPU model in brackets when the
timing check ran.

### `assumptions` and `not_modeled`

Lists of sentences: what the result assumes, and what it leaves out. In a shortlist each is an
object with a `memory` list and a `timing` list. Show them to whoever reads the verdict.

## `memory`

| Field | Type | Meaning |
|---|---|---|
| `verdict` | string | `RULED OUT (memory)`, `RULED OUT (memory, above your N % flash use limit)` and its RAM and combined forms, or `NOT RULED OUT: measure on hardware` |
| `ruled_out` | boolean | |
| `reasons` | list of strings | One per resource that rules the part out; empty if none |
| `over_capacity` | boolean | The smallest build exceeds a whole capacity, whatever limit was set |
| `holds_without_library` | boolean or null | For a rule-out: would it stand if library code counted as nothing? `null` if not ruled out, or for a prebuilt ELF |
| `cautions` | list of strings | Present when a rule-out depends on library code |
| `notes` | list of strings | Hints that do not change the verdict, such as "no static data was found" |
| `flash_use_limit`, `ram_use_limit` | number | The limits set with `--max-flash-use` and `--max-ram-use`, as fractions. `1.0` by default |
| `flash_use_at_least`, `ram_use_at_least` | number | The lower bound divided by the capacity |
| `lower_bounds` | object | `flash_bytes`, `ram_bytes`: the minimum over the builds. `flash_from`, `ram_from`: the label of the build each came from. `your_code_flash_bytes`, `your_code_ram_bytes`: the same bounds counting only your own object files, or `null` |
| `measurements` | list | One object per build, below |
| `target`, `versions`, `assumptions`, `not_modeled` | | As above |
| `inputs` | object | `sources`, `entries`, `user_flags`, `target_flags`, `defines`, `description`; for a prebuilt ELF `elf`, `entry`, `description` |

Each entry of `measurements`:

| Field | Type | Meaning |
|---|---|---|
| `label` | string | `user: <flags>`, `envelope: <flags>`, or `as built: <file>` |
| `ok` | boolean | `false` if the build failed; then only `error` is present |
| `error` | string | The last lines of the compiler's output |
| `flash_bytes` | integer | Allocated sections with contents |
| `ram_static_bytes` | integer | `.data` plus `.bss` |
| `stack_frame_lb_bytes` | integer or null | Stack the entry function is certain to use |
| `ram_bytes` | integer | `ram_static_bytes` plus `stack_frame_lb_bytes` |
| `berkeley` | object | `text`, `data`, `bss`, as `arm-none-eabi-size -B` reports them |
| `your_code_flash_bytes`, `your_code_ram_bytes` | integer or null | The parts that came from your own object files |
| `flash_by_origin` | object | Flash bytes per origin: `your code`, or a library archive name |
| `stack_frame_lb_detail` | object | `steps` and `stopped_at`: how the stack figure was found |
| `worst_case_stack_info` | object | `known_bytes`, `complete`, `unknowns`, `path`. An upper bound from GCC's call graph, for information only; never used for a verdict |

## `timing`

| Field | Type | Meaning |
|---|---|---|
| `verdict` | string | `RULED OUT (timing, best case)`, `RULED OUT (timing, best case above your N % load limit)`, or `NOT RULED OUT: measure on hardware` |
| `ruled_out` | boolean | |
| `over_deadline` | boolean | The best case misses the whole deadline, whatever load limit was set |
| `holds_without_library` | boolean or null | For a rule-out: would it stand if library routines took no time? |
| `cautions` | list of strings | Present when a rule-out depends on library code |
| `cycles_lower_bound` | integer | The minimum over the builds that could be traced |
| `lower_bound_from` | string | The label of that build |
| `your_code_cycles_lower_bound` | integer or null | The same, counting only cycles in your own code |
| `clock_hz` | integer | The target's maximum rated clock |
| `clock_where` | string | Where in the manufacturer's document that clock is stated |
| `time_lower_bound_s` | number | `cycles_lower_bound / clock_hz` |
| `your_code_time_lower_bound_s` | number or null | |
| `deadline_s` | number or null | The deadline given |
| `load_limit` | number | The limit set with `--max-load`, as a fraction. `1.0` by default |
| `allowed_time_s` | number or null | `deadline_s * load_limit` |
| `best_case_load` | number or null | `time_lower_bound_s / deadline_s`. A lower bound on the load |
| `required_clock_hz` | number or null | The clock below which this core is ruled out at this deadline and load limit, whatever the part |
| `instructions` | integer | Instructions executed inside the measured function, in the fastest build |
| `entry_return_value` | integer or null | What the entry function returned, as a C `int`. A harness built with `-D SELFTEST` returns 0 when the kernel's answer is right |
| `cycle_table` | string | The cycle table's version and the Arm manual it was transcribed from |
| `builds` | list | One object per build: `label`, `ok`, and `cycles`, `instructions`, `your_code_cycles`, or `error` if it could not be traced |
| `by_class` | object | Per instruction class: `instructions` and `cycles` |
| `by_function` | object | Executed instructions per function |
| `cycles_by_function` | object | Cycles per function |
| `cycles_by_origin` | object or null | Cycles per origin: `your code`, or a library archive name. `null` for a prebuilt ELF |
| `undocumented_counted_as_zero` | object | Mnemonics with no entry in the cycle table, and how often each ran. They cost 0 |
| `skipped_in_it_blocks` | integer | Instructions skipped inside IT blocks. They cost 0 |
| `inputs` | object | `built`, `entry`, `measure`, `args` |
| `target`, `versions`, `assumptions`, `not_modeled` | | As above |

## `shortlist`

| Field | Type | Meaning |
|---|---|---|
| `deadline_s` | number or null | |
| `limits` | object | `load`, `flash_use`, `ram_use`: the limits in force, as fractions |
| `timing_skipped` | string | Why the timing check did not run; empty if it ran |
| `counts` | object | `targets`, `ruled_out`, `not_ruled_out`, `no_verdict` |
| `not_ruled_out` | list of strings | Target ids. None of these is shown to work |
| `rows` | list | One object per target, below. Targets that are not ruled out come first; the order within a group is by name and says nothing else |
| `floors` | list | One object per group of targets that share a core and compiler flags, below |
| `inputs` | object | `sources`, `entry`, `measure`, `user_flags`, `defines`, `args`, `description` |
| `versions`, `assumptions`, `not_modeled` | | As above |

Each entry of `rows`:

| Field | Type | Meaning |
|---|---|---|
| `target` | object | As above |
| `status` | string | `not ruled out`, `no verdict`, or `RULED OUT (...)` naming the checks, for example `RULED OUT (timing: above 70 % load)` |
| `ruled_out` | boolean | |
| `ruled_out_by` | list of strings | `memory`, `timing`, or both |
| `depends_on_library` | boolean | Ruled out, but no check that rules it out would stand with library code counted as nothing |
| `cautions` | list of strings | |
| `errors` | list of strings | Why a check gave no verdict. A target with no verdict is not ruled out |
| `memory` | object or null | The verdict fields of the memory check: everything in the `memory` table above down to `lower_bounds` |
| `timing` | object or null | The verdict fields of the timing check: everything in the `timing` table above down to `your_code_time_lower_bound_s`, without `clock_where` |

Each entry of `floors`:

| Field | Type | Meaning |
|---|---|---|
| `core`, `gcc_flags`, `targets` | | The group, and the ids of the targets in it |
| `flash_bytes`, `ram_bytes` | integer or null | The least any part with this core needs |
| `cycles` | integer or null | The cycle lower bound for this core |
| `required_clock_hz` | number or null | `cycles / (deadline_s * limits.load)`. Any part with this core and a lower rated clock is ruled out, whether or not it is in the catalogue |
| `memory_builds` | list | `label`, `ok`, and `flash_bytes`, `ram_bytes`, or `error` |
| `timing_builds` | list | As `builds` in the timing output |
| `errors` | list of strings | |

## `compare`

Printed by `mcu-ruleout compare --json` (see [MEASURE.md](MEASURE.md)).

| Field | Type | Meaning |
|---|---|---|
| `measurement`, `entry` | string | The measurement's id and the timed function |
| `outcome` | string | `OK`, `WITHIN OVERHEAD` or `VIOLATION` |
| `bound_cycles`, `bound_empty_cycles` | integer | The tool's bound for the timed function and for the kit's empty function, from the same ELF |
| `measured_raw_cycles`, `overhead_cycles` | integer | The minimum measured counter differences |
| `measured_corrected_cycles` | integer | `raw - overhead + bound_empty` |
| `ratio_raw`, `ratio_corrected` | number | Measured divided by the bound |
| `cycle_table` | string | |
| `core_clock_hz` | integer | The clock the measurement was made at |
| `hardware` | boolean | `false` for the emulated port, whose numbers are made up |

## `targets --json`

A list of `target` objects, one per built-in spec. It has no `schema_version` of its own.

## Other files the tool writes

| File | Schema field | Described in |
|---|---|---|
| `--share FILE` | `"schema": "mcu-ruleout-share/1"` | The top of `src/mcu_ruleout/share.py`. Built from an allow-list: verdicts, bounds, floors, limits, versions and the compiler flags that cannot carry a name |
| Measurement file from `measurement import` | `"schema": "mcu-ruleout-measurement/1"` | [MEASURE.md](MEASURE.md) |
| `--report FILE` | Markdown, for people | |

## Example

```powershell
mcu-ruleout shortlist --example fir_q15 --deadline 100us --max-load 70 --json | python -c "import json,sys; d=json.load(sys.stdin); print(d['counts'], d['not_ruled_out'])"
```
