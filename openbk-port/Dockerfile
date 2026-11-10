# x86-64 Linux build environment for the BK7252N camera firmware.
# The Beken SDK's compiler, packager and OTA tool are x86-64 Linux binaries, so on an Apple-silicon
# Mac this image runs under Rosetta (Docker Desktop: Settings -> General -> "Use Rosetta").
# linux/amd64: docker_build.sh passes --platform to docker build and docker run
FROM ubuntu:22.04
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      make python3 python-is-python3 patch xz-utils ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /cam
