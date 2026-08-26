# H3 Preregistration Amendment Memo — V1 to V2

The V1 preparation gate failed before any outcome join.

The failure was caused by an implementation assumption, not by observed H3
results: already-aggregated security-month attention was required to be equal
for every security sharing an issuer CIK.

That is too strong for mid-month issuer continuity events.

The corrected invariant moves the equality test to the daily level, where
simultaneously active securities of one issuer must agree. The data are then
deduplicated to one issuer-day and aggregated to issuer-month.

This preserves the original purpose of issuer-level attention while correctly
handling sequential security identities.

No outcome data were read before this amendment. No H3 model, coefficient,
control, test direction, covariance rule, alpha, or multiple-testing rule was
changed.
