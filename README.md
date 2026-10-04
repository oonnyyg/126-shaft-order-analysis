# Shaft Order Analysis

Angular-domain order analysis for variable-speed shaft vibration, using only
the Python standard library. It aligns two independently acquired records —
shaft angle vs. time and vibration vs. time — and reports per-revolution
order amplitudes.

## Input

Two CSV files (optional header row `time_s,...`):

- Angle CSV: `time_s, cumulative_angle_rad` — time in seconds, cumulative
  angle in radians (not wrapped to one revolution). Both columns must be
  finite and strictly increasing.
- Vibration CSV: `time_s, vibration` — finite values, time strictly
  increasing.

The two records may use different, non-aligned time grids.

## Method

1. **Overlap**: only the time range covered by both records is used.
2. **Complete revolutions**: revolutions are delimited by integer multiples
   of `2*pi` of the cumulative angle. Incomplete leading/trailing fractions
   of a revolution are discarded; nothing is extrapolated or zero-padded.
3. **Resampling**: each revolution is sampled at `N` (positive even)
   equally spaced angles, including the start and excluding the end. The
   sample time is found by inverse interpolation of the angle record, then
   the vibration is linearly interpolated at that time. Samples are never
   taken by evenly dividing raw record indices.
4. **Orders**: each revolution's samples are de-meaned, then a DFT gives the
   peak amplitude of order `k` as `2*|X_k|/N`. Only integer orders
   `1 <= k < N/2` are accepted. No windowing, no power spectrum.

## Definitions

- **Order k**: vibration component completing exactly `k` cycles per shaft
  revolution.
- **Amplitude**: peak (not RMS) amplitude of that sinusoid, `2*|X_k|/N`
  after mean removal.
- **Mean speed**: `1 / (t_end - t_start)` of the revolution, in rev/s.
- **RMS by order**: root-mean-square of the per-revolution amplitudes of
  each order across all complete revolutions.
- **Synchronous average**: sample-by-sample average of all per-revolution
  waveforms; its orders are computed by DFT of that averaged waveform (not
  by averaging per-revolution amplitudes, which ignores phase).

## Usage

```
python -m shaft_order_analysis.cli \
    --angle-csv angle.csv --vibration-csv vib.csv \
    --points-per-rev 64 --orders 1,2,3,4 \
    --resampled-csv resampled.csv --json-report report.json
```

Outputs:

- Resampled CSV: `revolution, sample_index, angle_rad, time_s, vibration`.
- JSON report: config, per-revolution speeds and order amplitudes, RMS by
  order, synchronous-average order amplitudes, and `empty_reason` when no
  complete revolution exists (empty results are explicit, never silent).

## Tests

```
python -m unittest discover -s tests
```

Covers constant and varying speed, mismatched time grids, DC offset
removal, partial-revolution trimming, empty-result reasons, and the
distinction between synchronous averaging and mean-of-amplitudes.
