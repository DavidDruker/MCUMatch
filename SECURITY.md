# Security policy

## What this tool does on your machine

`mcu-ruleout` is a local tool. It has no server component that you deploy, no accounts, and it
sends nothing over the network. Knowing what it does run helps you decide what to feed it:

- **It runs your compiler on the source files you give it.** `arm-none-eabi-gcc` compiles and
  links them into a temporary folder. Compiling C does not execute it on your computer, but a
  compiler reads any file an `#include` names, and flags you pass with `--cflags` go to the
  compiler as they are. Give it only code and flags you would give your normal build.
- **It runs the compiled code in an emulator**, never on your processor. The emulated program
  sees only its own sections and a stack. It has no file system, no network and no system calls.
- **It reads the files you name**: sources, ELF files, target specs, and measurement files.
  A target spec and a measurement file are data, parsed as TOML and JSON.
- **It writes only where you tell it**: `--report`, `--share`, `--keep-build`, `--out`, and
  `mcu-ruleout new`. Temporary build folders are deleted afterwards.

## The local web page (`mcu-ruleout ui`)

The page is a convenience for one person on one computer. It accepts source text and runs the
compiler on it, so it is guarded:

- It listens on `127.0.0.1` only. It cannot be reached from another computer.
- Every request must carry a random token that is created at start-up and printed, as part of the
  address, in your terminal. A web page from elsewhere does not have it.
- The `Host` header must be this server's own address, which stops DNS-rebinding tricks.
- File names, symbol names and defines from the page are checked against strict patterns before
  they reach the compiler. Compiler flags from the page are passed to the compiler, as they are on
  the command line.

**Never expose it on a network.** Do not bind it to another address, forward its port, put it
behind a reverse proxy, or run it in a shared container with the port published. Anyone who can
reach it with the token can run your compiler with flags of their choice on your machine. It is
not built to withstand that, and it is not a hosted service.

Treat the address with its token like a password for as long as the page is running. It is in
your browser's history; stop the server with Ctrl+C when you are done.

## Validation recipes

`validation/run_validation_v2.py` can fetch third-party source code by repository and commit,
compile it and run it in the emulator. Read a recipe before running it, as you would any script
that downloads code. `--offline` forbids fetching.

## The measurement kit

Kit firmware runs on your own board. A board port sets clocks and volatile flash-controller
settings. A port must never write option bytes, security bits, protection registers or fuses, and
one that does will not be accepted. Review a port before flashing it, as you would any firmware.

## Supported versions

Only the latest release, and the `main` branch, receive fixes.

## Reporting a vulnerability

Please report it privately, not in a public issue:

- Use GitHub's private vulnerability reporting for this repository: the **Security** tab, then
  **Report a vulnerability**.

Say what you did, what happened, and what you expected. A small example that shows the problem
helps most. You will get an answer as soon as the maintainer can give one; this is a one-person
project, so please allow some days. If the report is accepted, the fix and a note in the changelog
will credit you unless you ask otherwise.

Things that count as vulnerabilities here: a way for a web page to reach the local server without
the token, a way for emulated code to affect the host, a crafted ELF, target spec or measurement
file that makes the tool run code or write outside the folders it was given.

Things that do not: that the tool runs the compiler on files you gave it, or that a harness you
wrote can make the emulator run for a long time (`--max-insns` limits it).
