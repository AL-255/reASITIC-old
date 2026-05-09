# reASITIC ↔ ASITIC C function mapping

Living catalog of every Python function in the reASITIC port and the
reverse-engineered C function(s) it ports / mirrors / supersedes. The
C side lives in `../decomp/output/asitic_*.c`; addresses are absolute
load-time virtual addresses inside `run/asitic.linux.2.2`.

The relationship column uses these tags:

| Tag           | Meaning |
|---------------|---------|
| **port**      | Direct re-implementation of the C body (formula or logic preserved) |
| **partial**   | Implements a subset of the C function's behavior |
| **subsumes**  | Replaces multiple C helpers with one Python implementation |
| **dispatch**  | Mirrors the C dispatcher's call but lets cleaner code do the work |
| **stub**      | Placeholder; full port deferred to a later phase |
| **utility**   | Python-only helper; no direct C analogue |
| **pure**      | Pure-Python implementation of standard math (no C analogue) |

When updating: add a row whenever a new Python function is written.
Keep the table sorted by Python module path, then by function name.

---

## `reasitic.units`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `MU_0`, `EPS_0`, `C_LIGHT` | utility | — | — | SI constants |
| `UM_TO_CM` (`= 1e-4`) | utility | — | — | Matches the `0.0001` factor scattered through the kernel for μm→cm conversion before invoking Grover formulas (e.g. `check_segments_intersect` body, `compute_inductance_inner_kernel`) |
| `LN2`, `EIGHT_PI`, `TWO_PI` | utility | — | — | The literal `0.6931471805599453` and `25.1327412287` constants from the decomp |

## `reasitic.tech`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `parse_tech_file` | partial | `techfile_parse_layers` | `0x0807b328` | Section/key parsing; the binary's variant also runs `techfile_validate_*` and `techfile_alloc_layer_table` |
| `parse_tech` | partial | `techfile_parse_layers` | `0x0807b328` | String/stream entry point |
| `write_tech` / `write_tech_file` | utility | (no direct C analogue) | — | Round-trip serialisation back to ``.tek`` |
| `Chip` (dataclass) | port | `<chip>` global block | `g_chip_xmax`/`g_chip_ymax`/etc. | Contents of `g_chip_*` BSS cells |
| `Layer` | port | substrate-layer record | `g_substrate_layer_table` (`0x080d8ac8`) | 16-byte per-entry record |
| `Metal` | port | metal-layer record | `g_metal_layer_table` (`0x080d8910`) | 0xec-byte per-entry record; `+0xb0`=t, `+0xb8`=rsh |
| `Via` | port | via-layer record | `g_via_layer_table` (`0x080d8914`) | 0xf0-byte record; `+0xa0`=Nx, `+0xa8`=Ny, `+0xc0`=R, `+0xcc`=top, `+0xd0`=bottom |
| `Tech.metal_by_name` | port | `lookup_metal_layer_by_name` | `0x08056494` | |
| `Tech.via_by_name` | port | `lookup_via_layer_by_name` | `0x080563fc` | |

## `reasitic.geometry`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `Point`, `Segment`, `Polygon` | port | `Polygon` record | (240-byte struct) | Pythonic flatten of `+0xdc` metal idx, `+0xe8` sub-chain, `+0xec` next, `+0xcc` width |
| `Shape` | port | `Shape` record | (188-byte struct) | Mirror of fields described in `shape_record_init_from_args` |
| `square_spiral` | partial | `cmd_square_build_geometry` | `0x08056670` | Simple-case port; no exit-metal transition or 3D mirroring |
| `polygon_spiral` | partial | `cmd_spiral_build_geometry` | `0x08057248` | Polygon-spiral with N sides |
| `wire` | port | `cmd_wire_build_geometry` | `0x08057998` | Single straight rectangle |
| `via` | partial | `cmd_via_build_geometry` | `0x08057b78` | Via cluster as a single z-segment between two metal layers |
| `ring` | port | `cmd_ring_build_geometry` (case 22) | — | Implemented as a single-turn polygon spiral |
| `transformer` | partial | `cmd_trans_build_geometry` | `0x080576d4` | Two interleaved square coils |
| `transformer_3d` | partial | `cmd_3dtrans_build_geometry` | `0x08057d40` | Two co-axial square coils on different metals + via |
| `symmetric_polygon` | partial | `cmd_sympoly_build_geometry` (case 17) | — | Symmetric centre-tapped polygon spiral |
| `multi_metal_square` | partial | `cmd_mmsq_build_geometry` (case 18) | — | Multi-metal series stacked square spiral |
| `symmetric_square` | partial | `cmd_symsq_build_geometry` | `0x08059854` | Two-arm centre-tapped variant |
| `balun` | partial | `cmd_balun_build_geometry` (case 5) | — | Two stacked counter-wound square coils |
| `capacitor` | partial | `cmd_capacitor_build_geometry` (case 4) | — | Two stacked rectangles on adjacent metals |
| `Shape.translate` | port | `shape_translate_inplace_xy` | `0x0805b8d4` | Bounding-box-recentre logic — out-of-place in Python |
| `Shape.bounding_box` | port | `shape_bbox_scan` | `0x0807a9f4` | |
| `Shape.segments` | utility | — | — | Python-only flat segment list |
| `_resolve_metal` | utility | — | — | Tech-table lookup helper |

