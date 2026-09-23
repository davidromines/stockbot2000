Your response was TRUNCATED at the output limit. It stopped mid-line at 28.5 KB
inside the file, with no closing fence, so nothing could be saved. The content
up to that point looked good — the problem is length, not quality.

Write the SAME test, compact:

- Target 250 to 320 lines TOTAL. Hard ceiling 350.
- One short module docstring (under 15 lines). No per-test docstrings — the
  check() name already says what is tested.
- One shared fixture builder that creates the in-memory db, both symbols'
  bars, and the listings. Reuse it; do not rebuild data in every test.
- Generate the synthetic bars with a short loop, not literal lists.
- Keep every requirement from the task, but merge related assertions into
  fewer functions. Requirements 3-7 (fund) can share one fixture and two or
  three functions; requirements 8-9 (brokers) one function; requirement 10
  (risk floors) one function with its four assertions; requirement 11 one
  function.
- End the file with the closing fence. If you find yourself running long, cut
  prose and comments, never a requirement.