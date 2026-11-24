<#
.SYNOPSIS
  M0 spike: build the FIR kernel for Cortex-M0+ and Cortex-M4F, print section sizes.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\build_spike.ps1
  powershell -ExecutionPolicy Bypass -File scripts\build_spike.ps1 -Opt -Os
#>
param(
    [string]$Opt = "-O2",
    [string]$ToolchainBin = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Invoke-Tool {
    param([string]$Exe, [string[]]$ToolArgs)
    & $Exe @ToolArgs
    if ($LASTEXITCODE -ne 0) { throw "$(Split-Path -Leaf $Exe) failed with exit code $LASTEXITCODE" }
}

# Locate the toolchain: -ToolchainBin, then PATH, then the Arm installer's default folder.
if (-not $ToolchainBin) {
    $cmd = Get-Command arm-none-eabi-gcc -ErrorAction SilentlyContinue
    if ($cmd) {
        $ToolchainBin = Split-Path $cmd.Source
    } else {
        $cand = Get-ChildItem -Path "${env:ProgramFiles(x86)}\Arm GNU Toolchain arm-none-eabi\*\bin\arm-none-eabi-gcc.exe",
                                    "$env:ProgramFiles\Arm GNU Toolchain arm-none-eabi\*\bin\arm-none-eabi-gcc.exe" -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending | Select-Object -First 1
        if (-not $cand) { throw "arm-none-eabi-gcc not found. Install it or pass -ToolchainBin <dir>." }
        $ToolchainBin = $cand.DirectoryName
    }
}
$gcc     = Join-Path $ToolchainBin "arm-none-eabi-gcc.exe"
$size    = Join-Path $ToolchainBin "arm-none-eabi-size.exe"
$objdump = Join-Path $ToolchainBin "arm-none-eabi-objdump.exe"
$gccVersion = (& $gcc --version)[0]
Write-Host "Toolchain: $gccVersion"
Write-Host "           $ToolchainBin"

$cores = [ordered]@{
    "m0plus" = @("-mcpu=cortex-m0plus", "-mthumb", "-mfloat-abi=soft")
    "m4f"    = @("-mcpu=cortex-m4", "-mthumb", "-mfpu=fpv4-sp-d16", "-mfloat-abi=hard")
}
$common  = @("-std=c11", $Opt, "-g", "-Wall", "-Wextra",
             "-ffunction-sections", "-fdata-sections",
             "-fstack-usage", "-fcallgraph-info=su")
$src     = Join-Path $root "kernels\fir\fir_f32.c"
$ldfile  = Join-Path $root "kernels\link\spike.ld"

foreach ($core in $cores.Keys) {
    $out = Join-Path $root "build\$core"
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $obj = Join-Path $out "fir_f32.o"
    $elf = Join-Path $out "fir_f32.elf"
    $map = Join-Path $out "fir_f32.map"
    $cpu = $cores[$core]

    Write-Host "`n=== $core ($($cpu -join ' ') $Opt) ==="
    Invoke-Tool $gcc ($cpu + $common + @("-c", $src, "-o", $obj))
    # -lgcc supplies the soft-float helpers (__aeabi_fadd, __aeabi_fmul) on M0+.
    Invoke-Tool $gcc ($cpu + @($Opt, "-nostdlib", "-T", $ldfile,
                               "-Wl,--gc-sections", "-Wl,--entry=fir_f32", "-Wl,-Map=$map",
                               $obj, "-lgcc", "-o", $elf))
    Invoke-Tool $size @("-A", "-d", $elf)
    & $objdump -d -S $elf | Out-File -Encoding utf8 (Join-Path $out "fir_f32.lst")

    # Record the build assumptions next to the ELF so the emulator can print them.
    @("toolchain: $gccVersion",
      "compile:   $(($cpu + $common) -join ' ')",
      "link:      $(($cpu + @($Opt, '-nostdlib', '-T', 'kernels/link/spike.ld', '-Wl,--gc-sections', '-Wl,--entry=fir_f32', '-lgcc')) -join ' ')"
    ) | Out-File -Encoding utf8 (Join-Path $out "build_info.txt")
}
Write-Host "`nOutputs in $(Join-Path $root 'build')"