## `reasitic.inductance.grover`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `segment_self_inductance(L, r)` | port | `grover_segment_self_inductance` | `0x08064308` | Round-wire Grover formula |
| `rectangular_bar_self_inductance(L, W, T)` | port | inner formula in `cmd_inductance_compute` | `0x0804ce78` | The `2L * (ln(2L/(W+T)) + 0.50049 + (W+T)/(3L))` block at lines 1417-1452 of `asitic_repl.c` |
| `coupled_wire_self_inductance(W, T, S)` | port | `coupled_wire_self_inductance_grover` | `0x0804cb90` | Grover Table 24 — full nested expansion |
| `mohan_modified_wheeler` | utility | (no direct C analogue) | — | Mohan 1999 closed-form L estimate (sanity check) |
| `parallel_segment_mutual` | partial | parallel-filament leaf of `mutual_inductance_4corner_grover` | `0x080613bc` | Clean closed form via the φ(t) antiderivative; the C version handles the general (non-parallel-axes) case |

## `reasitic.inductance.partial`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `compute_self_inductance(shape)` | dispatch | `cmd_inductance_compute` | `0x0804ce78` | Same `sum_self + 2·sum_pair_mutuals` structure |
| `compute_mutual_inductance(a, b)` | dispatch | `cmd_coupling_compute` | `0x0804d03c` | Cross-pair Greenhouse sum |
| `coupling_coefficient(a, b)` | port | `cmd_coupling_compute` (final division) | `0x0804d03c` | `M / sqrt(L1·L2)` |
| `_axis_of`, `_parallel_axis_pair`, `_segment_pair_mutual` | subsumes | case-2 dispatch in `check_segments_intersect` | `0x080611ec` | The C dispatcher classifies pairs (parallel / orthogonal / general / intersecting); we only handle parallel here |

## `reasitic.inductance.filament`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `Filament` (dataclass) | port | per-filament record inside `solve_inductance_matrix` | `0x08064360` | Pythonic; no byte layout dependency |
| `filament_grid(seg, n_w, n_t)` | partial | `set_cell_size_normal` | `0x0807043c` | Uniform cross-section subdivision; the binary's version also adapts cell size based on freq + skin |
| `auto_filament_subdivisions` | port | freq-dependent cell sizing in `set_cell_size_normal` | `0x0807043c` | Automatic skin-depth-aware subdivision |
| `build_inductance_matrix` | port | `fill_inductance_diagonal` + `fill_inductance_offdiag` | `0x080664ec` / `0x08066658` | Symmetric N×N partial inductance |
| `build_resistance_vector` | port | `compute_inductance_inner_kernel` (looped) | `0x0804d1e4` | Per-filament Wheeler AC R |
| `solve_inductance_matrix` | partial | `solve_inductance_matrix` | `0x08064360` | Schur-complement reduction of per-filament Z to per-segment, then series sum |
| `solve_inductance_mna` | port | `solve_inductance_matrix` | `0x08064360` | Rigorous modified-nodal-analysis solve (handles n_w·n_t > 1 correctly) |

> **Deferred** kernels still on the to-do list:
> `mutual_inductance_orthogonal_segments` (`0x08061b84`) — corner correction, negligible for Manhattan spirals,
> `mutual_inductance_filament_general` (`0x08062230`) — non-axis-aligned 3D segment pairs,
> `mutual_inductance_3d_segments` (`0x08062ebc`),
> `mutual_inductance_assemble_pair` (`0x0806597c`),
> `mutual_inductance_filament_kernel` (`0x080b1*`),
> `wire_inductance_far_field_kernel` (`0x08063ca0`).

## `reasitic.resistance.dc`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `segment_dc_resistance` | port | metal branch of `compute_inductance_inner_kernel` | `0x0804d1e4` | The `R = rsh · L / W` core; via branch handled separately |
| `compute_dc_resistance(shape, tech)` | partial | `compute_dc_resistance_per_polygon` | `0x0804dd40` | Bare summation only; the C version also splits at a tap point and computes microstrip caps |

## `reasitic.resistance.skin`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `ac_resistance_segment` | port | metal-layer branch of `compute_inductance_inner_kernel` | `0x0804d1e4` | Wheeler-style skin-effect formula with the exact decomp constants (0.0035, 1.1147, 1.2868, 1.2296, 1.287, 0.43093, 0.041) |
| `compute_ac_resistance(shape, tech, freq)` | dispatch | `cmd_resis_compute` / `cmd_resishf_compute` | `0x0804eedc` / `0x0804d70c` | Per-segment loop driven by Python instead of the C kernel's filament walk |
| `skin_depth(rho, freq, mu_r)` | pure | — | — | Textbook formula `δ = sqrt(ρ/(π·μ·f))`, used as a reference / sanity check |

