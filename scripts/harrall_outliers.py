import pandas as pd
import numpy as np


def _find_peaks_in_iteration(
    df: pd.DataFrame,
    pid_col: str,
    age_col: str,
    measure_col: str,
    apply_threshold: bool = False,
) -> set[int]:
    """
    Perform the core peak detection logic for identifying biologically implausible growth peaks
    (caps and cups) in longitudinal data using the Harrall algorithm.

    This function implements the iterative peak detection steps based on slope analysis
    of growth measurements. It identifies points where the growth trajectory shows
    significant inflection points (peaks) that are biologically improbable.

    The algorithm analyzes the change in slopes between consecutive measurements to
    identify potential caps (local maxima) and cups (local minima) in the growth curve,
    then refines these using magnitude comparisons.

    Args:
        df (pd.DataFrame): Input DataFrame containing growth data, sorted by participant and age.
        pid_col (str): Column name for participant ID.
        age_col (str): Column name for age (in years).
        measure_col (str): Column name for the growth measurement (height or weight).
        apply_threshold (bool, optional): If True, apply age-based slope thresholds for
            weight measurements. Defaults to False (used for height).

    Returns:
        set[int]: Set of row indices (_track_rows) representing detected peaks.

    Notes:
        - Data must be sorted by pid_col and age_col before calling.
        - The function uses vectorized pandas/numpy operations for performance.
        - For weight measurements, age-specific slope thresholds help distinguish
          biologically plausible from implausible changes.
        - The algorithm corresponds to the iterative peak removal steps in the
          Harrall et al. (2024) publication.
    """
    if df.empty:
        return set()

    # Ensure data is sorted by participant and age for proper time-sequenced analysis
    df = df.sort_values([pid_col, age_col])

    # Step 1: Calculate instantaneous slope between consecutive measurements for each participant
    # Slope = d(measure)/d(age) represents growth velocity
    age_diff = df.groupby(df[pid_col])[age_col].diff()
    measure_diff = df.groupby(df[pid_col])[measure_col].diff()
    slope = measure_diff / age_diff.replace(0, 0.001)  # Avoid division by zero

    # Step 2: Determine sign of slope (+1 for increasing, -1 for decreasing, 0 for flat)
    sign = np.sign(slope)

    # Step 3: Get the sign of the previous measurement's slope for trend analysis
    prev_sign = sign.groupby(df[pid_col]).shift(1).fillna(0)

    # Step 4: Compute sum of current and previous signs to detect curvature changes
    # Sum = 2: both positive (accelerating growth)
    # Sum = 0: signs differ (inflection point: peak or valley)
    # Sum = -2: both negative (accelerating decline)
    sum_signs = sign + prev_sign

    # Step 5: Lag the sum of signs for further pattern analysis
    prev_sum_signs = sum_signs.groupby(df[pid_col]).shift(1)

    # Step 6-8: Compute reverse-lagged sum of signs (next point's sum_signs)
    # This creates a 3-point window analysis around each measurement
    prev_rev_sum_signs = sum_signs.groupby(df[pid_col]).shift(-1)

    # Step 9: Identify potential caps (local maxima) and cups (local minima)
    # Caps: abrupt increase followed by decrease (maxima in growth curve)
    # Cups: abrupt decrease followed by increase (minima in growth curve)
    pos_peak_cap = ((abs(sum_signs) == 2) & (prev_rev_sum_signs == 0)) | (
        (sum_signs.isnull()) & (prev_rev_sum_signs == 0)
    )

    pos_peak_cup = ((sum_signs == 0) & (abs(prev_sum_signs) == 2)) | (
        (sum_signs.isnull()) & (prev_rev_sum_signs == 0)
    )

    # Step 10-11: Refine peaks by comparing additional slope magnitudes around candidate points
    # Calculate multi-point slopes for comprehensive curvature analysis:
    # - XB slope: from 2 points before to current (for cup analysis)
    # - AY slope: from current to 2 points after (for cap analysis)
    # - BY slope: from current to next point (baseline for comparison)
    prev_measure = df.groupby(df[pid_col])[measure_col].shift(1)
    prev2_measure = df.groupby(df[pid_col])[measure_col].shift(2)
    prev_age = df.groupby(df[pid_col])[age_col].shift(1)
    prev2_age = df.groupby(df[pid_col])[age_col].shift(2)

    xb_age_diff = (df[age_col] - prev2_age).replace(0, 0.001)
    xb_slope = (df[measure_col] - prev2_measure) / xb_age_diff

    next_measure = df.groupby(df[pid_col])[measure_col].shift(-1)
    next2_measure = df.groupby(df[pid_col])[measure_col].shift(-2)
    next_age = df.groupby(df[pid_col])[age_col].shift(-1)
    next2_age = df.groupby(df[pid_col])[age_col].shift(-2)

    ay_age_diff = (next2_age - df[age_col]).replace(0, 0.001)
    ay_slope = (next2_measure - df[measure_col]) / ay_age_diff

    by_age_diff = (next_age - df[age_col]).replace(0, 0.001)
    by_slope = (next_measure - df[measure_col]) / by_age_diff

    # Calculate slope differences for magnitude-based elimination
    # These differences help rank peaks by their severity/impact
    cap_diff = ay_slope - slope  # Magnitude metric for caps
    cup_diff = xb_slope - by_slope  # Magnitude metric for cups

    prev_cap_diff = cap_diff.groupby(df[pid_col]).shift(1)
    prev_rev_cup_diff = cup_diff.groupby(df[pid_col]).shift(-1)

    # Final peak selection: Combine potential peaks with magnitude comparisons
    # Select peaks where the slope discontinuity is most pronounced
    is_peak = (
        (pos_peak_cap & pos_peak_cup)  # Simultaneous cap and cup detection
        | (
            pos_peak_cap & (cap_diff < prev_rev_cup_diff)
        )  # Cap with smaller neighbor cup diff
        | (
            pos_peak_cap & (cap_diff == prev_rev_cup_diff)
        )  # Cap with equal neighbor cup diff
        | (
            pos_peak_cup & (cup_diff < prev_cap_diff)
        )  # Cup with smaller neighbor cap diff
        | (
            pos_peak_cup & (cup_diff == prev_cap_diff)
        )  # Cup with equal neighbor cap diff
    ).fillna(False)

    final_flag = is_peak

    # Step 12 (Weight Only): Apply age-specific slope thresholds to reduce false positives
    # Weight growth varies significantly by age, so we use empirical thresholds
    # based on expected maximum growth rates for each age group
    if apply_threshold:
        # Age-based threshold conditions: each condition is "age < X"
        # The corresponding choice is the max allowable slope for that age range
        conditions = [
            df[age_col] < 3,
            df[age_col] < 4,
            df[age_col] < 5,
            df[age_col] < 6,
            df[age_col] < 7,
            df[age_col] < 8,
            df[age_col] < 9,
            df[age_col] < 10,
            df[age_col] < 11,
            df[age_col] < 12,
            df[age_col] < 13,
            df[age_col] < 14,
            df[age_col] < 15,
            df[age_col] < 16,
            df[age_col] < 17,
        ]
        choices = [
            3.0,  # < 3 years: max 3.0 kg/year
            3.3,  # 3-4 years: max 3.3 kg/year
            3.7,  # 4-5 years: max 3.7 kg/year
            4.0,  # 5-6 years: max 4.0 kg/year
            4.4,  # 6-7 years: max 4.4 kg/year
            5.2,  # 7-8 years: max 5.2 kg/year
            6.0,  # 8-9 years: max 6.0 kg/year
            6.8,  # 9-10 years: max 6.8 kg/year
            7.3,  # 10-11 years: max 7.3 kg/year
            7.2,  # 11-12 years: max 7.2 kg/year
            6.5,  # 12-13 years: max 6.5 kg/year
            5.3,  # 13-14 years: max 5.3 kg/year
            4.0,  # 14-15 years: max 4.0 kg/year
            2.7,  # 15-16 years: max 2.7 kg/year
            1.8,  # 16-17 years: max 1.8 kg/year
            # >= 17 years: max 1.3 kg/year (default)
        ]
        threshold = np.select(conditions, choices, default=1.3)
        is_over_threshold = abs(slope) > threshold
        final_flag = is_peak & is_over_threshold

    peak_indices = df[final_flag]["_track_rows"].to_list()
    return set(peak_indices)


