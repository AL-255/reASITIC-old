# reASITIC CLI command reference

Auto-generated from `reasitic.cli._COMMAND_HELP`. Re-run `python scripts/generate_cli_reference.py` after adding new commands.

Categories of commands (use HELP <command> for details):

  Create:    SQ, SP, RING, W, VIA, 3DTRANS, BALUN, CAPACITOR
  Edit:      MOVE, MOVETO, ROTATE, FLIPV, FLIPH, ERASE, RENAME, COPY
  Calc:      IND, RES, Q, K, CAP, METAREA, LISTSEGS, LRMAT
  Network:   PI, ZIN, SELFRES, SHUNTR, PI3, PI4, CALCTRANS, 2PORT,
             2PORTGND, 2PORTPAD, 3PORT, REPORT
  Optimise:  OPTSQ, OPTPOLY, OPTAREA, OPTSYMSQ, BATCHOPT, SWEEP
  Export:    SAVE, LOAD, CIFSAVE, TEKSAVE, SONNETSAVE, S2PSAVE, SPICESAVE
  Session:   VERBOSE, TIMER, SAVEMAT, LOG, RECORD, EXEC, CAT, VERSION,
             HELP, LIST, GEOM, QUIT


## Command details

| Command | Description |
|---|---|
| `2PORT` | 2PORT <name> <f0> <f1> <step> — Frequency sweep of S parameters |
| `2PORTGND` | 2PORTGND <name> <gnd> <f0> <f1> <step> — Sweep with ground spiral |
| `2PORTPAD` | 2PORTPAD <name> <pad1> <pad2> <f0> <f1> <step> — Sweep with bond pads |
| `2PORTTRANS` | 2PORTTRANS <pri> <sec> <f0> <f1> <step> — Transformer 2-port sweep |
| `2PZIN` | 2PZIN <name> <freq_ghz> [Z_re Z_im] — 2-port input impedance |
| `3DTRANS` | 3DTRANS NAME=...:LEN=...:W=...:S=...:N=...:METAL_TOP=...:METAL_BOTTOM=... — 3D transformer |
| `3PORT` | 3PORT <name> <gnd> <freq_ghz> — 3-port reduction |
| `AUTOCELL` | AUTOCELL <alpha> <beta> — Adaptive cell size |
| `BALUN` | BALUN NAME=...:LEN=...:W=...:S=...:N=...:METAL=...:METAL2=... — Planar balun |
| `BATCHOPT` | BATCHOPT [<targets_file>] — Batch optimiser |
| `BEFRIEND` | BEFRIEND <s1> <s2> — Mark two shapes as electrically connected |
| `CALCTRANS` | CALCTRANS <pri> <sec> <freq_ghz> — Transformer L, M, k, n analysis |
| `CAP` | CAP <name> — Substrate shunt capacitance |
| `CAPACITOR` | CAPACITOR NAME=...:LEN=...:WID=...:METAL1=...:METAL2=... — MIM capacitor |
| `CAT` | CAT <path> — Print contents of a file |
| `CELL` | CELL [max_l] [max_w] [max_t] — Cell-size constraints |
| `CHIP` | CHIP [chipx] [chipy] — Resize chip extents |
| `CIFSAVE` | CIFSAVE <path> [<name> ...] — Write CIF layout |
| `COPY` | COPY <src> <dst> — Duplicate a shape |
| `EDDY` | EDDY [on\|off] — Toggle eddy-current calculation |
| `ERASE` | ERASE <name> ... — Delete one or more shapes |
| `EXEC` | EXEC <path> — Execute commands from a script file |
| `FLIPH` | FLIPH <name> — Mirror across y-axis |
| `FLIPV` | FLIPV <name> — Mirror across x-axis |
| `GEOM` | GEOM <name> — Print geometry summary |
| `HELP` | HELP [<command>] — Print this help |
| `HIDE` | HIDE <name> ... — Toggle visibility (no-op headless) |
| `IND` | IND <name> — Self-inductance in nH |
| `INPUT` | INPUT <path> — Alias for EXEC |
| `INTERSECT` | INTERSECT <name> — Detect self-intersecting polygons |
| `JOIN` | JOIN <s1> <s2> [<s3> ...] — Concatenate polygon lists into <s1> |
| `K` | K <name1> <name2> — Mutual inductance and coupling coefficient |
| `LDIV` | LDIV <name> <n_l> <n_w> <n_t> — Inductance with filament discretisation |
| `LIST` | LIST — List all built shapes |
| `LISTSEGS` | LISTSEGS <name> — List all conductor segments |
| `LOAD` | LOAD <path> — Load a JSON session |
| `LOG` | LOG [<filename>] — Start/stop a session log |
| `LRMAT` | LRMAT <name> [path] — Partial-L matrix |
| `METAREA` | METAREA <name> — Metal area in μm² |
| `MMSQUARE` | MMSQUARE NAME=...:LEN=...:W=...:S=...:N=...:METALS=m1,m2,m3 — Multi-metal series spiral |
| `MODIFYTECHLAYER` | MODIFYTECHLAYER <rho\|t\|eps> <layer> <value> — Edit tech layer |
| `MOVE` | MOVE <name> <dx> <dy> — Translate a shape |
| `MOVETO` | MOVETO <name> <x> <y> — Set shape origin |
| `OPTAREA` | OPTAREA <target_L_nH> <freq_ghz> [metal] — Area-minimising optimiser |
| `OPTPOLY` | OPTPOLY <target_L_nH> <freq_ghz> [sides] [metal] — Polygon-spiral optimiser |
| `OPTSQ` | OPTSQ <target_L_nH> <freq_ghz> [metal] — Square-spiral optimiser |
| `OPTSYMPOLY` | OPTSYMPOLY <target_L_nH> <freq_ghz> [sides] [metal] — Symmetric polygon optimiser |
| `OPTSYMSQ` | OPTSYMSQ <target_L_nH> <freq_ghz> [metal] — Symmetric square optimiser |
| `PAUSE` | PAUSE — No-op (for binary parity) |
| `PHASE` | PHASE <name> <+1\|-1> — Set current direction sign |
| `PI` | PI <name> <freq_ghz> — Pi-equivalent (L_s, R_s, C_p1, C_p2) |
| `PI3` | PI3 <name> <freq_ghz> [<gnd>] — 3-port Pi model |
| `PI4` | PI4 <name> <freq_ghz> [<pad1> [<pad2>]] — 4-port Pi model |
| `PIX` | PIX <name> <freq_ghz> — Extended Pi with R-C substrate split |
| `Q` | Q <name> <freq_ghz> — Metal-only quality factor |
| `QUIT` | QUIT / EXIT — Leave the REPL |
| `RECORD` | RECORD [<filename>] — Start/stop macro recording |
| `RENAME` | RENAME <old> <new> — Rename a shape |
| `REPORT` | REPORT <name> <freq_ghz> [<freq_ghz> ...] — Multi-frequency design report |
| `RES` | RES <name> [freq_ghz] — DC and optional AC resistance |
| `RING` | RING NAME=...:RADIUS=...:W=...:METAL=...:SIDES=... — Single ring |
| `ROTATE` | ROTATE <name> <angle_deg> — Rotate about origin |
| `S2PSAVE` | S2PSAVE <name> <f0> <f1> <step> <path> — Touchstone S2P export |
| `SAVE` | SAVE <path> — Save the current session as JSON |
| `SAVEMAT` | SAVEMAT [true\|false] — Toggle matrix dumps |
| `SELFRES` | SELFRES <name> <f_lo> <f_hi> — Self-resonance frequency |
| `SHUNTR` | SHUNTR <name> <freq_ghz> [S\|D] — Parallel-equivalent resistance |
| `SONNETSAVE` | SONNETSAVE <path> [<name> ...] — Write Sonnet .son |
| `SP` | SP NAME=...:RADIUS=...:W=...:S=...:N=...:SIDES=...:METAL=... — Polygon spiral |
| `SPICESAVE` | SPICESAVE <name> <freq_ghz> <path> — SPICE Pi-model |
| `SPLIT` | SPLIT <name> <segment_index> <new_name> — Split a shape |
| `SQ` | SQ NAME=...:LEN=...:W=...:S=...:N=...:METAL=... — Square spiral |
| `SWEEP` | SWEEP LMIN=...:LMAX=...:LSTEP=...:WMIN=...:...:FREQ=... — Cartesian sweep |
| `SYMPOLY` | SYMPOLY NAME=...:RAD=...:W=...:S=...:N=...:SIDES=...:METAL=... — Symmetric polygon spiral |
| `SYMSQ` | SYMSQ NAME=...:LEN=...:W=...:S=...:N=...:METAL=... — Symmetric square spiral |
| `TEKSAVE` | TEKSAVE <path> [<name> ...] — Write gnuplot/Tek dump |
| `TIMER` | TIMER [true\|false] — Toggle per-command timing |
| `TRANS` | TRANS NAME=...:LEN=...:W=...:S=...:N=...:METAL=...:METAL2=... — Planar transformer |
| `UNFRIEND` | UNFRIEND <s1> <s2> — Remove a befriended pair |
| `VERBOSE` | VERBOSE [true\|false] — Toggle diagnostic output |
| `VERSION` | VERSION — Print build info |
| `VIA` | VIA NAME=...:VIA=<idx>:NX=...:NY=... — Via cluster |
| `W` | W NAME=...:LEN=...:WID=...:METAL=... — Single wire |
| `ZIN` | ZIN <name> <freq_ghz> [Z_re Z_im] — Input impedance with load |