## `reasitic.quality`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `metal_only_q(shape, tech, freq)` | partial | `compute_q_factor_from_globals` | `0x0804ec50` | Metal-loss-only `Q = ωL/R`; the C version reads the global Y matrix (after substrate FFT) so its Q includes substrate loss |

## `reasitic.network.twoport`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `y_to_z` / `z_to_y` | port | `y_to_z_2port_invert` | `0x0808800c` | Direct 2×2 inverse |
| `y_to_s` | port | `y_to_s_2port_50ohm` | `0x08087d14` | Reference admittance defaults to 0.02 S (50 Ω), matching the binary's hardcoded `Y0` |
| `s_to_y` | utility | — | — | Inverse of `y_to_s`; binary doesn't ship the reverse path |
| `deembed_pad_open` | utility | — | — | Open-only de-embedding (subtract pad shunt) |
| `deembed_pad_open_short` | utility | — | — | Open-then-short de-embedding (subtract pad shunt and access-line series) |
| `pi_equivalent(Y, freq)` | port | `extract_pi_equivalent` | `0x08089e40` | `Z_s = -1/Y₁₂`, `Y_p₁ = Y₁₁ + Y₁₂`, `Y_p₂ = Y₂₂ + Y₁₂` |
| `pi_to_y(model)` | utility | — | — | Inverse synthesis; convenience for testing |
| `spiral_y_at_freq(shape, tech, freq)` | partial | `analyze_narrow_band_2port` | `0x080515e4` | Single-frequency Y construction; lossless-substrate first cut |
| `PiModel` (dataclass) | utility | — | — | Holds `(Z_s, Y_p1, Y_p2, freq_ghz)` |

## `reasitic.network.threeport`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `reduce_3port_z_to_2port_y` | port | `reduce_3port_z_to_2port_y` | `0x080881a8` | Invert 3×3 Z, take 2×2 sub-block of Y |
| `z_to_s_3port` | port | `z_to_s_3port_50ohm` | `0x080884b8` | `S = (Z − Z₀ I)(Z + Z₀ I)⁻¹` |

## `reasitic.network.touchstone`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `TouchstonePoint` / `TouchstoneFile` | utility | — | — | Per-frequency / file-level wrappers |
| `write_touchstone` / `write_touchstone_file` | utility | — | — | IEEE Touchstone v1 writer |
| `read_touchstone` / `read_touchstone_file` | utility | — | — | Touchstone v1 parser; round-trips the writer |

## `reasitic.network.sweep`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `NetworkSweep` (dataclass) | utility | — | — | Bundles per-freq Y/Z/S/Pi |
| `two_port_sweep` | dispatch | `cmd_2port_emit` (case 528) | — | Drives `analyze_narrow_band_2port` over a freq sweep |
| `linear_freqs(start, stop, step)` | utility | — | — | Inclusive linear stride |

## `reasitic.network.analysis`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `pi_model_at_freq` | port | `cmd_pi_emit` (case 505) → `extract_pi_lumped_3port` | `0x080897e4` | Breaks Z_s / Y_p into physical L, R, C, g |
| `PiResult` (dataclass) | utility | — | — | (freq, L_nH, R, C_p1, C_p2, g_p1, g_p2) |
| `zin_terminated` | port | `zin_terminated_2port` | `0x0804e9b0` | Z_in = Z_11 − Z_12·Z_21/(Z_22 + Z_load) |
| `self_resonance` | port | `cmd_selfres_compute` | `0x0804e590` | Linear-scan + bisection on Im(Z_11) zero crossing |
| `SelfResonance` (dataclass) | utility | — | — | (freq, Q, z11_imag, converged) |
| `shunt_resistance` | port | `cmd_shuntr_compute` (case 533) | `0x0804e354` | R_p = R_s · (1 + Q²); supports differential mode |
| `ShuntRResult` (dataclass) | utility | — | — | (freq, R_p, Q, L, R_series) |
| `pi3_model` | port | `cmd_pi3_emit` (case 517) | `0x08050b2c` | 3-port Pi with optional ground spiral |
| `Pi3Result` (dataclass) | utility | — | — | (L, R, C_p1_to_gnd, C_p2_to_gnd, R_sub_p1, R_sub_p2) |
| `pi4_model` | port | `cmd_pi4_emit` (case 518) | `0x08050d10` | 4-port Pi with bond-pad caps |
| `Pi4Result` (dataclass) | utility | — | — | (L, R, C_pad{1,2}, C_sub{1,2}, R_sub{1,2}) |
| `pix_model` | port | `cmd_pix_emit` (case 538) | `0x080527a4` | Extended Pi with R-C substrate split |
| `PixResult` (dataclass) | utility | — | — | (L, R, R_sub{1,2}, C_sub{1,2}) |
| `calc_transformer` | port | `cmd_calctrans_emit` (case 523) | `0x08051280` | (L_pri, L_sec, R_pri, R_sec, M, k, n, Q_pri, Q_sec) |
| `TransformerAnalysis` (dataclass) | utility | — | — | |

