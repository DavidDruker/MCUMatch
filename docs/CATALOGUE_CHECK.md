# Catalogue check log

Roadmap tasks 1.2, 1.3 and 1.7. Every capacity and clock number in a built-in target spec has to be
compared, by a person, with the page of the manufacturer's document it cites. This file is the
record of that check: one table row per number.

**State on 2026-11-27: nothing below has been checked by a person.** The tables were generated
from the specs by `scripts/catalogue_checklist.py`, and the last three columns are empty on
purpose. No automated agent may fill them in; the point of this check is that a person does it.

## How to check one spec

1. Download each document listed for the spec in a browser and open the PDF itself, not text
   extracted from it. Confirm the revision matches the one listed. If the manufacturer has
   published a newer revision, check against the newer one and update `revision` and `accessed`
   in the spec.
2. For each row: go to the cited section and printed page, read the number and its unit from the
   rendered page, and write what the page says in "Rendered page says". Put `yes` in "OK?" when
   the number, the unit, the section and the printed page all match.
3. When something does not match, write what is wrong and what you changed in the last column,
   fix the spec, and add an entry to the changelog naming the verdicts that change (a wrong
   capacity or clock can change verdicts in either direction).
4. Tick the four items under the table.
5. Set the spec's check record, with your own date and method:

   ```toml
   [checked]
   by = "person"
   date = 2026-12-03
   method = "Rendered PDF pages; every cited page opened and each number, unit and page confirmed."
   ```

   Update `provenance` to match, and the README status block ("Targets checked by a person").
6. When every built-in spec is checked, the release-gate test in `tests/test_targets.py` reports
   an unexpected success. Remove its `expectedFailure` decorator so it guards every later spec.

Start with the parts in the README example whose verdicts are closest to the deadline; they come
first below.

## Pack cross-check (task 1.7)

