# Optional Synthea development backend

This is the implemented, opt-in bridge from an externally supplied Synthea checkout to the exact PPOC schema. The native generator remains the ordinary and release-one route; this backend never changes the default `synthetic.generate` command or its fail-closed behavior.

## What it generates

The bridge runs Synthea revision `d9d07a6eef91ee5144293b42ab64224d84d124f8` with the checked-in Gradle wrapper `9.2.1` and Java 17. It requests fictional pediatric members aged 0–18 at a fixed reference date and reads only the resulting FHIR R4 JSON. Synthea supplies the correlated healthy measurement trajectories; the checked-in Generic Module Framework overlay samples a fictional growth-hormone-deficiency (GHD) event with prior `0.143291`, and the adapter applies the versioned `synthea-growth-overlay-v1` attenuation to height and weight while recomputing BMI. The prior is a development scenario, not a clinical or population prevalence estimate.

The adapter projects only the six base resources in `datapackage.json` and delegates the two augmented resources to the existing test-only source-matched augmenter. It creates fresh deterministic PPOC patient and visit IDs, keeps Synthea names, addresses, UUIDs, raw FHIR, and hidden disorder state out of the package, and returns only aggregate run counts and digests in its in-memory report. A successful `manifest.json` has `engine="synthea"` and `test_only_derivation=true`.

Race projection follows the source schema's missing-value convention: an absent primary race is `Unknown`, while unpopulated race slots (including slots after the last FHIR race extension) are empty strings. This keeps `race_2`–`race_8` predominantly blank instead of turning structural missingness into repeated `Unknown` values.

Here, `healthy_count` means the member did not receive the fictional GHD event or growth attenuation; it does not mean that every unrelated Synthea condition was removed. Only conditions carrying an ICD-10 coding-system entry are projected into `enc_diag_*`; non-ICD conditions are discarded, so every populated encounter diagnosis in the generated package is an ICD-10 code. Synthea labs, medications, problem-list entries, and referrals are intentionally empty in this first adapter slice.

## Prerequisites

The caller obtains Synthea outside this repository and checks out the exact revision. The adapter verifies the revision and tracked-tree cleanliness before copying the checkout into a private temporary build root; it never modifies the caller checkout.

```sh
git clone https://github.com/synthetichealth/synthea.git /tmp/synthea
git -C /tmp/synthea checkout d9d07a6eef91ee5144293b42ab64224d84d124f8
uv sync
```

Use an explicit Java 17 installation and a writable Gradle cache. The adapter verifies `java -version` and rejects Java 26, an implicit system Java, or a different wrapper/revision. Gradle is offline by default, so the cache must already contain the wrapper and dependencies; pass `--allow-gradle-network` only when an explicit dependency download is intended.

```sh
export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
export GRADLE_USER_HOME=/tmp/synthea-gradle-home
```

## One command

Run from the repository root and choose a new output directory. The patient count must be between 1 and 10,000; use a fixed seed for reproducible fixtures.

```sh
uv run python scripts/synthea_backend.py \
  --synthea-root /tmp/synthea \
  --output /tmp/ppoc-synthea-development \
  --patients 1000 \
  --seed 20260901 \
  --java-home "$JAVA_HOME"
```

The command prints the promoted package path followed by one aggregate JSON report. It exits with the fixed message `synthea backend unavailable` for checkout, Java, Gradle, FHIR, schema, augmentation, or validation failures. Existing output paths are never overwritten. If the Gradle cache is not populated, rerun with the explicit `--allow-gradle-network` option rather than changing the command arguments or the checkout.

The successful package contains exactly the eight descriptor resources plus `datapackage.json`, `validation-report.json`, and `manifest.json`:

```text
patients.csv                 visits.csv
labs.csv                     medications.csv
problem_list.csv             referrals.csv
patients_augmented.csv       visits_augmented.csv
datapackage.json             validation-report.json
manifest.json
```

Inspect the manifest and validation report after generation:

```sh
jq '{engine, profile, test_only_derivation, row_counts, status}' \
  /tmp/ppoc-synthea-development/manifest.json
jq '{errors, warnings, row_counts}' \
  /tmp/ppoc-synthea-development/validation-report.json
```

For reproducibility, generate into two different fresh output paths with the same checkout, Java 17, seed, patient count, reference time, and software revision, then compare all non-manifest files. The report's `ghd_count`, `healthy_count`, visit count, and anthropometry counts are aggregate checks; they do not expose patient-level truth.

## Java and Gradle note

Java 17 remains the required adapter runtime even if a newer locally installed Gradle can compile Synthea with Java 26. The pinned Synthea wrapper is Gradle 9.2.1 and fails under Java 26 before compilation (`Unsupported class file major version 70`); Homebrew Gradle 9.7.1 is not a replacement for that checked-in wrapper. The full upstream Synthea test task also exits `134` in this environment under both Java 26 and Java 17, so that abort is a separate upstream test-executor/environment issue rather than a reason to switch the adapter to Java 26. The focused GeneratorTest and the adapter's `run` smoke complete on the Java 17 path.

## Boundaries

This backend is a development bridge, not a Synthea conformance result or a clinical simulator. Its fixed GHD prior, demographics inherited from Synthea, and growth overlay are intentionally fictional and are not evidence of real prevalence, demographic representativeness, clinical validity, task utility, or model performance. Fresh IDs and synthetic-only inputs reduce accidental leakage but do not prove that a generated profile cannot be matched to a real patient; non-matchability requires a separate qualified privacy evaluation and still cannot be proven absolutely.

The repository does not vendor Synthea source, Java, Gradle distributions, generated FHIR, or an output package. The adapter accepts no real-data root, governed calibration/held-out input, patient profile, arbitrary module, diagnosis payload, or network URL. The ordinary native profiles remain independent, and the default/no-profile CLI continues to fail closed with `No production growth reference or authoritative derivation oracle is configured`.

For the declaration-only conformance contract and its separate clinical, population, privacy, held-out, and release gates, see [Synthea engine conformance](synthea-conformance.md). For the ordinary native and development profiles, see the [synthetic generator guide](synthetic-generator.md).