## `reasitic.persistence`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `save_session` / `load_session` | subsumes | `BSAVE`/`BLOAD`/`SAVE`/`LOAD` (cases 201, 202, 225, 226) | — | Replaces the binary's custom format with portable JSON |
| `shape_to_dict` / `shape_from_dict` | utility | — | — | Shape ↔ dict |
| `tech_to_dict` / `tech_from_dict` | utility | — | — | Tech ↔ dict |

## `reasitic.exports`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `write_cif` / `write_cif_file` | partial | `cmd_cifsave` (case 300) | — | CIF intermediate format; spiral polygons emitted on per-metal layers |
| `read_cif` / `read_cif_file` | utility | — | — | Parse CIF back into Shapes; round-trips the writer |
| `read_sonnet` / `read_sonnet_file` | utility | — | — | Parse Sonnet `.son` GEO block back into Shapes |
| `write_tek` / `write_tek_file` | partial | `cmd_print_tek` (case 214) | — | gnuplot-friendly x/y dump |
| `write_tek4014` / `write_tek4014_file` | port | `cmd_print_tek` (case 214) | — | True Tek 4014 escape-code byte stream |
| `write_sonnet` | partial | `cmd_sonnet_emit` (case 302) | — | Minimal Sonnet `.son` (header + GEO block) |
| `write_spice_subckt` / `write_spice_subckt_file` | utility | — | — | SPICE Pi-model `.subckt` block; replaces the binary's text 2Port output for circuit-sim consumption |
| `write_fasthenry` / `write_fasthenry_file` | utility | — | — | FastHenry ``.inp`` for cross-validation against the MIT inductance extractor |

## `reasitic.optimise`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `optimise_square_spiral` | dispatch | `cmd_opt_l_sq` (case 700) | — | scipy.optimize SLSQP wrapper; the binary uses hand-rolled gradient descent |
| `OptResult` (dataclass) | utility | — | — | (length, width, spacing, turns, L, Q, success, message) |
| `optimise_polygon_spiral` | dispatch | `cmd_opt_l_poly` (case 708) | — | Polygon-spiral OptPoly variant |
| `optimise_area_square_spiral` | dispatch | `cmd_opt_area` (case 706) | — | Minimise length² (footprint) under L target |
| `optimise_symmetric_square` | dispatch | `cmd_opt_l_symsq` (case 713) | — | Symmetric centre-tapped square |
| `batch_opt_square` | dispatch | `cmd_batchopt` (case 707) | — | Multi-target driver |
| `sweep_square_spiral` | dispatch | `cmd_sweep` (case 711, SWEEP) | — | Cartesian (length × width × spacing × turns) → numpy structured array |
| `sweep_to_tsv` | utility | — | — | TSV serialiser for the sweep array |

## `reasitic.inductance.eddy`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `eddy_correction` | port | `gen_eddy_current_matrix` + `inductance_eddy_fold` | `0x080b0e50`, `0x...` | Ground-image method; substrate-skin-depth attenuation |
| `solve_inductance_with_eddy` | dispatch | `solve_inductance_matrix` w/ eddy fold | `0x08064360` | Adds (ΔL, ΔR) eddy correction to closed-form result |
| `_image_filament` | utility | — | — | Mirrors filament across z=0 with reversed direction |

## `reasitic.substrate.green`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `_stack_reflection_coefficient` | port | layered-stack reflection in `compute_green_function` | `0x0808c350` | Recursive transmission-line formula |
| `green_function_static` | port | quasi-static limit of `compute_green_function` | `0x0808c350` | Per-pair static Green's function value |
| `coupled_capacitance_per_pair` | port | `coupled_microstrip_to_cap_matrix` | `0x0804ecac` | Mutual cap from area × Green's value |
| `integrate_green_kernel` | partial | full Sommerfeld in `compute_green_function` | `0x0808c350` | Bessel-J0 numerical integration via scipy.integrate.quad |

## `reasitic.substrate.fft_grid`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `GreenFFTGrid` (dataclass) | port | grid record in `fft_setup` | `0x08091548` | Holds (g_grid, g_fft) for batched conv |
| `setup_green_fft_grid` | port | `fft_setup` | `0x08091548` | Vectorised; reads chip dims and fftx/ffty from tech |
| `green_apply` | port | `fft_apply_to_green` | `0x080912c0` | scipy.fft 2-D convolution |

