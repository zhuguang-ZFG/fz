; Minimal program that a stock Grbl/grblHAL controller should accept after unlock.
; Units mm, absolute, feed mode units/min.
G21
G90
G94
G17
G0 X0 Y0 Z5
G1 Z0 F300
G1 X10 Y0 F1000
G1 X10 Y10
G1 X0 Y10
G1 X0 Y0
G0 Z5
M5
M2
