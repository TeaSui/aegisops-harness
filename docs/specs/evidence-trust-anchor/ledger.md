# Ledger — evidence-trust-anchor

Append-only, written by `aidlc` only.

- 2026-11-26T08:00:01Z advance proposed→accepted
- 2026-11-26T08:00:01Z advance accepted→planned
- 2026-11-26T08:00:02Z advance planned→building
- 2026-11-26T08:02:26Z task-done T1 exit=0 fingerprint=c436c7ae8f370ade745fd32eb91d6187b0fd633f11e23ebe6d4c24a4356e4d89 cmd="python3 -m unittest tests.test_autopilot tests.test_check_setup"
- 2026-11-26T08:04:34Z task-done T2 exit=0 fingerprint=4fbfcf60852f99c0b45c34c24152224492f78247c415f03bc6757525d5c2c6bd cmd="python3 -m unittest tests.test_evals"
- 2026-11-26T08:15:30Z task-done T3 exit=0 fingerprint=c193f415a3526a23f5ec18771a4e08fc333ad3b43864c3a8cd753605667a5997 cmd="python3 -m unittest tests.test_evals tests.test_eval_cases"
- 2026-11-26T08:25:36Z task-done T4 exit=0 fingerprint=776bbd3a572c28972f97429d1f742994d83c9b2b5d9d18aff48a3135a4b8aab1 cmd="python3 -m unittest tests.test_aidlc tests.test_trust_anchor"
- 2026-11-26T08:29:57Z task-done T5 exit=0 fingerprint=552139a255422f946f060fa9abf2c843fe1d8d866fc4c3692546f6ae1b9e9271 cmd="python3 -m unittest tests.test_trust_anchor"
- 2026-11-26T08:33:51Z task-done T6 exit=0 fingerprint=8e049fa2ba0ee8dda3d1f5ed6d172d2512e9ca484fe9de09b7e6239e050eb6b4 cmd="python3 -m unittest tests.test_aidlc tests.test_trust_anchor"
- 2026-11-26T08:39:55Z task-done T7 exit=0 fingerprint=ac7309ff302c31fb8ddf89ed2a436a69dad5e73a0d37cd02dafba18b72c925a7 cmd="python3 -m unittest tests.test_trust_anchor tests.test_evals"
- 2026-11-26T08:50:45Z task-done T8 exit=0 fingerprint=490223993386d3a66afd1203936786e11c7f1975fb1415afd212441e8a5a5c50 cmd="python3 -m unittest tests.test_trust_anchor tests.test_evidence_guard"
- 2026-11-26T08:51:11Z task-done T9 exit=0 fingerprint=490223993386d3a66afd1203936786e11c7f1975fb1415afd212441e8a5a5c50 cmd="python3 -m unittest tests.test_trust_anchor tests.test_evidence_guard tests.test_record_returns"
- 2026-11-26T08:58:53Z task-done T10 exit=0 fingerprint=cd7633c2a9442ad7ed0e22c807c87e451bf24f2b7b6bee45600ad231ca77491e cmd="python3 -m unittest tests.test_hook_commands tests.test_ship_gate"
- 2026-11-26T09:09:46Z task-done T11 exit=0 fingerprint=a2f2761363f92d406fca79bef05fdc88a1c9ef61b0f92005caba5251c00e2898 cmd="python3 -m unittest discover -s tests"
- 2026-11-26T09:11:06Z advance building→proposed back reason="6.0.0: an approval is an event the owner records (aidlc approve). The session that built this change cannot record it, and the accepted_by line it typed under 5.0.0 approves nothing"
- 2026-11-26T10:58:12Z revert-check exit=1 fingerprint=2ffdef29887bb23536caf63da9c7de38d31644ef0b7218361d6ebee589f71d56 base=ccf82d035326 files=23 junit=173 passed, 266 failed
- 2026-11-26T10:59:53Z verify exit=0 fingerprint=2ffdef29887bb23536caf63da9c7de38d31644ef0b7218361d6ebee589f71d56 cmd="python3 tests/junit_runner.py -s tests -o reports/junit.xml" pinned=onboarding junit=460 passed, 0 failed req-pass=ETA-1,ETA-10,ETA-11,ETA-12,ETA-13,ETA-14,ETA-15,ETA-2,ETA-3,ETA-4,ETA-5,ETA-6,ETA-7,ETA-8,ETA-9
- 2026-11-26T16:08:05Z approve spec=5a5a48cda6677496ed6e83b0ec23f37be7f4777625840328c8cc247e31f83553 by="Tea Nguyen" how=approved
- 2026-11-26T16:09:23Z advance proposed→accepted
- 2026-11-26T16:09:23Z advance accepted→planned
- 2026-11-26T16:09:23Z advance planned→building
- 2026-11-26T16:09:28Z advance building→verified
- 2026-11-26T16:42:52Z revert-check exit=1 fingerprint=14497fa306f9643eccb899efc9479f8ab19331f6ed639871eaa604a9339e3863 base=ccf82d035326 files=23 junit=173 passed, 271 failed
- 2026-11-26T16:45:49Z verify exit=0 fingerprint=14497fa306f9643eccb899efc9479f8ab19331f6ed639871eaa604a9339e3863 cmd="python3 tests/junit_runner.py -s tests -o reports/junit.xml" pinned=onboarding junit=466 passed, 0 failed req-pass=ETA-1,ETA-10,ETA-11,ETA-12,ETA-13,ETA-14,ETA-15,ETA-2,ETA-3,ETA-4,ETA-5,ETA-6,ETA-7,ETA-8,ETA-9
