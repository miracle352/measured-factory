# Stage 1 probes (spec-only)
Needs the mock web (see challenge README) with MOCK_ADMIN_TOKEN, and the service wired to it.
  SVC=http://localhost:8000 MOCK=http://localhost:8080 ADMIN=local-admin python3 -I probe.py all
Single probes: python3 -I probe.py build_core idempotency ...  (names without p_ prefix). selftest checks the embedded Appendix A reference against the spec examples.
Each failure prints an exam-list id (E-xx). Probes assume mock epoch 0 and sample corpus; they reset the mock themselves.
