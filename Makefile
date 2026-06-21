# Minimal Makefile — coverage convenience target.
# The logic lives in util/run_coverage.bash (single source of truth); this is a thin wrapper.
.PHONY: coverage
coverage:  ## Reproduce the CI coverage gate locally (full suite)
	@bash util/run_coverage.bash
