/* Link script for kernel-only measurement builds. NOT a real memory map.
 * The regions are deliberately huge so the link never fails on size:
 * mcu-ruleout compares the measured sizes against the target spec itself.
 * There is no vector table or startup code. Unlisted (orphan) sections are
 * placed by ld's default rules. */

MEMORY
{
  FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 0x10000000
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 0x20000000
}

SECTIONS
{
  .text : {
    *(.text .text.*)
  } > FLASH

  .rodata : {
    *(.rodata .rodata.*)
  } > FLASH

  .ARM.extab : {
    *(.ARM.extab .ARM.extab.*)
  } > FLASH

  .ARM.exidx : {
    *(.ARM.exidx .ARM.exidx.*)
  } > FLASH

  .data : {
    *(.data .data.*)
  } > RAM AT > FLASH

  .bss (NOLOAD) : {
    *(.bss .bss.*)
    *(COMMON)
  } > RAM

  /* For newlib's sbrk if the kernel calls malloc. The heap itself is not counted. */
  PROVIDE(end = .);
  PROVIDE(__end__ = .);
}
