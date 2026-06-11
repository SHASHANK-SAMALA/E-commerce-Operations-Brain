"""Test mem0 add + recall pipeline end-to-end."""
import time
from ecommerce_brain.memory.mem0_integration import add_investigation_memory, recall_similar

SID = "session-mem0-test-final"

ok = add_investigation_memory(
    query_id="test-final-001",
    query="Revenue dropped 9 percent - paused campaigns and stockouts confirmed",
    root_causes=["Paused CAM-003 CAM-005 campaigns", "ELEC-001 ELEC-004 out of stock"],
    actions_taken=["resume_campaign", "restock_product"],
    evidence_score=0.896,
    session_id=SID,
)
print("add result:", ok)

time.sleep(2)

results = recall_similar("sales drop campaigns paused stockouts", session_id=SID, limit=5)
print("recall hits:", len(results))
for r in results:
    print(" -", r.get("memory", "")[:120])
