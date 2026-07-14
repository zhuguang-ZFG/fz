# grblHAL Simulator hardware inject protocol

Source: [grblHAL/Simulator](https://github.com/grblHAL/Simulator) `src/grbl_interface.c`  
Community note: `-p <port>` frees **stdin** for pin toggles while G-code goes over TCP ([README](https://github.com/grblHAL/Simulator)).

## A. TCP realtime (works automated on Windows)

Standard Grbl realtime bytes on the **same TCP stream** as G-code:

| Byte | Meaning | Observed on vendored sim |
|------|---------|---------------------------|
| `!` (0x21) | Feed hold | status → `Hold:…` |
| `~` (0x7E) | Cycle start / resume | `Hold` → `Run` / continue |
| `0x18` | Soft reset | reboot banner |
| `?` | Status (also as line) | `<Idle|…>` / `<Run|…>` |

**Requirement:** use `-t 1` (or slow feed) so motion is still `Run` when hold is sent. With `-t 0`, moves often finish before inject.

## B. Stdin pin toggles (console / interactive)

When sim runs with `-p`, keyboard/stdin chars toggle **MCU GPIO** (not serial):

| Key | Pin |
|-----|-----|
| `h`/`H` | Feed hold **switch** (toggle) |
| `s`/`S` | Cycle start switch |
| `r`/`R` | Reset switch |
| `e`/`E` | E-stop |
| `d`/`D` | Safety door |
| `p`/`P` | Probe |
| `o`/`O` | Probe connected |
| `x`/`y`/`z` | Limit min (port0) |
| `X`/`Y`/`Z` | Limit max (port1) |
| `?` / `@` | Status via realtime enqueue |
| `Ctrl-F` (0x06) | Clean sim exit |

**Windows automation caveat:** piping to `stdin` of a detached process often does **not** drive `platform_poll_stdin()` the same as a real console. Prefer **TCP realtime** for CI.

## C. Plant strategy in `fz`

| Event | Method in plant.py |
|-------|-------------------|
| feed_hold / resume | TCP `!` / `~` |
| soft_reset | TCP `0x18` |
| limit/probe/door | stdin keys if console attached; else mark **unsimulated in CI** |

Hard-limit trip via `x`/`X` remains best-effort; product paper/BT still need G3b.
