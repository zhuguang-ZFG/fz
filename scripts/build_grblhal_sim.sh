#!/usr/bin/env bash
# R32: build grblHAL_sim for Linux into vendor/grblhal_sim/bin/
# Upstream: https://github.com/grblHAL/Simulator (cmake; same as Windows MinGW path)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${ROOT}/vendor/grblhal_sim/src"
BUILD="${ROOT}/vendor/grblhal_sim/build_linux"
BIN="${ROOT}/vendor/grblhal_sim/bin"

if [[ ! -f "${SRC}/CMakeLists.txt" ]]; then
  echo "Cloning grblHAL/Simulator into ${SRC} ..."
  git clone --depth 1 --recurse-submodules \
    https://github.com/grblHAL/Simulator.git "${SRC}"
fi

mkdir -p "${BUILD}" "${BIN}"
cmake -DCMAKE_BUILD_TYPE=Release -B "${BUILD}" -S "${SRC}"
cmake --build "${BUILD}" -j"$(nproc 2>/dev/null || echo 2)"

# CMake may place binaries in build root or a config subdir
for name in grblHAL_sim grblHAL_validator; do
  found=""
  for cand in \
    "${BUILD}/${name}" \
    "${BUILD}/Release/${name}" \
    "${BUILD}/bin/${name}"; do
    if [[ -f "${cand}" ]]; then
      found="${cand}"
      break
    fi
  done
  if [[ -z "${found}" ]]; then
    found="$(find "${BUILD}" -type f -name "${name}" 2>/dev/null | head -1 || true)"
  fi
  if [[ -z "${found}" || ! -f "${found}" ]]; then
    echo "ERROR: ${name} not found under ${BUILD}" >&2
    find "${BUILD}" -type f -name 'grblHAL*' 2>/dev/null | head -20 >&2 || true
    exit 2
  fi
  cp -f "${found}" "${BIN}/${name}"
  chmod +x "${BIN}/${name}"
  echo "Installed ${BIN}/${name}"
done

echo "Linux sim build OK. Set GRBLHAL_SIM=${BIN}/grblHAL_sim if needed."
