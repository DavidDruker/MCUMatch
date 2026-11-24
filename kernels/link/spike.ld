/* M0 spike linker script: one flat code region and one RAM region.
 * NOT a real part's memory map. Real per-part maps come from cited target
 * specs in M1. There is no vector table or startup code: the emulator
 * harness loads sections directly and calls the entry function. */

MEMORY
{
  FLASH (rx)  : ORIGIN = 0x00000000, LENGTH = 1M
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 256K
}

SECTIONS
{
  .text : {
    *(.text .text.*)
  } > FLASH

  .rodata : {
    *(.rodata .rodata.*)
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
}