## `reasitic.info`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `metal_area` | port | `cmd_metalarea_print` (case 413) | `0x0804ee74` | Shoelace area sum across all polygons |
| `list_segments` / `format_segments` | port | `cmd_listsegs` (case 210) | — | Per-segment dump with positions, length, width |
| `lr_matrix` / `format_lr_matrix` | port | `cmd_lrmat` (case 531) | — | Per-segment partial-L matrix in nH |

## `reasitic.substrate`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `parallel_plate_cap_per_area` | utility | — | — | Standard parallel-plate formula |
| `shape_shunt_capacitance` | partial | `cmd_capacitance_compute` (case 503) → calls into `coupled_microstrip_caps_hj` | `0x0804df6c` | First-cut substrate model: parallel plate + edge fringe. Full FFT Green's function (`compute_green_function` `0x0808c350`) deferred. |

## `reasitic.cli` (REPL commands)

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `Repl.cmd_load_tech` | port | tech-load on startup → `init_load_techfile` | `0x0804b7b0` | |
| `Repl.cmd_wire` | dispatch | `cmd_wire_build_geometry` | `0x08057998` | |
| `Repl.cmd_square` | dispatch | `cmd_square_build_geometry` | `0x08056670` | |
| `Repl.cmd_spiral` | dispatch | `cmd_spiral_build_geometry` | `0x08057248` | |
| `Repl.cmd_ring` | dispatch | case `22` (Ring) | — | |
| `Repl.cmd_via` | dispatch | case `14` (Via) → `cmd_via_build_geometry` | `0x08057b78` | |
| `Repl.cmd_ind` | dispatch | case `502` (Ind) → `cmd_inductance_compute` | `0x0804ce78` | |
| `Repl.cmd_res` | dispatch | case `501` (Res) → `cmd_resis_compute` | `0x0804eedc` | |
| `Repl.cmd_q` | dispatch | case `504` (Q) → uses `compute_q_factor_from_globals` | `0x0804ec50` | |
| `Repl.cmd_coupling` | dispatch | case `500` (K/Coupling) → `cmd_coupling_compute` | `0x0804d03c` | |
| `Repl.cmd_2port` | dispatch | case `528` (2Port) → `analyze_narrow_band_2port` | `0x080515e4` | |
| `Repl.cmd_cap` | dispatch | case `503` (Cap) → substrate cap path | — | |
| `Repl.cmd_save` / `cmd_load` | dispatch | cases `225`/`226` (Save/Load) | — | JSON persistence |
| `Repl.cmd_cifsave` | dispatch | case `300` (CIFSave) | — | |
| `Repl.cmd_teksave` | dispatch | case `214` (PrintTekFile) | — | gnuplot text format |
| `Repl.cmd_sonnetsave` | dispatch | case `302` (SonnetSave) | — | |
| `Repl.cmd_s2psave` | dispatch | (no direct C analogue; standard Touchstone export) | — | |
| `Repl.cmd_optsq` | dispatch | case `700` (OptSq) | — | scipy.optimize SLSQP |
| `Repl.cmd_2port_gnd` | dispatch | case `529` (2PortGnd) | — | 2-port sweep with grounded coupling |
| `Repl.cmd_2port_pad` | dispatch | case `530` (2PortPad) | — | 2-port sweep with bond-pad caps |
| `Repl.cmd_3port` | dispatch | case `536` (3Port) → `reduce_3port_z_to_2port_y` | `0x080881a8` | |
| `Repl.cmd_2port_trans` | dispatch | case `524` (2PortTrans) | — | Transformer 2-port over a freq sweep |
| `Repl.cmd_2pzin` | dispatch | case `537` (2PZin) | — | Input impedance with arbitrary load |
| `Repl.cmd_pix` | dispatch | case `538` (PiX) → `cmd_pix_emit` | `0x080527a4` | Extended Pi with R-C substrate split |
| `Repl.cmd_befriend` / `cmd_unfriend` | dispatch | cases `417`/`418` | — | Shape friendship pairs |
| `Repl.cmd_intersect` | dispatch | case `419` (Intersect/FindI) | — | Bounding-box overlap detection |
| `Repl.cmd_trans` / `cmd_balun` / `cmd_capacitor` / `cmd_symsq` | dispatch | cases `3`/`5`/`4`/`16` | — | Builder commands |
| `Repl.cmd_split` / `cmd_join` / `cmd_phase` | dispatch | cases `416`/`409`/`404` | — | Edit commands |
| `Repl.cmd_modify_tech_layer` / `cmd_cell` / `cmd_auto_cell` / `cmd_chip` / `cmd_eddy` | dispatch | cases `222`/`207`/`212`/`217`/`221` | — | Tech and cell-size edits |
| `Repl.cmd_pause` / `cmd_input` / view no-ops | dispatch | cases `216`/`215`/100-115 | — | Session and view commands |
| `Repl.cmd_sympoly` / `cmd_mmsquare` | dispatch | cases `17`/`18` | — | Symmetric polygon and multi-metal square builders |
| `Repl.cmd_ldiv` | dispatch | case `800` (LDiv) | — | Inductance with filament discretisation |
| `Repl.cmd_optsympoly` | dispatch | case `714` (OPTSYMPOLY) | — | Symmetric polygon optimiser |
| `Repl.cmd_erase` / `cmd_rename` / `cmd_copy` / `cmd_hide` | dispatch | cases `400`/`401`/`402`/`420` | — | Shape-management commands |
| `Repl.cmd_verbose` / `cmd_timer` / `cmd_savemat` | dispatch | cases `220`/`228`/`229` | — | Session toggles |
| `Repl.cmd_log` / `cmd_record` / `cmd_exec_script` / `cmd_cat` | dispatch | cases `203`/`213`/`209`/`227` | — | Session recording / playback |
| `Repl.cmd_version` / `cmd_help` | dispatch | cases `208`/`206` | — | Help & version |
| `Repl.cmd_pi` | dispatch | case `505` (Pi) | — | Pi-model L/R/C breakout at one frequency |
| `Repl.cmd_zin` | dispatch | case `535` (Zin) → `zin_terminated_2port` | `0x0804e9b0` | |
| `Repl.cmd_selfres` | dispatch | case `534` (SelfRes) → `cmd_selfres_compute` | `0x0804e590` | |
| `Repl.cmd_listsegs` | dispatch | case `210` (ListSegs) | — | |
| `Repl.cmd_metarea` | dispatch | case `413` (MetalArea) | — | |
| `Repl.cmd_lrmat` | dispatch | case `531` (LRMAT) | — | |
| `Repl.cmd_sweep` | dispatch | case `711` (Sweep) | — | Cartesian param grid |
| `Repl.cmd_3dtrans` | dispatch | case `10` (3DMirrorTrans) | `0x08057d40` | |
| `Repl.cmd_shuntr` | dispatch | case `533` (ShuntR) → `cmd_shuntr_compute` | `0x0804e354` | S/D mode |
| `Repl.cmd_pi3` | dispatch | case `517` (Pi3) → `cmd_pi3_emit` | `0x08050b2c` | |
| `Repl.cmd_pi4` | dispatch | case `518` (Pi4) → `cmd_pi4_emit` | `0x08050d10` | |
| `Repl.cmd_calctrans` | dispatch | case `523` (CalcTrans) | `0x08051280` | |
| `Repl.cmd_optpoly` | dispatch | case `708` (OptPoly) | — | |
| `Repl.cmd_optarea` | dispatch | case `706` (OptArea) | — | |
| `Repl.cmd_optsymsq` | dispatch | case `713` (OptSymSq) | — | |
| `Repl.cmd_batchopt` | dispatch | case `707` (BatchOpt) | — | |
| `Repl.cmd_spicesave` | dispatch | (no direct C analogue) | — | SPICE Pi-model |
| `Repl.cmd_geom` | dispatch | case `410` (Geom) → `cmd_geom_show` | `0x0804c620` | |
| `Repl.cmd_list` | port | case `224` (Who/List) | (in `cmd_dispatch_switch`) | |