def _detect_outliers(
    df: pd.DataFrame,
    pid_col: str,
    age_col: str,
    measure_col: str,
    apply_threshold: bool = False,
) -> set[int]:
    """
    Perform iterative outlier detection for growth measurements using the Harrall algorithm.

    This function repeatedly identifies and removes biologically implausible peaks
    (caps and cups) from growth data until no more anomalies can be found. It starts
    with initial cleanup steps to remove obvious duplicates and zero-slope repeats,
    then iteratively applies peak detection to refine the dataset.

    The process continues until convergence, where no new peaks are identified in
    an iteration. This corresponds to the iterative outlier removal described in
    Harrall et al. (2024).

    Args:
        df (pd.DataFrame): Input DataFrame with growth data, must include '_track_rows' column
            for indexing. Data should be sorted by participant and age.
        pid_col (str): Column name for participant ID.
        age_col (str): Column name for age (in years).
        measure_col (str): Column name for the growth measurement.
        apply_threshold (bool, optional): Whether to apply slope thresholds (used for weight).
            Defaults to False.

    Returns:
        set[int]: Set of row indices (_track_rows) representing all identified outliers.

    Notes:
        - The function modifies a working copy of the data and tracks original indices.
        - Initial cleanup removes exact duplicates and points with zero slope change.
        - Iterative peak detection uses slope analysis to find biologically implausible
          inflection points.
        - Convergence is reached when no new peaks are found in an iteration.
    """
    # Remove rows with missing key values (participant ID handled separately)
    work_df = df.dropna(subset=[measure_col, age_col]).copy()
    all_outlier_indices = set()

    # Initial Cleanup Phase: Remove obviously erroneous data points
    # 1. Exact duplicates: multiple entries with same pid, age, and measurement
    # These are likely data entry errors or duplicate records
    duplicates = work_df[
        work_df.duplicated(subset=[pid_col, age_col, measure_col], keep=False)
    ]
    all_outlier_indices.update(duplicates["_track_rows"])

    # 2. Zero-slope repeats: consecutive measurements with same value (no change)
    # These could indicate measurement errors or true plateaus, but are flagged for review
    slope = work_df.groupby(pid_col)[measure_col].diff() / work_df.groupby(pid_col)[
        age_col
    ].diff().replace(0, np.nan)
    zero_slopes = work_df[slope == 0]
    all_outlier_indices.update(zero_slopes["_track_rows"])

    # Create cleaned dataset for iterative peak detection
    iter_df = work_df[~work_df["_track_rows"].isin(all_outlier_indices)].copy()

    # Iterative Peak Detection: Repeatedly find and remove biologically implausible peaks
    # Each iteration refines the growth curve by eliminating the most problematic points
    # Convergence occurs when no additional peaks are found
    while True:
        peak_indices_this_iter = _find_peaks_in_iteration(
            iter_df, pid_col, age_col, measure_col, apply_threshold
        )

        # Stop when no more peaks are detected (algorithm has converged)
        if not peak_indices_this_iter:
            break

        # Accumulate outlier indices across iterations
        all_outlier_indices.update(peak_indices_this_iter)

        # Remove detected peaks from working dataset for next iteration
        iter_df = iter_df[~iter_df["_track_rows"].isin(peak_indices_this_iter)].copy()

    return all_outlier_indices


