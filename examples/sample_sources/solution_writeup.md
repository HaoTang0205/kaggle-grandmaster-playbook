# Sample Solution Write-up

Metric: AUC.

We used target encoding with grouped cross-validation. Key idea: avoid leakage by fitting encoders inside folds. We found pseudo labels improved the private leaderboard after calibration.