> **Not yet ported** (REPL surface): the remaining 107 commands listed in
> `../decomp/output/commands.md`. The biggest gaps are 3D structure
> creators (`Trans`, `Balun`, `3DTrans`, `SymSq`, `SymPoly`, `MMSquare`,
> `Ring`, `Capacitor`), file I/O (`Save`/`Load`/`CIFSave`/`SonnetSave`),
> network commands beyond Ind/Res/Q/K (`Pi`, `Pi2`, `Pi3`, `Pi4`,
> `2Port`, `3Port`, `SelfRes`, `ShuntR`, `Zin`), and the optimisation
> family (`OptSq`, `OptPoly`, `OptArea`, `Sweep`).

## `reasitic.validation.binary_runner`

| Python | Tag | C function | Address | Notes |
|---|---|---|---|---|
| `BinaryRunner.run_script` | utility | — | — | Drives `run/asitic` headlessly under `xvfb-run` |
| `BinaryRunner.geom` | utility | invokes `cmd_geom_show` indirectly | `0x0804c620` | Cross-validation harness for geometry |
| `parse_geom_output`, `GeomResult` | utility | — | — | Parses the binary's textual `Geom` output |

---

## Subsumed by NumPy / SciPy / Python stdlib

Many of the binary's small numerical helpers are direct one-liners
in NumPy / SciPy / Python and do not need their own Python module.
They are listed here so the coverage accounting reflects them:

### Vector / FPU primitives (subsumed by `numpy` / `math`)

