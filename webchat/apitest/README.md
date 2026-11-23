# Black-box API tests

These tests treat the stack as a deployed system: they start `docker compose`, call the public REST
API and open WebSocket sessions. They do not import service code.

## Layout (to be created)

```
apitest/
  rest/           # requests against /api/v1, one folder per flow
  ws/             # WebSocket frames, incl. reconnect and replay
  fixtures/       # two users, one friendship, one group
  run.sh          # entry point used by CI
```

`run.sh` must:

1. start the stack and wait for all three health checks;
2. create the fixture users through the public API;
3. run the REST and WebSocket suites;
4. print a failure summary and exit non-zero on the first failed assertion;
5. delete the stack volume so the next run starts clean.

The cases in the spec's "Kiểm thử và nghiệm thu" section are the acceptance list. Contract validation
belongs to `contracts/`, not here.