**Run on 2026-11-27 in CI, on commit `92f28f2`**
([run 46053768532](https://github.com/DavidDruker/MCUMatch/actions/runs/46053768532)).
`scripts/check_against_packs.py` compared each spec's flash, RAM and maximum clock with the
vendor's CMSIS device family pack. **23 of 33 comparisons agree. 10 differ, and in 5 of those the
pack gives more than the spec.** One of the ten is an open question (the K64's FlexRAM, row 1
below). No difference has been confirmed by a person, so none is recorded as `explained` in
`scripts/pack_devices.toml`.

A pack is a cross-check and never a source, so a difference means "re-read the datasheet page",
not "copy the pack". No number in a spec was changed because of this run. Agreement is not a
person-check either: it shows that the spec and the pack say the same thing, and both can be wrong
in the same way.

### How it runs

- `scripts/packs.toml` pins nine packs by version and SHA-256. `python scripts/fetch_packs.py`
  downloads them into `packs/` (ignored by Git, about 160 MB) and checks each hash. Nothing from
  a pack is committed.
- `python scripts/check_against_packs.py --markdown` prints the table below. `--regions` lists
  every memory region of each matched device and says whether it was counted, and why not.
- The `pack cross-check` workflow (`.github/workflows/packs.yml`) does both whenever a spec, the
  pack list or the script changes, and leaves the output on the run's summary page. It fails when
  a pack cannot be fetched or does not match its hash. It does not fail on a difference.
- NXP's own KL26 pack (NXP.MKL26Z4_DFP 10.0.3) lists only the 128 kB and 256 kB parts. The 64 kB
  part is compared with Keil's older pack for the whole KL family, which the pack index marks as
  deprecated since 2023-09-03.

### What a pack total counts

A pack lists more than program flash and RAM: peripheral address windows, the same memory at a
second address, windows for external flash, configuration rows. The first run added all of them
up and reported, for example, 538 MB of RAM for the SAM D21. The script now counts a region only
when all of these hold:

1. Its access string makes it RAM (readable and writable) or program flash (readable and
   executable, not writable), and the pack does not mark it as a peripheral or as an alias of
   another region.
2. The pack gives it to the linker by default (`default="1"`). When the pack marks no such region
   of that kind, every region that rule 1 keeps is counted.
3. Each address is counted once, however many regions cover it.

These rules use only what the pack format says about a region. They know nothing about the chip.
Nordic's packs, for example, list the region at 0x00800000 as an ordinary default RAM region, so
it is counted and appears as a difference below.

### Result

| spec | quantity | spec says | pack says | result | detail |
|---|---|---|---|---|---|
| apollo3-blue | flash | 1,048,576 B | 999,424 B | DIFFERENT | AMA3B1KK-KBR in AmbiqMicro.Apollo_DFP.1.6.0.pack: the pack gives less than the spec; re-read the datasheet. Counted: IROM1 999,424 B at 0x0000c000 |
| apollo3-blue | ram | 393,216 B | 393,216 B | same | AMA3B1KK-KBR in AmbiqMicro.Apollo_DFP.1.6.0.pack. Counted: IRAM1 393,216 B at 0x10000000 |
| apollo3-blue | clock | 96 MHz | 48 MHz | DIFFERENT | AMA3B1KK-KBR in AmbiqMicro.Apollo_DFP.1.6.0.pack: the pack gives less than the spec; re-read the datasheet |
| atsamd21g18a | flash | 262,144 B | 262,144 B | same | ATSAMD21G18A in Microchip.SAMD21_DFP.3.9.287.pack. Counted: FLASH 262,144 B at 0x00000000 |
| atsamd21g18a | ram | 32,768 B | 32,768 B | same | ATSAMD21G18A in Microchip.SAMD21_DFP.3.9.287.pack. Counted: HMCRAMC0 32,768 B at 0x20000000. Not counted: HPB0 65,536 B at 0x40000000 (marked as a peripheral), HPB1 65,536 B at 0x41000000 (marked as a peripheral), HPB2 65,536 B at 0x42000000 (marked as a peripheral), PPB 1,048,576 B at 0xe0000000 (marked as a peripheral), SCS 4,096 B at 0xe000e000 (marked as a peripheral), PERIPHERALS 536,870,912 B at 0x40000000 (marked as a peripheral), USER_ROW 256 B at 0x00804000 (not readable) |
| atsamd21g18a | clock | 48 MHz | 48 MHz | same | ATSAMD21G18A in Microchip.SAMD21_DFP.3.9.287.pack |
| atsamd51j19a | flash | 524,288 B | 524,288 B | same | ATSAMD51J19A in Microchip.SAMD51_DFP.3.10.283.pack. Counted: FLASH 524,288 B at 0x00000000 |
| atsamd51j19a | ram | 208,896 B | 196,608 B | DIFFERENT | ATSAMD51J19A in Microchip.SAMD51_DFP.3.10.283.pack: the pack gives less than the spec; re-read the datasheet. Counted: HSRAM 196,608 B at 0x20000000. Not counted: BKUPRAM 8,192 B at 0x47000000 (not given to the linker by default), CMCC 16,777,216 B at 0x03000000 (marked as a peripheral), CMCC_DATARAM 4,096 B at 0x03000000 (marked as a peripheral), CMCC_TAGRAM 1,024 B at 0x03001000 (marked as a peripheral), CMCC_VALIDRAM 64 B at 0x03002000 (marked as a peripheral), HPB0 17,408 B at 0x40000000 (marked as a peripheral), HPB1 139,264 B at 0x41000000 (marked as a peripheral), HPB2 15,360 B at 0x42000000 (marked as a peripheral), HPB3 12,288 B at 0x43000000 (marked as a peripheral), SEEPROM 131,072 B at 0x44000000 (marked as a peripheral), SDHC0 3,072 B at 0x45000000 (marked as a peripheral), PPB 1,048,576 B at 0xe0000000 (marked as a peripheral), SCS 4,096 B at 0xe000e000 (marked as a peripheral) |
| atsamd51j19a | clock | 120 MHz | 120 MHz | same | ATSAMD51J19A in Microchip.SAMD51_DFP.3.10.283.pack |
| mk64fn1m0vll12 | flash | 1,048,576 B | 1,048,576 B | same | MK64FN1M0VLL12 in NXP.MK64F12_DFP.14.0.0.pack. Counted: PROGRAM_FLASH 1,048,576 B at 0x00000000 |
| mk64fn1m0vll12 | ram | 262,144 B | 266,240 B | DIFFERENT | MK64FN1M0VLL12 in NXP.MK64F12_DFP.14.0.0.pack: the pack gives more than the spec; re-read the datasheet. Counted: FLEX_RAM 4,096 B at 0x14000000, SRAM_LOWER 65,536 B at 0x1fff0000, SRAM_UPPER 196,608 B at 0x20000000 |
| mk64fn1m0vll12 | clock | 120 MHz | 120 MHz | same | MK64FN1M0VLL12 in NXP.MK64F12_DFP.14.0.0.pack |
| mkl26z64vft4 | flash | 65,536 B | 65,536 B | same | MKL26Z64xxx4 in Keil.Kinetis_KLxx_DFP.1.15.1.pack. Counted: IROM1 65,536 B at 0x00000000 |
| mkl26z64vft4 | ram | 8,192 B | 8,192 B | same | MKL26Z64xxx4 in Keil.Kinetis_KLxx_DFP.1.15.1.pack. Counted: IRAM1 8,192 B at 0x1ffff800 |
| mkl26z64vft4 | clock | 48 MHz | 48 MHz | same | MKL26Z64xxx4 in Keil.Kinetis_KLxx_DFP.1.15.1.pack |
| mspm0g3507 | flash | 131,072 B | 131,072 B | same | MSPM0G3507 in TexasInstruments.MSPM0G1X0X_G3X0X_DFP.1.3.1.pack. Counted: IROM1 131,072 B at 0x00000000. Not counted: IROM2 131,072 B at 0x00400000 (an alias of IROM1), NonMain_ECC 512 B at 0x41c00000 (not executable), NonMain_noECC 512 B at 0x41c10000 (an alias of NonMain_ECC), Factory_ECC 128 B at 0x41c40000 (not executable), Factory_noECC 128 B at 0x41c50000 (an alias of Factory_ECC) |
| mspm0g3507 | ram | 32,768 B | 32,768 B | same | MSPM0G3507 in TexasInstruments.MSPM0G1X0X_G3X0X_DFP.1.3.1.pack. Counted: IRAM1 32,768 B at 0x20000000. Not counted: IRAM_Parity 32,768 B at 0x20100000 (an alias of IRAM1), IRAM_No_Parity 32,768 B at 0x20200000 (an alias of IRAM1), IRAM_Parity_Code 32,768 B at 0x20300000 (an alias of IRAM1) |
| mspm0g3507 | clock | 80 MHz | 80 MHz | same | MSPM0G3507 in TexasInstruments.MSPM0G1X0X_G3X0X_DFP.1.3.1.pack |
| nrf52832 | flash | 524,288 B | 524,288 B | same | nRF52832_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack. Counted: IROM1 524,288 B at 0x00000000 |
| nrf52832 | ram | 65,536 B | 131,072 B | DIFFERENT | nRF52832_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack: the pack gives more than the spec; re-read the datasheet. Counted: IRAM1 65,536 B at 0x20000000, IRAM2 65,536 B at 0x00800000 |
| nrf52832 | clock | 64 MHz | 64 MHz | same | nRF52832_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack |
| nrf52833 | flash | 524,288 B | 524,288 B | same | nRF52833_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack. Counted: IROM1 524,288 B at 0x00000000 |
| nrf52833 | ram | 131,072 B | 262,144 B | DIFFERENT | nRF52833_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack: the pack gives more than the spec; re-read the datasheet. Counted: IRAM1 131,072 B at 0x20000000, IRAM2 131,072 B at 0x00800000 |
| nrf52833 | clock | 64 MHz | 64 MHz | same | nRF52833_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack |
| nrf52840 | flash | 1,048,576 B | 135,266,304 B | DIFFERENT | nRF52840_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack: the pack gives more than the spec; re-read the datasheet. Counted: IROM1 1,048,576 B at 0x00000000, IROM2 134,217,728 B at 0x12000000 |
| nrf52840 | ram | 262,144 B | 524,288 B | DIFFERENT | nRF52840_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack: the pack gives more than the spec; re-read the datasheet. Counted: IRAM1 262,144 B at 0x20000000, IRAM2 262,144 B at 0x00800000 |
| nrf52840 | clock | 64 MHz | 64 MHz | same | nRF52840_xxAA in NordicSemiconductor.nRF_DeviceFamilyPack.8.44.1.pack |
| rp2040-pico | flash | 2,097,152 B | 2,097,152 B | same | RP2040 in RaspberryPi.RP2xxx_DFP.0.9.5.pack. Counted: External_Flash 2,097,152 B at 0x10000000 |
| rp2040-pico | ram | 290,816 B | 270,336 B | DIFFERENT | RP2040 in RaspberryPi.RP2xxx_DFP.0.9.5.pack: the pack gives less than the spec; re-read the datasheet. Counted: SRAM 270,336 B at 0x20000000 |
| rp2040-pico | clock | 200 MHz | 133 MHz | DIFFERENT | RP2040 in RaspberryPi.RP2xxx_DFP.0.9.5.pack: the pack gives less than the spec; re-read the datasheet |
| tm4c123gh6pm | flash | 262,144 B | 262,144 B | same | TM4C123GH6PM in Keil.TM4C_DFP.1.1.0.pack. Counted: IROM1 262,144 B at 0x00000000 |
| tm4c123gh6pm | ram | 32,768 B | 32,768 B | same | TM4C123GH6PM in Keil.TM4C_DFP.1.1.0.pack. Counted: IRAM1 32,768 B at 0x20000000 |
| tm4c123gh6pm | clock | 80 MHz | 80 MHz | same | TM4C123GH6PM in Keil.TM4C_DFP.1.1.0.pack |

### The ten differences

None of these has been checked by a person. Each row gives what the pack shows, what the spec's
own cited note says about it, and what the person doing the check has to confirm on the rendered
page. When the spec turns out right, record the reason under `explained` in
`scripts/pack_devices.toml`. When it is wrong, fix the spec as in step 3 of the list above.

**The pack gives more than the spec.** Look at these first: a spec that understates a capacity
could rule a part out wrongly.

| # | Spec, quantity | What the pack shows | What the spec says about it | To confirm |
|---|---|---|---|---|
| 1 | `mk64fn1m0vll12` RAM | 4,096 B more. A `FLEX_RAM` region of 4,096 B at 0x14000000, next to `SRAM_LOWER` 65,536 B at 0x1FFF0000 and `SRAM_UPPER` 196,608 B at 0x20000000. The two SRAM regions together are the spec's 262,144 B | Note in the spec: "N in the part number means no FlexNVM or FlexRAM (s7.3 Fields p.80)". **The pack and that note disagree, and no document read so far settles it.** The reference manual (K64P144M120SF5RM) could not be fetched without a login | In the reference manual: whether this part number has the 4 kB FlexRAM, and whether it can hold ordinary data. If it can, the spec understates RAM by 4,096 B (1.6 %) and needs one more region with a condition. Until then, a RAM rule-out on this part by less than 4,096 B is not settled. The pack's split of the SRAM (64 kB below 0x20000000, 192 kB from it) is the split the spec could not cite |
| 2 | `nrf52832` RAM | Twice the spec: `IRAM2` 65,536 B at 0x00800000 as well as `IRAM1` 65,536 B at 0x20000000 | Note: the Code RAM region at 0x00800000 is the same physical RAM as the Data RAM at 0x20000000 and is not counted twice. The note cites only "Memory chapter" | The memory map page of the product specification. Add its section and printed page to the note |
| 3 | `nrf52833` RAM | Twice the spec: `IRAM2` 131,072 B at 0x00800000 as well as `IRAM1` 131,072 B at 0x20000000 | The same note, also citing only "Memory chapter" | As row 2 |
| 4 | `nrf52840` RAM | Twice the spec: `IRAM2` 262,144 B at 0x00800000 as well as `IRAM1` 262,144 B at 0x20000000 | Note: the code-RAM alias at 0x00800000 is the same physical RAM as 0x20000000 (PS s4.2 p.21-22) | That page |
| 5 | `nrf52840` flash | 134,217,728 B more: `IROM2` at 0x12000000, as well as `IROM1` 1,048,576 B at 0 | Note: a board with external QSPI flash can execute from the XIP window at 0x12000000-0x19FFFFFF (PS Figure 3 p.23, s6.19.5 p.580); the spec is chip-level and such a board needs its own spec. That window is 134,217,728 B long, the size of the pack's region | Those pages |

**The pack gives less than the spec.** This is the usual case: a spec takes the most generous
figure the datasheet allows, and a pack describes a default configuration.

| # | Spec, quantity | What the pack shows | What the spec says about it | To confirm |
|---|---|---|---|---|
| 6 | `apollo3-blue` flash | 49,152 B less. `IROM1` starts at 0x0000C000 instead of 0 and ends where the spec's region ends, at 0x00100000 | Flash is 0x00000000 - 0x000FFFFF (s3.3 Table 5 p.78). Note: "Any flash a secure boot loader keeps is not subtracted, so capacity stays an upper bound" | What the first 0xC000 bytes hold, and that they are part of the 1 MB of flash |
| 7 | `apollo3-blue` clock | 48 MHz | 96 MHz is the TurboSPOT burst mode, off by default and with conditions; the nominal clock is 48 MHz (s12.1.6 p.550, Features p.2) | That page and the conditions |
| 8 | `atsamd51j19a` RAM | 12,288 B less. Counted: `HSRAM` 196,608 B. Not counted: `BKUPRAM` 8,192 B at 0x47000000 (not given to the linker by default) and `CMCC_DATARAM` 4,096 B at 0x03000000 (marked as a peripheral) | The spec has the same three regions: embedded SRAM 196,608 B, backup SRAM 8,192 B (s9.2 Table 9-1 p.50) and tightly coupled memory 4,096 B, usable only with the cache disabled or made smaller (s11.6.7 and Table 11-1 p.74-75). 196,608 + 8,192 + 4,096 = 208,896 | Those pages |
| 9 | `rp2040-pico` RAM | 20,480 B less. Counted: `SRAM` 270,336 B at 0x20000000 | The spec adds the XIP cache, 16,384 B, usable only with the cache disabled, and the USB DPRAM, 4,096 B, usable only if USB is not used (s2.6.2.1 p.123). 270,336 + 16,384 + 4,096 = 290,816 | That page |
| 10 | `rp2040-pico` clock | 133 MHz | 200 MHz needs a raised core voltage; the rating at the default core voltage is 133 MHz (s2.15.3.1, note after Table 206, p.179) | That note |

Two rows that agree still deserve a look. The `rp2040-pico` flash agrees because the pack's
`External_Flash` region happens to be 2 MB, the size of the Pico's flash chip; the flash is on the
board, and the pack's figure is a default. And for `mkl26z64vft4` the pack places the 8 kB of SRAM
at 0x1FFFF800, a base address the spec does not have because the reference manual was not read.

## Per-spec tables

### apollo3-blue

Ambiq Apollo3 Blue AMA3B1KK (1 MB flash, 384 kB RAM). Core `cortex-m4f`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: Every cited page was re-read by a second automated pass, as text extracted from the PDF. Tables were not viewed as rendered pages.

Documents:

- `apollo3-ds`: Apollo3 and Apollo3 Blue SoC Datasheet, DS-A3-1p4p0, Revision 1.4.0, 2026, https://contentportal.ambiq.com/documents/20123/388385/Apollo3-Blue-SoC-Datasheet.pdf (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | FPU, precision not stated in the datasheet | `apollo3-ds`: s2 System Core p.72 (32-bit ARM Cortex-M4 processor with Floating Point Unit); Features p.2. |  |  |  |
| 2 | Maximum clock | 96,000,000 Hz | `apollo3-ds`: s12.1.6 TurboSPOT Mode Support p.550 (in TurboSPOT mode the core clock runs at 96 MHz); Features p.2; Table 1202 Recommended Operating Conditions p.816. Note in spec: The most generous documented rating, used because a rule-out needs the best case. It is a burst mode with conditions; the nominal clock is 48 MHz (Features p.2). |  |  |  |
| 3 | Flash: flash memory | 1,048,576 B at 0x00000000 | `apollo3-ds`: s3.3 Table 5 MCU System Memory Map p.78 (0x00000000 - 0x000FFFFF Flash); Table 1564 Ordering Information p.954 (AMA3B1KK: 1 MB). |  |  |  |
| 4 | RAM: SRAM (TCM), low-latency | 65,536 B at 0x10000000 | `apollo3-ds`: s3.3 Table 5 p.78 (0x10000000 - 0x1000FFFF SRAM (TCM)). |  |  |  |
| 5 | RAM: SRAM (Main) | 327,680 B at 0x10010000 | `apollo3-ds`: s3.3 Table 5 p.78 (0x10010000 - 0x1005FFFF SRAM (Main)); Table 1564 p.954 (384 kB in total with the TCM). |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 1,048,576 B and RAM 393,216 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### tm4c123gh6pm

Texas Instruments TM4C123GH6PM (256 kB flash, 32 kB RAM). Core `cortex-m4f`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: Every cited page was re-read by a second automated pass, as text extracted from the PDF. Tables were not viewed as rendered pages.

Documents:

- `tm4c123-ds`: Tiva TM4C123GH6PM Microcontroller Data Sheet, DS-TM4C123GH6PM-15842.2741, SPMS376E, June 12, 2014, https://www.ti.com/lit/ds/symlink/tm4c123gh6pm.pdf (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | single-precision FPU | `tm4c123-ds`: s1.3.1.1 Processor Core p.49 (IEEE754-compliant single-precision Floating-Point Unit); Table 1-1 p.46 (ARM Cortex-M4F processor core). |  |  |  |
| 2 | Maximum clock | 80,000,000 Hz | `tm4c123-ds`: Table 1-1 TM4C123GH6PM Microcontroller Features p.46, Performance row (80-MHz operation); s5.2.6 LDO Sleep/Deep-Sleep Power Control p.230. Note in spec: The only rating given, with the LDO at 1.2 V. |  |  |  |
| 3 | Flash: on-chip flash | 262,144 B at 0x00000000 | `tm4c123-ds`: Table 1-1 p.46 (256 KB single-cycle Flash memory); s2.4 Table 2-4 Memory Map p.92, row On-chip Flash (0x0000.0000 to 0x0003.FFFF). |  |  |  |
| 4 | RAM: bit-banded on-chip SRAM | 32,768 B at 0x20000000 | `tm4c123-ds`: Table 1-1 p.46 (32 KB single-cycle SRAM); s2.4 Table 2-4 p.92 (0x2000.0000 to 0x2000.7FFF). |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 262,144 B and RAM 32,768 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### atsamd51j19a

Microchip ATSAMD51J19A (512 kB flash, 192 kB RAM). Core `cortex-m4f`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: Every cited page was re-read by a second automated pass, as text extracted from the PDF. Tables were not viewed as rendered pages.

Documents:

- `samd51-ds`: SAM D5x/E5x Family Complete Data Sheet, DS60001507N, Revision N, 03/2026, https://ww1.microchip.com/downloads/aemDocuments/documents/MCU32/ProductDocuments/DataSheets/SAM-D5x-E5x-Family-Data-Sheet-DS60001507.pdf (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | single-precision FPU | `samd51-ds`: s10.1.3 Cortex-M4 Processor Features and Configuration p.57 (IEEE 754-compliant single-precision FPU); configuration table p.58. |  |  |  |
| 2 | Maximum clock | 120,000,000 Hz | `samd51-ds`: s54.6 Table 54-6 Maximum Peripheral Clock Frequencies, row fCPU, p.1860; Operating Conditions p.1. Note in spec: The most generous rating: DC to 120 MHz from -40 C to +105 C. At +125 C it is 100 MHz. |  |  |  |
| 3 | Flash: embedded flash | 524,288 B at 0x00000000 | `samd51-ds`: s9.2 Table 9-1 Physical Memory Map p.50, column SAMD51x19 (512 KB); Table 1-2 p.18, row SAMD51J19. |  |  |  |
| 4 | RAM: embedded SRAM | 196,608 B at 0x20000000 | `samd51-ds`: s9.2 Table 9-1 p.50, column SAMD51x19 (192 KB); Table 1-2 p.18, row SAMD51J19 (192/8). |  |  |  |
| 5 | RAM: backup SRAM | 8,192 B at 0x47000000; condition: a separate region in the backup power domain | `samd51-ds`: s9.2 Table 9-1 p.50, row Backup SRAM (8 KB). |  |  |  |
| 6 | RAM: tightly coupled memory, taken from the cache | 4,096 B at 0x03000000; condition: only with the cache disabled or made smaller: TCM size = maximum cache size - configured cache size | `samd51-ds`: Features p.1 (up to 4 KB of TCM); s11.6.7 and Table 11-1 TCM Sizes p.74-75; Figure 8-1 Product Mapping p.48 (CMCC region at 0x03000000). |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 524,288 B and RAM 208,896 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### mk64fn1m0vll12

NXP Kinetis MK64FN1M0VLL12 (1 MB flash, 256 kB RAM). Core `cortex-m4f`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: Every cited page was re-read by a second automated pass, as text extracted from the PDF. Tables were not viewed as rendered pages.

Documents:

- `k64-ds`: Kinetis K64F Sub-Family Data Sheet, K64P144M120SF5, Rev. 7, 11/2016, https://www.nxp.com/docs/en/data-sheet/K64P144M120SF5.pdf (accessed 2026-11-26)
- `an4745`: AN4745 Optimizing Performance on Kinetis K-series MCUs, Rev 1, 06/2014, https://www.nxp.com/docs/en/application-note/AN4745.pdf (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | FPU, precision not stated in the data sheet | `k64-ds`: front page p.1 (Cortex-M4 core with DSP instructions and floating point unit); s7.3 Fields p.80 (F = Cortex-M4 w/ DSP and FPU). |  |  |  |
| 2 | Maximum clock | 120,000,000 Hz | `k64-ds`: s2.3.1 Table 10 Device clock specifications p.17, normal run mode, row fSYS System and core clock; s7.3 Fields p.81 (CC: 12 = 120 MHz). |  |  |  |
| 3 | Flash: program flash | 1,048,576 B at 0x00000000 | `k64-ds`: Ordering Information table p.2, row MK64FN1M0VLL12 (Flash 1 MB); base address from AN4745 Table 1 CODE bus memory map p.3 (program flash from 0x0000_0000 on all K-series parts). |  |  |  |
| 4 | RAM: SRAM (SRAM_L and SRAM_U together) | 262,144 B (no base address in the spec) | `k64-ds`: Ordering Information table p.2, row MK64FN1M0VLL12 (SRAM 256 KB). |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 1,048,576 B and RAM 262,144 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### atsamd21g18a

Microchip ATSAMD21G18A (256 kB flash, 32 kB RAM). Core `cortex-m0plus`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: Every cited page was re-read by a second automated pass, as text extracted from the PDF. Tables were not viewed as rendered pages.

Documents:

- `samd21-ds`: SAM D21/DA1 Family Complete Data Sheet, DS40001882L, Revision L, February 2026, https://ww1.microchip.com/downloads/aemDocuments/documents/MCU32/ProductDocuments/DataSheets/SAM-D21-DA1-Family-Data-Sheet-DS40001882.pdf (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | none | `samd21-ds`: Features p.1 (Processor: Arm Cortex-M0+ CPU; no FPU is listed anywhere in the document). Note in spec: Inferred from absence: the data sheet never says 'no FPU'. |  |  |  |
| 2 | Maximum clock | 48,000,000 Hz | `samd21-ds`: s37.6 Maximum Clock Frequencies, Table 37-7, row fCPU, p.908; Features p.1. Note in spec: The most generous rating. At 125 C, variant A parts are rated 32 MHz (Table 39-4 p.971). |  |  |  |
| 3 | Flash: internal flash | 262,144 B at 0x00000000 | `samd21-ds`: s10.2 Table 10-1 SAM D21 Physical Memory Map p.40, column SAMD21x18 (256 Kbytes); Table 2-1 p.13, row ATSAMD21G18A. |  |  |  |
| 4 | RAM: internal SRAM | 32,768 B at 0x20000000 | `samd21-ds`: s10.2 Table 10-1 p.40, column SAMD21x18 (32 Kbytes); Table 2-1 p.13, row ATSAMD21G18A. |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 262,144 B and RAM 32,768 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### mkl26z64vft4

NXP Kinetis MKL26Z64VFT4 (64 kB flash, 8 kB RAM). Core `cortex-m0plus`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: Every cited page was re-read by a second automated pass, as text extracted from the PDF. Tables were not viewed as rendered pages.

Documents:

- `kl26-ds`: Kinetis KL26 Sub-Family Data Sheet: 48 MHz Cortex-M0+ Based Microcontroller, KL26P64M48SF5, Rev 5, 08/2014, https://www.nxp.com/docs/en/data-sheet/KL26P64M48SF5.pdf (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | none | `kl26-ds`: front page p.1 (48 MHz ARM Cortex-M0+ core; no FPU is listed anywhere in the document); s7.3 Fields p.55 (Z = Cortex-M0+). Note in spec: Inferred from absence: the data sheet never says 'no FPU'. |  |  |  |
| 2 | Maximum clock | 48,000,000 Hz | `kl26-ds`: s2.3.1 Table 13 Device clock specifications p.16, normal run mode, row fSYS System and core clock; s7.3 Fields p.55 (CC: 4 = 48 MHz). |  |  |  |
| 3 | Flash: program flash | 65,536 B (no base address in the spec) | `kl26-ds`: Ordering Information table p.2, row MKL26Z64VFT4 (Flash 64 KB). |  |  |  |
| 4 | RAM: SRAM | 8,192 B (no base address in the spec) | `kl26-ds`: Ordering Information table p.2, row MKL26Z64VFT4 (SRAM 8 KB). |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 65,536 B and RAM 8,192 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### mspm0g3507

Texas Instruments MSPM0G3507 (128 kB flash, 32 kB RAM). Core `cortex-m0plus`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: Every cited page was re-read by a second automated pass, as text extracted from the PDF. Tables were not viewed as rendered pages.

Documents:

- `mspm0g350x-ds`: MSPM0G350x Mixed-Signal Microcontrollers With CAN-FD Interface (data sheet), SLASEX6C, February 2023, revised October 2025, https://www.ti.com/lit/ds/symlink/mspm0g3507.pdf (accessed 2026-11-26)
- `mspm0g-trm`: MSPM0 G-Series 80MHz Microcontrollers Technical Reference Manual, SLAU846F, June 2023, revised November 2026, https://www.ti.com/lit/ug/slau846/slau846.pdf (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | none | `mspm0g350x-ds`: s1 Features p.1 (Core: Arm 32-bit Cortex-M0+ CPU; no FPU is listed anywhere in the document). Note in spec: Inferred from absence: the data sheet never says 'no FPU'. |  |  |  |
| 2 | Maximum clock | 80,000,000 Hz | `mspm0g350x-ds`: s7.3 Recommended Operating Conditions (continued) p.26, row fMCLK: MCLK, CPUCLK frequency with 2 flash wait states. Note in spec: The most generous rating. It needs 2 flash wait states; see the notes. |  |  |  |
| 3 | Flash: main flash (code, ECC corrected) | 131,072 B at 0x00000000 | `mspm0g350x-ds`: Table 5-1 Device Comparison p.6 (MSPM0G3507: 128 / 32); s8.7.1 Table 8-5 Memory Organization p.57 (Code (Flash) from 0x0000.0000). |  |  |  |
| 4 | RAM: SRAM (default region) | 32,768 B at 0x20000000 | `mspm0g-trm`: TRM s1.3.2 Table 1-2 SRAM Region Memory Map p.21 (Default region from 0x2000.0000); size from the data sheet, Table 5-1 p.6 and Table 8-5 p.58 (32 KB). |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 131,072 B and RAM 32,768 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### nrf52832

Nordic nRF52832 QFAA/CIAA (512 kB flash, 64 kB RAM). Core `cortex-m4f`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: The Memory chapter text, the memory map figure, the CPU chapter and the revision history were re-read by a second automated pass in a browser (HTML edition, no page numbers).

Documents:

- `nrf52832-ps`: nRF52832 Product Specification, v1.9, December 2023 (HTML edition; the revision history chapter lists this as the latest), https://docs.nordicsemi.com/bundle/ps_nrf52832/ (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | single-precision FPU | `nrf52832-ps`: chapter CPU, opening paragraph and feature list (single-precision floating-point unit). |  |  |  |
| 2 | Maximum clock | 64,000,000 Hz | `nrf52832-ps`: chapter CPU, Electrical specification, CPU performance ('The CPU clock speed is 64 MHz.'). Note in spec: The only CPU clock the document gives. |  |  |  |
| 3 | Flash: on-chip flash | 524,288 B at 0x00000000 | `nrf52832-ps`: chapter Memory, Table 1 Memory variants (nRF52832-QFAA: 512 kB flash); Figure 2 Memory map (Flash from 0x0000 0000 to 0x0008 0000). |  |  |  |
| 4 | RAM: on-chip RAM (Data RAM view) | 65,536 B at 0x20000000 | `nrf52832-ps`: chapter Memory, Table 1 Memory variants (nRF52832-QFAA: 64 kB RAM); Figure 2 Memory map (Data RAM from 0x2000 0000 to 0x2001 0000). |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 524,288 B and RAM 65,536 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### nrf52833

Nordic nRF52833 (512 kB flash, 128 kB RAM). Core `cortex-m4f`. Check record today: not checked by a person; read by an automated agent on 2026-11-26: The Memory chapter text and the memory layout figure were re-read by a second automated pass in a browser (HTML edition, no page numbers). The CPU chapter and the revision history were read once only.

Documents:

- `nrf52833-ps`: nRF52833 Product Specification, v1.7, June 2024 (HTML edition; the revision history chapter lists this as the latest), https://docs.nordicsemi.com/bundle/ps_nrf52833/ (accessed 2026-11-26)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | single-precision FPU | `nrf52833-ps`: chapter CPU, opening paragraph and feature list (single-precision floating-point unit). |  |  |  |
| 2 | Maximum clock | 64,000,000 Hz | `nrf52833-ps`: chapter CPU, Electrical specification, CPU performance (the CPU clock speed is 64 MHz). Note in spec: The only CPU clock the document gives. |  |  |  |
| 3 | Flash: on-chip flash | 524,288 B at 0x00000000 | `nrf52833-ps`: chapter Memory, first sentence (512 kB of flash memory) and Flash - Non-volatile memory (128 pages of 4 kB); Figure 1 Memory layout (page 0 at 0x0000 0000). |  |  |  |
| 4 | RAM: RAM0 to RAM7 (Data RAM view) | 65,536 B at 0x20000000 | `nrf52833-ps`: chapter Memory, RAM - Random access memory (slaves 0 to 7: two 4 kB sections each); Figure 1 Memory layout (from 0x2000 0000). |  |  |  |
| 5 | RAM: RAM8 (Data RAM view) | 65,536 B at 0x20010000 | `nrf52833-ps`: chapter Memory, RAM - Random access memory (slave 8: two 32 kB sections); Figure 1 Memory layout (0x2001 0000 and 0x2001 8000). |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 524,288 B and RAM 131,072 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### nrf52840

Nordic nRF52840 (on-chip 1 MB flash, 256 kB RAM). Core `cortex-m4f`. Check record today: not checked by a person; read by an automated agent on 2026-11-24: Flash, RAM, clock and FPU figures were confirmed by a second, independent fetch of Nordic's HTML pages (milestone M1 log).

Documents:

- `nrf52840-ps`: nRF52840 Product Specification, v1.11 (4413_417), 2024-10-01; latest per the online revision history on the access date, https://docs.nordicsemi.com/bundle/ps_nrf52840/ (accessed 2026-11-24)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | single-precision FPU | `nrf52840-ps`: s4.1 CPU p.20 (feature list); s4.1.2 CPU configuration table p.21 (FPU: YES). Note in spec: DSP instructions and hardware divide are also listed in s4.1 p.20. |  |  |  |
| 2 | Maximum clock | 64,000,000 Hz | `nrf52840-ps`: s4.1.3.1 CPU performance p.21; s5.4.1 HFCLK controller p.158. Note in spec: The CPU page states 'The CPU clock speed is 64 MHz.' No higher or voltage-dependent rating was found. |  |  |  |
| 3 | Flash: on-chip flash | 1,048,576 B at 0x00000000 | `nrf52840-ps`: s4.2 Memory p.21 (1024 kB); s4.2.2 p.22 (256 pages of 4 kB); base address from Figure 3 memory map p.23. |  |  |  |
| 4 | RAM: on-chip RAM (Data RAM view) | 262,144 B at 0x20000000 | `nrf52840-ps`: s4.2 Memory p.21-22 (256 kB); s4.2.1 and Figure 2 p.22 (RAM0-RAM8 layout); base address from Figure 3 p.23. |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 1,048,576 B and RAM 262,144 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.

### rp2040-pico

Raspberry Pi Pico (RP2040, 2 MB QSPI flash). Core `cortex-m0plus`. Check record today: not checked by a person; read by an automated agent on 2026-11-24: The values were re-checked against text extracted from the two PDFs (milestone M1 log). Pages were not viewed as rendered pages.

Documents:

- `rp2040-ds`: RP2040 Datasheet, Release 13, build date 19/11/2026, build 4c5ccacb2c2f, https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf (accessed 2026-11-24)
- `pico-ds`: Raspberry Pi Pico Datasheet, Release 22, build date 19/11/2026 (Pico Rev3), https://datasheets.raspberrypi.com/pico/pico-datasheet.pdf (accessed 2026-11-24)

| # | What | Spec says | Cited at | Rendered page says | OK? | Discrepancy and fix |
|---|---|---|---|---|---|---|
| 1 | FPU | none | `rp2040-ds`: s2.4.1.2 Configuration p.67 (per-core options list no FPU); s2.8.3.2 Fast Floating Point Library p.136 (float is a ROM software library). Note in spec: Inferred: the datasheet never says 'no FPU' explicitly. Armv6-M (CPUID ARCHITECTURE 0xc, s2.4.8 Table 105 p.87). |  |  |  |
| 2 | Maximum clock | 200,000,000 Hz | `rp2040-ds`: s2.15.3.1 Instances, Note after Table 206, p.179. Note in spec: The most generous documented rating, used because a rule-out needs the best case: 200 MHz with DVDD raised and VREG VSEL = 1.15 V. The guaranteed rating across process, voltage and temperature at the default core voltage is 133 MHz (same note). The Pico datasheet (s1 p.3) still says up to 133 MHz. |  |  |  |
| 3 | Flash: Pico on-board QSPI flash (Winbond W25Q16JV, XIP) | 2,097,152 B at 0x10000000 | `pico-ds`: s1 About Raspberry Pi Pico p.3 ('2 MB Flash', W25Q16JV); s4.1 Programming the flash p.19; XIP base from RP2040 datasheet s2.6.3 p.123. |  |  |  |
| 4 | RAM: SRAM0-5 (main SRAM) | 270,336 B at 0x20000000 | `rp2040-ds`: s2.6.2 SRAM p.122 (264 kB in six banks); s2.2.2.3-4 p.25 (SRAM_END 0x20042000). |  |  |  |
| 5 | RAM: XIP cache used as SRAM | 16,384 B at 0x15000000; condition: only with the XIP cache disabled (CTRL.EN = 0), which slows code running from flash | `rp2040-ds`: s2.6.2.1 p.123; s2.6.3.1 p.124; s2.2.2.2 p.24 (XIP_SRAM_BASE 0x15000000 to XIP_SRAM_END 0x15004000). |  |  |  |
| 6 | RAM: USB DPRAM used as RAM | 4,096 B at 0x50100000; condition: only if USB is not used | `rp2040-ds`: s2.6.2.1 p.123; s2.2.2.8 p.26 (USBCTRL_DPRAM_BASE); s4.1.2.7 DPSRAM p.376. |  |  |  |
| 7 | Library note | The RP2040 boot ROM holds its own floating-point routines, and the Pico SDK uses them by default in place of the compiler's (pico_float, pico_double). The datasheet lists averages of 71 cycles for an add and 58 for a multiply (V2 and V3 ROM). | `rp2040-ds`: s2.8.3.2 Fast Floating Point Library p.136; s2.8.3.2.2 Functions and Table 170 p.137. Note in spec: Table 170 heads its columns 'Cycles (Avg)' while its caption speaks of average time in microseconds; the figures are averages, not minimums, so they cannot serve as a lower bound. |  |  |  |

Also confirm, and write the result under the table:

- [ ] the most generous figure was taken: the highest clock rating the document gives, every region that can hold code or data in some configuration, and aliases counted once;
- [ ] the capacity totals: flash 2,097,152 B and RAM 290,816 B;
- [ ] every note in the spec that cites a page;
- [ ] the document revision above is the one you opened.