| C function (decomp address) | Python equivalent |
|---|---|
| `vec3_dot_product` (`0x0806421c`) | `np.dot(a, b)` / built-in |
| `vec3_cross_product` (`0x080641a8`) | `np.cross(a, b)` |
| `vec3_l2_norm` (`0x0806422c`) | `np.linalg.norm(v)` |
| `vec3_sqrt_dot_pair` (`0x08064208`) | `np.sqrt(np.dot(a, b))` |
| `dist3d_pt` (`0x080642dc`) | `np.linalg.norm(b - a)` |
| `coth_double` (`0x08064248`) | `1.0 / math.tanh(x)` |
| `cdouble_tanh` (`backend`) | `cmath.tanh(z)` (numpy supports complex too) |
| `cos_or_sin_select` (`backend`) | `math.cos` / `math.sin` |
| `clipped_pow2_x` (`backend`) | `math.pow(2.0, x)` with bounds |
| `ref_pow_double` (`backend`) | `pow(x, n)` |
| `safe_divide_clipped` (`0x08063bb4`) | `a / b if abs(b) > eps else 0.0` |
| `safe_log_minus_x_clipped` (`backend`) | `math.log1p(-x)` for small x |
| `build_3x3_identity_complex` (`backend`) | `np.eye(3, dtype=complex)` |

### LAPACK wrappers (subsumed by `scipy.linalg`)

| C function | Python equivalent |
|---|---|
| `lapack_lu_factor_raw` / `lapack_lu_factor_matobj` | `scipy.linalg.lu_factor(A)` |
| `lapack_lu_solve_raw` / `lapack_lu_solve_matobj` | `scipy.linalg.lu_solve(piv, b)` |

### Container / state helpers (subsumed by Python lists/dicts)

| C function | Python equivalent |
|---|---|
| `list_prepend_15int_node` (`0x080561e0`) | `list.insert(0, …)` |
| `list_destroy_node_chain_at_38` (`0x0805623c`) | (garbage-collected) |
| `save_chain_find_by_name` (`0x080563c4`) | `dict.get(name)` |
| `save_chain_unlink` (`0x080565bc`) | `del shapes[name]` |
| `spiral_list_reverse_at_84` (`0x08056580`) | `list[::-1]` |
| `filament_list_to_index_array` | `np.asarray(list)` |
| `destroy_filament_record_5char_5ptr` | (garbage-collected) |
| `clear_yzs_globals` | (no globals in port) |
| `capacitance_cleanup` (`0x08056524`) | (no globals in port) |
| `dump_complex_matrix_to_file_a` / `_b` | `np.savetxt(...)` (debug only) |
| `kernel_noop_stub_a` / `_b` | (cosmetic stubs) |

### Interactive prompts (subsumed by `cli.Repl` parser)

| C function | Python equivalent |
|---|---|
| `prompt_metal_layer` | `args["METAL"]` parse path in `cli.py` |
| `prompt_exit_metal_layer` | `args["EXITMETAL"]` parse path |
| `prompt_unique_shape_name` | `args["NAME"]` validation in `cli.Repl` |

These bookkeeping rows account for **31 backend / utility C
functions** that need no dedicated Python implementation.

## Coverage summary

| Bucket | Total C funcs | Ported in Python | % |
|---|---:|---:|---:|
| Inductance kernels (Grover/Greenhouse) | 9 | 5 | 56% |
| Resistance | 5 | 2 | 40% |
| Network (Y/Z/S, Pi/Pi3/Pi4, Zin, SelfRes, ShuntR) | 14 | 13 | 93% |
| Transformer analysis (CalcTrans) | 2 | 1 | 50% |
| Filament solver + MNA + eddy currents | 6 | 5 (partial) | 83% |
| Geometry builders | 12 | 10 | 83% |
| Tech file parsing | 8 | 1 (subset) | 12% |
| Layout exports (CIF, Tek, Sonnet, SPICE, FastHenry) | 6 | 5 (partial) | 83% |
| Save/load | 4 | 1 (subsumes) | 100% (functional) |
| Optimisation (Opt/Sweep family) | 9 | 6 | 67% |
| Info commands (Geom/MetArea/LRMAT/ListSegs) | 5 | 4 | 80% |
| Substrate Green's (incl. Sommerfeld + FFT + eddy) | 12 | 7 | 58% |
| Coupled-microstrip H/J caps (Cp, Cf, Cf′, Cga, Cgd, Z_e/Z_o) | 2 | 2 | 100% |
| Polygon edge ops (forward/backward 2-D diff) | 2 | 2 | 100% |
| Chip-edge segment extension | 1 | 1 | 100% |
| Three-class DC-resistance accumulator | 1 | 1 | 100% |
| Multi-shape bounding-box utility | 1 | 1 | 100% |
| Substrate Green's primitives (γ, Γ per layer) | 3 | 3 | 100% |
| FFT-conv Green's pipeline (compute_green_function, fft_apply_to_green, rasterize, cap-matrix) | 4 | 4 | 100% |
| GDSII export / import (gdstk-based) | 0 (new) | 4 | n/a |
| Eddy-matrix packed index | 1 | 1 | 100% |
| Orthogonal & general-3D segment mutuals | 4 | 4 | 100% |
| 2-port Y-derived helpers (z_2port_from_y, imag_z_2port_from_y, zin_terminated_2port) | 3 | 3 | 100% |
| Sommerfeld inner integrand cluster | 4 | 4 | 100% |

