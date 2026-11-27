/* Link script for tests/data/firmware.c: a vendor-style memory map.
 * FLASH_ORIGIN and RAM_ORIGIN come from the command line (-Wl,--defsym=...), so one script
 * serves an STM32-like image at 0x08000000 and an RP2040-like image at 0x10000000. */

MEMORY
{
  FLASH (rx)  : ORIGIN = FLASH_ORIGIN, LENGTH = 256K
  RAM   (rwx) : ORIGIN = RAM_ORIGIN,   LENGTH = 32K
}

ENTRY(Reset_Handler)

SECTIONS
{
  .isr_vector : { KEEP(*(.isr_vector)) } > FLASH

  .text : {
    *(.text .text.*)
    *(.rodata .rodata.*)
  } > FLASH

  _sidata = LOADADDR(.data);

  .data : {
    _sdata = .;
    *(.data .data.*)
    . = ALIGN(4);
    _edata = .;
  } > RAM AT > FLASH

  .bss (NOLOAD) : {
    _sbss = .;
    *(.bss .bss.*)
    *(COMMON)
    . = ALIGN(4);
    _ebss = .;
  } > RAM

  _estack = ORIGIN(RAM) + LENGTH(RAM);
}
