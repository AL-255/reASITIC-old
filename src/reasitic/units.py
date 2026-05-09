"""Physical constants and unit conventions used across reASITIC.

Conventions inherited from the original ASITIC binary:

* Lateral lengths are in **microns** at the user/REPL boundary.
* Numerical kernels (e.g. Grover formulas) consume lengths in **cm**;
  the conversion factor 1e-4 (μm → cm) is baked in to the kernels —
  see `inductance.grover` where the call sites pre-multiply by
  ``UM_TO_CM`` before invoking the closed-form expression.
* Inductance is reported in **nH**.
* Frequency is in **GHz**.
* Resistance is in **Ω**.

Recovered from the decompiled C: every coordinate-bearing kernel
function performs ``x = x * 0.0001`` before invoking the inductance
math (see ``check_segments_intersect`` in ``asitic_kernel.c``).
"""

from __future__ import annotations

import math

# SI constants -----------------------------------------------------------
# vacuum permeability (H/m)
MU_0 = 4.0e-7 * math.pi
# vacuum permittivity (F/m)
EPS_0 = 8.8541878128e-12
# speed of light (m/s)
C_LIGHT = 299_792_458.0

# Unit conversions -------------------------------------------------------
UM_TO_CM = 1.0e-4
UM_TO_M = 1.0e-6
GHZ_TO_HZ = 1.0e9
NH_TO_H = 1.0e-9
PH_TO_H = 1.0e-12
MOHM_PER_SQ_TO_OHM = 1.0e-3  # tech-file rsh field is in mΩ/sq

# Convenience -------------------------------------------------------------
TWO_PI = 2.0 * math.pi
EIGHT_PI = 8.0 * math.pi  # the 25.1327412287 factor in compute_inductance_inner_kernel
LN2 = math.log(2.0)  # 0.6931471805599453 — appears throughout the Grover formulas
