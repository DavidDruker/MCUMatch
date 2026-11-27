# A reproducible environment for mcu-ruleout: the pinned Arm GNU Toolchain 14.2.Rel1, Python, and
# this checkout of the tool. Roadmap task 6.13. Build it yourself; no image is published.
#
#   docker build -t mcu-ruleout .
#   docker run --rm mcu-ruleout shortlist --example fir_f32 --deadline 100us
#   docker run --rm -v "$PWD:/work" mcu-ruleout shortlist /work/my_kernel.c --entry bench --deadline 1ms
#   docker run --rm --entrypoint python mcu-ruleout validation/dry_run_v2.py
#
# x86-64 only: the toolchain archive pinned below is the x86_64 Linux build. On an Arm host
# (Apple silicon) add `--platform linux/amd64` to both commands.
#
# Licences: the image contains the Arm GNU Toolchain (GPL and others) and, through the [emu]
# extra, Unicorn (GPL-2.0). Building and running it yourself is fine. If you redistribute the
# image, those licences' terms apply to you. See THIRD_PARTY_NOTICES.md.
FROM python:3.12-slim

# The same archive and checksum as CI (.github/actions/arm-toolchain). The checksum is the content
# of Arm's own .sha256asc file for this archive. A mismatch stops the build.
ARG TOOLCHAIN_URL=https://developer.arm.com/-/media/Files/downloads/gnu/14.2.rel1/binrel/arm-gnu-toolchain-14.2.rel1-x86_64-arm-none-eabi.tar.xz
ARG TOOLCHAIN_SHA256=62a63b981fe391a9cbad7ef51b17e49aeaa3e7b0d029b36ca1e9c3b2a9b78823

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /tmp/toolchain.tar.xz "$TOOLCHAIN_URL" \
    && echo "$TOOLCHAIN_SHA256  /tmp/toolchain.tar.xz" | sha256sum -c - \
    && mkdir -p /opt/arm-gnu-toolchain \
    && tar -xf /tmp/toolchain.tar.xz -C /opt/arm-gnu-toolchain --strip-components=1 \
    && rm /tmp/toolchain.tar.xz \
    # Documentation and the unused C++ and debugger parts are not needed to build C kernels.
    && rm -rf /opt/arm-gnu-toolchain/share/doc /opt/arm-gnu-toolchain/share/man /opt/arm-gnu-toolchain/share/info

ENV PATH=/opt/arm-gnu-toolchain/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# The whole checkout, so that the validation scripts, the kit and the dataset are there too.
WORKDIR /opt/mcu-ruleout
COPY . .
RUN pip install -e ".[emu]" \
    # Fail the build, not the first run, if the toolchain or the emulator does not work.
    && mcu-ruleout doctor

ENTRYPOINT ["mcu-ruleout"]
CMD ["--help"]
