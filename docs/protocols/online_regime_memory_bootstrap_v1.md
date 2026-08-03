# Online regime memory bootstrap v1

Gate B uses seeds 4100--4199 and a frozen outcome-blind four-cell assignment:
stable-bias/compensation, stable-bias/retry, stochastic-noise/compensation, and
stochastic-noise/retry. It retains the first five eligible failures per cell,
for exactly 20 selected-action records and 10 records per action.

Each episode executes only its manifest-assigned action. An unselected paired
outcome is neither executed nor stored. All ACCEPTED, INCONCLUSIVE, and REJECTED
selected-action outcomes enter the immutable statistical audit; only ACCEPTED
records appear in the verified-example index. Records become retrievable from
the next episode and all retrieval remains action-specific.

This is an infrastructure bootstrap, not evidence that memory improves an
online Agent. It cannot call GLM, run Gate C, or support validation/held-out
claims.
