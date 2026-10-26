# Pre-evaluation clarification: isolate first-disclosure timing

Recorded on 2026-10-27 (Asia/Shanghai), before any held-out filing was parsed.

The first development implementation of `period_end` selected the first disclosed value
forever. This changed two mechanisms: it made a number available too early and prevented
subsequent legitimate revisions from updating it. Differences after the first disclosure
could therefore reflect stale-version retention rather than premature availability alone.

The final protocol changes only the first disclosure's effective timestamp to the financial
period end. All subsequent revisions retain their actual `available_at` timestamps. At and
after the first actual availability, `period_end` and `pit` must select the same revenue
and status. Before that availability, the baseline may expose the first source early.

The number of modes, sample, split, dates, source collection, revenue definition and growth
formula are unchanged. `latest` and `pit` are unchanged. No held-out outcome motivated this
clarification; it came from an independent AI review of the experimental intervention.

Earlier development observations, rankings and summary remain under
`data/exploratory/pre_timing_clarification/` with hashes and their code commit. They are
explicitly superseded exploration, not current release results. Final development results
are regenerated and the rule freeze is created only after this change passes validation.

Interpretation consequence: after both timing-baseline and PIT observations are usable,
their values should match. Premature use is visible in future-source counts and
baseline-only usable observations, rather than in a nonzero paired numeric difference.
