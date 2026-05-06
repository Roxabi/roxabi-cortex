.PHONY: cortex-insight cortex-memory start stop reload status logs

# Pattern Roxabi: `make <svc> <action>` where action ∈ {start, stop, reload, status, logs}
# Aligned with ~/projects/Makefile and conf.d/*.mk (ADR-002)
# Replace echo stubs with systemctl --user once Quadlet units are installed.

cortex-insight:
	@echo "TODO: cortex-insight $(filter-out cortex-insight, $(MAKECMDGOALS))"
	@echo "  → systemctl --user $(filter-out cortex-insight, $(MAKECMDGOALS)) cortex-insight.service"

cortex-memory:
	@echo "TODO: cortex-memory $(filter-out cortex-memory, $(MAKECMDGOALS))"
	@echo "  → systemctl --user $(filter-out cortex-memory, $(MAKECMDGOALS)) cortex-memory.service"

start stop reload status logs:
	@:
