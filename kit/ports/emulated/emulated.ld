/* Link script of the emulated port (not hardware). It has the two things every port's script
 * needs: the build-id note is kept, and its address is named __kit_build_id. */

MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 1M
  RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 512K
}

ENTRY(main)

SECTIONS
{
  .text : {
    *(.text .text.*)
    *(.rodata .rodata.*)
  } > FLASH

  .note.gnu.build-id : {
    __kit_build_id = .;
    KEEP(*(.note.gnu.build-id))
  } > FLASH

  .ARM.exidx : { *(.ARM.exidx .ARM.exidx.*) } > FLASH

  .data : {
    *(.data .data.*)
    . = ALIGN(4);
  } > RAM AT > FLASH

  .bss (NOLOAD) : {
    *(.bss .bss.*)
    *(COMMON)
    . = ALIGN(4);
  } > RAM

  PROVIDE(end = .);
  PROVIDE(__end__ = .);
}
