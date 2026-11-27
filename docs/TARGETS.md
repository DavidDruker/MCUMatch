# Writing a target spec

A target is one TOML file in `src/mcu_ruleout/targets/`. It describes one exact part, or one
board, and cites the manufacturer's document for every hardware number. You can also keep a spec
anywhere and pass its path to `--target`.

Check a spec by showing it:

```powershell
.\.venv\Scripts\mcu-ruleout.exe targets path\to\my-part.toml
```

## Rules

1. **Manufacturer's documents only.** The datasheet, product specification or reference manual
   from the manufacturer's own site. No distributor pages, mirrors, wikis or forum posts.
2. **Cite the place.** Each number needs `source` (a key in `[sources.*]`) and `where`: section,
   table or figure, and the page number printed on the page. Say so if only a PDF index or an HTML
   chapter is available.
3. **Never fill a gap from memory.** If the document does not state something, leave it out and
   say so in `notes`. A region's `base` address may be left out; its `size` may not.
4. **Take the most generous figure.** A rule-out must hold in the best case, so:
   - `max_clock_hz` is the highest rating the document gives, even if it needs a special mode,
     voltage or temperature range. Put the condition in `note`.
   - Flash and RAM list every region that can hold code or data in some configuration. Mark the
     conditional ones with `condition`. Do not subtract bootloaders, radio stacks or reserved areas.
   - An alias of the same physical memory is counted once.
5. **One spec, one part.** A variant with different memory, or a board with a different flash
   chip, is a different spec.
6. **Say how it was read.** `provenance` records who or what extracted the numbers and how they
   were checked.
7. **Record the check.** `[checked]` says who last compared every number with the cited pages:
   `by = "person"` or `by = "agent"`, the `date`, and the `method`. A spec without the record, or
   with `by = "agent"`, is marked `^` in every report as "not checked by a person". Write
   `by = "person"` only after you have opened every cited page in the rendered document (not text
   extracted from it) and confirmed the number, its unit, the section and the printed page.

## Fields

| Field | Required | Content |
|---|---|---|
| `schema` | yes | `1` |
| `id` | yes | The file name without `.toml` |
| `name` | yes | Maker, part number, and the memory sizes |
| `core` | yes | `cortex-m0plus` or `cortex-m4f` |
| `gcc_flags` | yes | A tool choice, not a datasheet fact. Use exactly the flags of an existing spec with the same core, or the shortlist will build that core twice |
| `provenance` | no | How the numbers were read and checked |
| `[checked]` | no, but a built-in spec needs it | `by` (`"person"` or `"agent"`), `date` (`2026-11-27`), `method` (for example "rendered PDF pages, every cited page opened"), and optional `notes`. No other keys |
| `notes` | no | Conditions, variants, anything that would mislead if left unsaid |
| `[sources.KEY]` | yes | `title`, `revision`, `url`, `accessed`; `publisher` is welcome |
| `[fpu]` | yes | `value`, `source`, `where`; `note` if it is inferred |
| `[max_clock_hz]` | yes | `value` in Hz, `source`, `where`, and a `note` for any condition |
| `[[flash]]`, `[[ram]]` | one or more each | `name`, `size` in bytes, `source`, `where`; `base` and `condition` where known |
| `[library_note]` | no | `value`, `source`, `where`: a faster or smaller runtime library the manufacturer documents for this part. It is printed with any rule-out that depends on library code |

The flags in use today:

| Core | `gcc_flags` |
|---|---|
| `cortex-m0plus` | `["-mcpu=cortex-m0plus", "-mthumb", "-mfloat-abi=soft"]` |
| `cortex-m4f` | `["-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard"]` |

A check record looks like this:

```toml
[checked]
by = "person"
date = 2026-12-03
method = "Rendered PDF pages; every cited page opened and each number, unit and page confirmed."
notes = "Table 10 lists the clock in two rows; the higher one is the normal run mode."
```

The test suite has a release gate that fails while any built-in spec is not checked by a person.
It is marked as an expected failure until the whole catalogue has been checked.

## Example

`src/mcu_ruleout/targets/atsamd21g18a.toml` is a short, complete one.
`src/mcu_ruleout/targets/rp2040-pico.toml` shows conditional RAM regions and a `[library_note]`.
`src/mcu_ruleout/targets/mkl26z64vft4.toml` shows regions without a base address.

## Parts that are wanted

- **STM32** (for example STM32G031K8, STM32G0B1RE, STM32F407VG, STM32F411CE, STM32G431KB,
  STM32L476RG). ST's site did not answer automated requests on 2026-11-24 or 2026-11-26. The
  datasheets open in a normal browser, so these need a person to download and read them.
- **NXP Kinetis memory maps.** The KL26 and K64 reference manuals need an NXP login. With them,
  the two Kinetis specs can get their base addresses and the SRAM_L / SRAM_U split.
- **Nordic page numbers.** The nRF52832 and nRF52833 specs cite the HTML edition. The PDFs would
  give page numbers.