def detect_harrall_outliers(
    df: pd.DataFrame,
    pid_col: str,
    age_col: str,
    height_col: str,
    weight_col: str,
    height_flag_col: str,
    weight_flag_col: str,
) -> pd.DataFrame:
    """
    Identify outliers in pediatric height and weight measurements using the Harrall algorithm.

    This function applies the Harrall algorithm to longitudinal growth data, iteratively
    detecting and removing biologically implausible peaks (local maxima and minima, or
    "caps" and "cups") in growth trajectories. The algorithm considers each participant's
    growth curve separately and uses slope-based analysis to identify anomalies.

    Key features:
    - Height outliers: Detected without thresholds, based on slope discontinuities alone.
    - Weight outliers: Detected using age-specific slope thresholds to account for expected
      weight gain variations by age.
    - Iterative process: Continues until no new outliers are found in an iteration.
    - Vectorized implementation: Uses pandas and numpy for efficient computation on
      large datasets.

    The algorithm improves upon previous methods by focusing on biologically implausible
    inflection points in growth curves, rather than absolute thresholds, making it more
    sensitive to genuine outliers while reducing false positives.

    Args:
        df (pd.DataFrame): Input DataFrame containing longitudinal growth data.
            Must include columns for participant ID, age, height, and weight.
            Data will be sorted internally by participant and age.
        pid_col (str): Name of the column containing participant IDs.
        age_col (str): Name of the column containing age in years (numeric).
        height_col (str): Name of the column containing height measurements.
        weight_col (str): Name of the column containing weight measurements.
        height_flag_col (str): Name for the new column containing int flags
            for height outliers (1 = outlier, 0 = plausible).
        weight_flag_col (str): Name for the new column containing int flags
            for weight outliers (1 = outlier, 0 = plausible).

    Returns:
        pd.DataFrame: The input DataFrame with two additional int columns
            (height_flag_col and weight_flag_col) indicating identified outliers.
            Original data ordering and indices are preserved.

    Raises:
        KeyError: If required columns (pid_col, age_col, height_col, weight_col)
            are not present in the DataFrame.
        ValueError: If DataFrame is malformed (e.g., missing numeric data where expected).

    Examples:
        >>> import pandas as pd
        >>> import numpy as np
        >>> data = {
        ...     'participant_id': [1, 1, 1, 2, 2],
        ...     'age_years': [5.0, 6.0, 7.0, 5.5, 6.5],
        ...     'height_cm': [110, 115, 120, 112, 118],
        ...     'weight_kg': [20, 22, 24, 21, 23]
        ... }
        >>> df = pd.DataFrame(data)
        >>> result = detect_harrall_outliers(
        ...     df, 'participant_id', 'age_years', 'height_cm', 'weight_kg',
        ...     'height_outlier', 'weight_outlier'
        ... )
        >>> result['height_outlier'].sum()  # Number of height outliers
        0
        >>> result['weight_outlier'].sum()  # Number of weight outliers
        0

    References:
        Harrall, K.K., Bird, S.M., Muller, K.E. et al. A better performing algorithm
        for identification of implausible growth data from longitudinal pediatric
        medical records. Sci Rep 14, 18276 (2024).
        https://doi.org/10.1038/s41598-024-69161-5
    """
    # Handle edge case of empty DataFrame
    if df.empty:
        df[height_flag_col] = 0
        df[weight_flag_col] = 0
        return df

    # Prepare working DataFrame for analysis
    # Sort by participant and age to ensure chronological order
    # Add tracking column to maintain original index mapping
    work_df = df.copy()
    work_df.sort_values(by=[pid_col, age_col], inplace=True)
    work_df["_track_rows"] = range(len(work_df))

    # Apply outlier detection algorithm to height measurements
    # Height outliers detected using slope discontinuities only (no age-based thresholds)
    height_outlier_indices = _detect_outliers(
        work_df, pid_col, age_col, height_col, apply_threshold=False
    )

    # Apply outlier detection algorithm to weight measurements
    # Weight outliers use both slope discontinuities AND age-based thresholds
    weight_outlier_indices = _detect_outliers(
        work_df, pid_col, age_col, weight_col, apply_threshold=True
    )

    # Initialize flag columns in original DataFrame
    # Only set flags for rows that have valid measurements
    df[height_flag_col] = np.nan
    df[weight_flag_col] = np.nan

    # Get valid measurement indices (non-NA values)
    valid_height_indices = df[df[height_col].notna()].index
    valid_weight_indices = df[df[weight_col].notna()].index

    # Set default values (0 = plausible) for rows with valid measurements
    df.loc[valid_height_indices, height_flag_col] = 0
    df.loc[valid_weight_indices, weight_flag_col] = 0

    # Map working DataFrame indices back to original DataFrame indices
    # Height outlier indices
    original_indices_ht = work_df[
        work_df["_track_rows"].isin(height_outlier_indices)
    ].index
    # Weight outlier indices
    original_indices_wt = work_df[
        work_df["_track_rows"].isin(weight_outlier_indices)
    ].index

    # Set outlier flags to 1 for detected outliers (only for rows with valid measurements)
    df.loc[original_indices_ht, height_flag_col] = 1
    df.loc[original_indices_wt, weight_flag_col] = 1

    # Set the column dtypes to Int8 to handle 0, 1, and NA values
    df[height_flag_col] = df[height_flag_col].astype("Int8")
    df[weight_flag_col] = df[weight_flag_col].astype("Int8")

    # Return DataFrame with added outlier flags
    return df
