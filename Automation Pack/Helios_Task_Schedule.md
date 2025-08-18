| Task | Script | Frequency | Start Time |
|------|--------|-----------|------------|
| Helios_Triage_Tasks | core_py\run_agent_triage.py | PT4H | 2025-08-06T06:00:00 |
| Helios_Starling_Ingestion | core_py\modules\fss\starling_ingestion.py | P1D | 2025-08-06T02:00:00 |
| Helios_Run_FSS | core_py\core\run_fss.py | P1W | 2025-08-11T05:00:00 |
| Helios_Agentic_Nudges | curl http://localhost:3333/api/agent-nudge | PT3H | 2025-08-06T07:00:00 |