Explicit decomp names ported in the inner-integrand cluster:
``green_oscillating_integrand``, ``green_propagation_integrand``,
``green_function_kernel_a_oscillating``, ``green_function_kernel_b_reflection``.

Other already-ported decomp names whose canonical form lives under
a renamed Python symbol:
``compute_overall_bounding_box`` → ``shapes_bounding_box``;
``forward_diff_2d_inplace`` / ``backward_diff_2d_inplace`` →
``polygon_edge_vectors``; ``compute_dc_resistance_3metal_constants``
→ ``three_class_resistance``; ``complex_propagation_constant_a`` /
``complex_propagation_constant_b`` → ``propagation_constant``;
``reflection_coeff_imag`` → ``layer_reflection_coefficient``;
``shape_extend_last_to_chip_edge`` → ``extend_last_segment_to_chip_edge``.


| Filament-pair primitives (mutual_inductance_filament_kernel, wire_axial_separation, wire_separation_periodic) | 3 | 3 | 100% |
| Filament-list assembly + impedance-matrix fill (build_filament_list, filament_list_setup, fill_inductance_diagonal/_offdiag, fill_impedance_matrix_triangular, filament_pair_4corner_integration) | 6 | 6 | 100% |
| Per-segment substrate-cap pipeline (capacitance_setup, capacitance_segment_integral, capacitance_integral_inner_a/b, capacitance_per_segment, analyze_capacitance_polygon, analyze_capacitance_driver) | 7 | 7 | 100% |
| Spiral / cell-sizing helpers (spiral_FindMaxN, spiral_radius_for_N, spiral_turn_position_recursive, wire_position_periodic_fold, segment_pair_distance_metric) | 5 | 5 | 100% |
| Shape mutations (shape_terminal_segment_extend_unit, shape_emit_vias_at_layer_transitions) | 2 | 2 | 100% |
| MNA matrix helpers (node_eq_assemble, node_eq_setup_rhs, node_eq_unpack_forward/_backward) | 4 | 4 | 100% |
| LMAT subblock + partial-trace helpers (lmat_subblock_assemble, lmat_compute_partial_traces) | 2 | 2 | 100% |
| Trivial helpers subsumed by NumPy/SciPy/stdlib | 31 | 31 | 100% |
| Shape transforms (Move/Flip/Rotate) | 6 | 4 | 67% |
| REPL commands | 117 | 117 | 100% |
| GUI (X11/Mesa front-end → Tk) | 28 | 12 | 43% |
| **Total identified C functions** | **643** | ~263 | ~41% |

## GUI (X11 / Mesa → Tk)

| C function (decomp) | Address | Python equivalent |
|---|---|---|
| `init_x11_and_gl` | `0x0807fc9c` | `reasitic.gui.app.GuiApp.__init__` |
| `xui_init_resources` | `0x0807ff18` | `reasitic.gui.app.GuiApp.__init__` (toolbar, menu, palettes) |
| `xui_render_layout_view` | `0x08080b48` | `reasitic.gui.renderer.render_all` |
| `xui_redraw_substrate_polygons` | `0x0807f0c4` | `reasitic.gui.renderer.draw_polygon` (per-shape loop) |
| `xui_redraw_substrate_grid` | `0x0807f4dc` | `reasitic.gui.renderer.draw_grid` |
| `xui_draw_chip_outline` | `0x08082010` | `reasitic.gui.renderer.draw_chip_outline` |
| `xui_draw_grid_or_ruler` | `0x08081c0c` | `reasitic.gui.renderer.draw_grid` |
| `xui_draw_zoom_box_around_current_shape` | `0x08081a24` | `reasitic.gui.renderer.draw_selection` |
| `xui_draw_string_at_world` | `0x08081764` | Tk `Canvas.create_text` (per-shape label) |
| `xui_blit_pixmap_double_buffer` | `0x08081890` | implicit — Tk double-buffers internally |
| `view_zoom_to_rectangle` | `0x0807fb18` | `reasitic.gui.viewport.Viewport.fit_bbox` |
| `cmd_scale_clamp_view` | `0x08081dc4` | `reasitic.gui.viewport.Viewport.zoom_at_screen` |
| `xui_destroy_window_and_close` | `0x08081d10` | `Tk.destroy()` (handled by `mainloop` exit) |

The plan in [PLAN.md](./PLAN.md) tracks the remaining phases; this
mapping is the line-item view of what's been moved across.
